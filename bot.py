import json
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from openai import AsyncOpenAI

from config import (
    ANSWER_MAX_CHAR,
    CONTEXT_SIZE,
    LOG_LEVEL,
    MEMORY_DB_PATH,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    SEARCH_MAX_RESULTS,
    SNIPPET_CONTEXT_CHARS,
    TELEGRAM_BOT_TOKEN,
    TOOL_MAX_ITERATIONS,
    TOOL_RESULT_MAX_CHAR,
)
from storage import DialogMemory, Memory
import base64
import hashlib
from ddgs import DDGS

logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
memory = Memory(MEMORY_DB_PATH)
dialog_memory = DialogMemory(context_size=CONTEXT_SIZE)

logger.info("Загружено пар в общую память: %d", len(memory.get_all()))

SYSTEM_PROMPT = (
    "Пиши максимально коротко. Делай то что говорит пользователь.\n"
    "Учитывай предыдущие инструкции, тон и сообщения пользователя — продолжай диалог в его стиле "
    "Если просят написать текст — пиши только текст, без пояснений.\n"
    "У тебя есть инструменты: search_web (поиск в интернете), add_memory (запомнить пару "
    "«название — значение»), search_memory (поиск по текущим диалогам и парам памяти), "
    "list_memory (показать все сохранённые пары). Используй их эффективно и по делу: немного, "
    "но применяй для проверки фактов и информации, в которой не уверен. "
    "Все важные факты о пользователе (имя, предпочтения, данные, воспоминания) записывай через "
    "add_memory как пары «название — значение» — память общая на всех пользователей, "
    "так ты будешь помнить их в будущем. "
    "Результаты инструментов в ответ пользователю не выводи — используй их только для себя."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Поиск информации в интернете через DuckDuckGo. "
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
                "Запомнить важную пару «название — значение» о пользователе или информацию на будущее "
                "(имя, предпочтения, данные, воспоминания). Память общая на всех пользователей. "
                "Передавай название и значение отдельными полями."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Название факта"},
                    "value": {"type": "string", "description": "Значение факта"},
                },
                "required": ["name", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Поиск по текущим диалогам (все роли, все пользователи) и сохранённым парам памяти. "
                "Возвращает сниппеты с найденным словом."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Что ищем"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memory",
            "description": "Показать все сохранённые пары «название — значение».",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[обрезано]"


def _snippet(text: str, query: str, radius: int) -> str | None:
    idx = text.lower().find(query.lower())
    if idx == -1:
        return None
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def web_search(query: str, max_results: int = 3) -> str:
    try:
        results = DDGS().text(query, max_results=max_results)
        context = "\n\n".join(
            [f"Заголовок: {r['title']}\nТекст: {r['body']}" for r in results]
        )
        return context
    except Exception as e:
        return f"Ошибка поиска: {e}"


async def execute_tool(user_id: int, name: str, args: str) -> str:
    params = json.loads(args)
    try:
        if name == "search_web":
            return web_search(params["query"])
        if name == "add_memory":
            memory.add(params["name"], params["value"])
            return f"Сохранено: {params['name']} = {params['value']}"
        if name == "search_memory":
            query = params["query"]
            results: list[str] = []
            for msg in dialog_memory.all_messages():
                snip = _snippet(msg.content, query, SNIPPET_CONTEXT_CHARS)
                if snip:
                    results.append(f"[чат:{msg.role}] {snip}")
            for n, v in memory.search(query):
                results.append(f"[память] {n} = {v}")
            if not results:
                return "Ничего не найдено."
            return "\n".join(results[:SEARCH_MAX_RESULTS])
        if name == "list_memory":
            pairs = memory.get_all()
            if not pairs:
                return "Память пуста."
            return "\n".join(f"{n} = {v}" for n, v in pairs)
        return "Неизвестный инструмент."
    except Exception as e:
        logger.exception("Ошибка при выполнении тула %s", name)
        return f"Ошибка тула: {e}"


async def ask_llm(user_id: int, text: str, image_urls: list[str] | None = None) -> str:
    text = text[:ANSWER_MAX_CHAR]
    messages = build_messages(user_id, text, image_urls)
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
                result = await execute_tool(
                    user_id, tc.function.name, tc.function.arguments
                )
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

    answer = answer[:ANSWER_MAX_CHAR]
    dialog_memory.add(user_id, "user", text)
    dialog_memory.add(user_id, "assistant", answer)
    return answer


def build_messages(
    user_id: int, new_text: str, image_urls: list[str] | None = None
) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in dialog_memory.get_context(user_id):
        messages.append({"role": msg.role, "content": msg.content})
    if image_urls:
        content: list[dict] = [{"type": "text", "text": new_text}]
        content.extend(
            {"type": "image_url", "image_url": {"url": u}} for u in image_urls
        )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": new_text})
    return messages


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я - СЫН ШЛЮХИ. Отправь мне сообщение, или вызови через @ в любом чате."
    )
    await bot.set_my_commands(
        [BotCommand(command="start", description="Запустить бота")]
    )


async def _collect_image_urls(message: Message) -> list[str]:
    urls: list[str] = []

    async def _dl(file_id: str, mime: str) -> str:
        file = await bot.get_file(file_id)
        content = await bot.download_file(file.file_path)
        b64 = base64.b64encode(content.read()).decode()
        return f"data:{mime};base64,{b64}"

    if message.photo:
        urls.append(await _dl(message.photo[-1].file_id, "image/jpeg"))
    elif (
        message.document
        and message.document.mime_type
        and message.document.mime_type.startswith("image/")
    ):
        urls.append(await _dl(message.document.file_id, message.document.mime_type))

    rt = message.reply_to_message
    if rt:
        if rt.photo:
            urls.append(await _dl(rt.photo[-1].file_id, "image/jpeg"))
        elif (
            rt.document
            and rt.document.mime_type
            and rt.document.mime_type.startswith("image/")
        ):
            urls.append(await _dl(rt.document.file_id, rt.document.mime_type))

    return urls


def _collect_text(message: Message, bot_username: str) -> str:
    parts: list[str] = []

    rt = message.reply_to_message
    if rt:
        sender = rt.from_user.first_name if rt.from_user else "Собеседник"
        replied_text = rt.text or rt.caption or "[медиафайл/картинка]"
        parts.append(f'[В ответ на сообщение от {sender}: "{replied_text}"]')
    elif message.quote:
        parts.append(f'[Цитата: "{message.quote.text}"]')

    current = message.text or message.caption or ""
    clean_query = current.lower().replace(f"@{bot_username.lower()}", "").strip()

    if clean_query:
        parts.append(clean_query)
    elif rt:
        parts.append("Ответь на сообщение выше или опиши прикреплённое медиа.")

    return "\n\n".join(parts)


async def process_and_reply(message: Message):
    if not message.from_user:
        return

    bot_info = await bot.get_me()
    bot_username = bot_info.username

    prompt_text = _collect_text(message, bot_username)
    if not prompt_text:
        return

    try:
        image_urls = await _collect_image_urls(message)
    except Exception as e:
        logger.warning("Не удалось загрузить изображение: %s", e)
        image_urls = []

    try:
        answer = await ask_llm(message.from_user.id, prompt_text, image_urls or None)
    except Exception as e:
        logger.exception("Ошибка ask_llm")
        answer = f"Произошла ошибка: {e}"

    if getattr(message, "guest_query_id", None):
        result_id = hashlib.md5(f"g_{message.guest_query_id}".encode()).hexdigest()
        result = InlineQueryResultArticle(
            id=result_id,
            title="Ответ",
            input_message_content=InputTextMessageContent(message_text=answer),
        )
        await message.answer_guest_query(result=result)
    else:
        await message.reply(answer)


@dp.guest_message()
async def handle_guest(message: Message):
    await process_and_reply(message)


@dp.message(
    F.text
    | F.caption
    | F.photo
    | (F.document & F.document.mime_type.startswith("image/"))
)
async def handle_normal_message(message: Message):
    bot_info = await bot.get_me()
    bot_tag = f"@{bot_info.username.lower()}"

    if message.chat.type == "private":
        await process_and_reply(message)
        return

    raw_text = (message.text or message.caption or "").lower()
    is_replied_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_info.id
    )

    if bot_tag in raw_text or is_replied_to_bot:
        await process_and_reply(message)
