import asyncio
import os
from dataclasses import dataclass
from datetime import datetime

import config

config.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
config.OPENAI_API_KEY = "sk-test"
config.OPENAI_BASE_URL = "http://localhost:9999"
config.OPENAI_MODEL = "test-model"
config.MEMORY_DB_PATH = "test_tools.db"
config.FOURGET_BASE_URL = "http://localhost:9998"

if os.path.exists("test_tools.db"):
    os.remove("test_tools.db")
if os.path.exists("test_tools_memory.db"):
    os.remove("test_tools_memory.db")

from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.types import Update, User, Message, Chat
from bot import dp, TOOLS
from storage import DialogMemory, Memory

TOOL_CALL_ID = "call_abc123"


@dataclass
class FunctionCall:
    name: str
    arguments: str


@dataclass
class ToolCall:
    id: str
    function: FunctionCall


@dataclass
class M:
    content: str | None
    tool_calls: list[ToolCall] | None


@dataclass
class Choice:
    message: M


@dataclass
class Resp:
    choices: list[Choice]


async def test_tool_loop():
    user = User(id=111, is_bot=False, first_name="Test")
    chat = Chat(id=111, type="private", first_name="Test")
    msg = Message(
        message_id=1,
        date=datetime(2024, 1, 1),
        chat=chat,
        from_user=user,
        text="Найди что-нибудь в интернете",
    )
    update = Update(update_id=1, message=msg)

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    captured_methods = []
    llm_calls = []

    async def fake(bot_instance, method, timeout=None):
        captured_methods.append((type(method).__name__, method))
        return {"ok": True, "result": True}

    async def llm_side_effect(**kwargs):
        llm_calls.append(kwargs)
        if len(llm_calls) == 1:
            # первый вызов: модель просит тул
            return Resp(
                choices=[
                    Choice(
                        message=M(
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id=TOOL_CALL_ID,
                                    function=FunctionCall(
                                        name="search_web",
                                        arguments='{"query": "тест"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        # второй вызов: финальный ответ
        return Resp(choices=[Choice(message=M(content="Вот что я нашёл.", tool_calls=None))])

    with patch("bot.web_search", new=AsyncMock(return_value="Ничего не найдено.")):
        with patch.object(bot.session, "make_request", fake):
            with patch("bot.client") as mock_client:
                mock_client.chat.completions.create = AsyncMock(side_effect=llm_side_effect)
                await dp.feed_update(bot=bot, update=update)

    # LLM вызван дважды: тул + финал
    assert len(llm_calls) == 2, llm_calls
    # второй вызов получил результат тула в messages
    second_messages = llm_calls[1]["messages"]
    tool_msgs = [m for m in second_messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == TOOL_CALL_ID
    assert "Ничего не найдено." in tool_msgs[0]["content"]

    # финальный ответ без результата тула
    assert len(captured_methods) == 2
    assert captured_methods[1][1].text == "Вот что я нашёл."
    assert "Ничего не найдено." not in captured_methods[1][1].text

    # в памяти только user + assistant
    from bot import dialog_memory as bot_dialog_memory
    ctx = bot_dialog_memory.get_context(111)
    assert len(ctx) == 2
    assert ctx[0].role == "user"
    assert ctx[1].role == "assistant"
    assert ctx[1].content == "Вот что я нашёл."

    print("TOOL_LOOP_TEST_PASSED")


async def test_add_memory_tool():
    config.MEMORY_DB_PATH = "test_tools_memory.db"
    # пересоздаём хранилища после смены пути (в bot.py они модульные)
    import bot as bot_module

    bot_module.memory = Memory("test_tools_memory.db")
    bot_module.dialog_memory = DialogMemory()

    user = User(id=222, is_bot=False, first_name="Test")
    chat = Chat(id=222, type="private", first_name="Test")
    msg = Message(
        message_id=1,
        date=datetime(2024, 1, 1),
        chat=chat,
        from_user=user,
        text="Запомни: меня зовут Алекс",
    )
    update = Update(update_id=1, message=msg)
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    captured = []

    async def fake(bot_instance, method, timeout=None):
        captured.append((type(method).__name__, method))
        return {"ok": True, "result": True}

    call_count = [0]

    async def llm_side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return Resp(
                choices=[
                    Choice(
                        message=M(
                            content=None,
                            tool_calls=[
                                ToolCall(
                                    id=TOOL_CALL_ID,
                                    function=FunctionCall(
                                        name="add_memory",
                                        arguments='{"name": "имя", "value": "пользователя зовут Алекс"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        return Resp(choices=[Choice(message=M(content="Запомнил.", tool_calls=None))])

    with patch.object(bot.session, "make_request", fake):
        with patch("bot.client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(side_effect=llm_side_effect)
            await dp.feed_update(bot=bot, update=update)

    all_pairs = bot_module.memory.get_all()
    assert any("Алекс" in v for n, v in all_pairs), all_pairs
    assert captured[1][1].text == "Запомнил."

    if os.path.exists("test_tools_memory.db"):
        os.remove("test_tools_memory.db")
    print("ADD_MEMORY_TEST_PASSED")


async def test_list_and_search_memory():
    config.MEMORY_DB_PATH = "test_tools_memory.db"
    import bot as bot_module

    bot_module.memory = Memory("test_tools_memory.db")
    bot_module.dialog_memory = DialogMemory()

    # наполняем память парами и диалогами
    bot_module.memory.add("имя", "Алекс")
    bot_module.memory.add("предпочтение", "любит пиццу")
    bot_module.dialog_memory.add(1, "user", "привет, меня зовут Алекс")
    bot_module.dialog_memory.add(2, "user", "а я люблю пиццу и шио")

    from bot import execute_tool

    res = await execute_tool(1, "list_memory", "{}")
    assert "имя = Алекс" in res, res
    assert "предпочтение = любит пиццу" in res, res

    res = await execute_tool(1, "search_memory", '{"query": "пицц"}')
    assert "пицц" in res, res
    assert "[чат:user] а я люблю пиццу и шио" in res, res
    assert "[память] предпочтение = любит пиццу" in res, res

    res = await execute_tool(1, "search_memory", '{"query": "zzzнет"}')
    assert res == "Ничего не найдено.", res

    if os.path.exists("test_tools_memory.db"):
        os.remove("test_tools_memory.db")
    print("LIST_SEARCH_MEMORY_TEST_PASSED")


async def main():
    await test_tool_loop()
    await test_add_memory_tool()
    await test_list_and_search_memory()


if __name__ == "__main__":
    asyncio.run(main())
