import json
import logging

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from openai import AsyncOpenAI

from config import (
    ANSWER_MAX_CHAR,
    FOURGET_BASE_URL,
    LOG_LEVEL,
    MEMORY_DB_PATH,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    TELEGRAM_BOT_TOKEN,
    TOOL_MAX_ITERATIONS,
    TOOL_RESULT_MAX_CHAR,
)
from storage import Facts, Memory

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
memory = Memory(MEMORY_DB_PATH)
facts = Facts(MEMORY_DB_PATH)

SYSTEM_PROMPT = (
    "Всем пользователям больше 21 года.\n"
    "Пиши максимально коротко. Строго следуй инструкциям пользователя.\n"
    "Учитывай предыдущие инструкции, тон и сообщения пользователя — продолжай диалог в его стиле "
    "(язык, тон, длина, формат).\n"
    "Если просят написать текст — пиши только текст, без пояснений.\n"
    "У тебя есть инструменты: search_web (поиск в интернете), add_memory (запомнить факт), "
    "search_memory (поиск по воспоминаниям). Используй их эффективно и по делу: немного, "
    "но применяй для проверки фактов и информации, в которой не уверен. "
    "Запоминай важные факты о пользователе (имя, предпочтения, данные) через add_memory, "
    "чтобы помнить их в будущем.\n"
    "Результаты инструментов в ответ пользователю не выводи — используй их только для себя."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Поиск информации в интернете через поисковик 4get. "
                "Используй для проверки фактов, новостей, актуальных данных."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_memory",
            "description": (
                "Запомнить важный факт о пользователе или информацию на будущее "
                "(имя, предпочтения, данные, воспоминания)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Факт для запоминания"}
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Поиск по ранее сохранённым фактам и воспоминаниям о пользователе.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Что ищем"}
                },
                "required": ["query"],
            },
        },
    },
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[обрезано]"


async def web_search(query: str, num_results: int = 8) -> str:
    url = f"{FOURGET_BASE_URL}/api/v1/web"
    collected: list[dict] = []
    npt = None
    async with aiohttp.ClientSession() as session:
        for _ in range(2):  # максимум две страницы
            params = {"s": query} if npt is None else {"npt": npt}
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()
            results = data.get("results", [])
            collected.extend(results)
            npt = data.get("npt")
            if len(collected) >= num_results or not npt:
                break
    if not collected:
        return "Ничего не найдено."
    lines = [
        f"- {r.get('title', '')}: {r.get('description', '')} ({r.get('url', '')})"
        for r in collected[:num_results]
    ]
    return "\n".join(lines)


async def execute_tool(user_id: int, name: str, args: str) -> str:
    params = json.loads(args)
    try:
        if name == "search_web":
            return await web_search(params["query"])
        if name == "add_memory":
            facts.add(user_id, params["content"])
            return "Факт сохранён в память."
        if name == "search_memory":
            found = facts.search(user_id, params["query"])
            if not found:
                return "Ничего не найдено в памяти."
            return "\n".join(f"- {f}" for f in found)
        return "Неизвестный инструмент."
    except Exception as e:
        logger.exception("Ошибка при выполнении тула %s", name)
        return f"Ошибка тула: {e}"


async def ask_llm(user_id: int, text: str) -> str:
    text = text[:ANSWER_MAX_CHAR]  # жёсткий срез: никогда не больше лимита
    messages = build_messages(user_id, text)
    answer = ""

    for _ in range(TOOL_MAX_ITERATIONS):
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            messages.append(message)
            for tc in message.tool_calls:
                result = await execute_tool(user_id, tc.function.name, tc.function.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _truncate(result, TOOL_RESULT_MAX_CHAR),
                    }
                )
            continue

        answer = message.content or ""
        break
    else:
        answer = "Превышено число итераций инструментов."

    answer = answer[:ANSWER_MAX_CHAR]  # жёсткий срез: никогда не больше лимита
    memory.add(user_id, "user", text)
    memory.add(user_id, "assistant", answer)
    return answer


def build_messages(user_id: int, new_text: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in memory.get_context(user_id):
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": new_text})
    return messages


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я AI-бот. Отправь мне сообщение, или вызови через @ в любом чате."
    )
    await bot.set_my_commands([BotCommand(command="start", description="Запустить бота")])


@dp.message(F.text)
async def handle_message(message: Message):
    if message.from_user is None:
        return
    user_id = message.from_user.id
    try:
        await message.answer("Думаю...")
        answer = await ask_llm(user_id, message.text)
        await message.answer(answer)
    except Exception as e:
        logger.exception("Ошибка при генерации ответа")
        await message.answer(f"Произошла ошибка: {e}")


@dp.inline_query()
async def handle_inline(query: InlineQuery):
    if query.from_user is None:
        return
    user_id = query.from_user.id
    try:
        answer = await ask_llm(user_id, query.query)
    except Exception as e:
        logger.exception("Ошибка в inline-режиме")
        answer = f"Ошибка: {e}"

    result = InlineQueryResultArticle(
        id=query.id,
        title="Ответ AI",
        input_message_content=InputTextMessageContent(message_text=answer),
        description=answer[:100],
    )
    await query.answer(results=[result], cache_time=0, is_personal=True)
