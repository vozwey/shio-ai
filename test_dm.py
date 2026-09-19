import asyncio
import os
from dataclasses import dataclass
from datetime import datetime

import config

config.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
config.OPENAI_API_KEY = "sk-test"
config.OPENAI_BASE_URL = "http://localhost:9999"
config.OPENAI_MODEL = "test-model"
config.MEMORY_DB_PATH = "test_dm.db"

if os.path.exists("test_dm.db"):
    os.remove("test_dm.db")

from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Update, User, Message, Chat

from bot import dp
from storage import DialogMemory

TEST_ANSWER = "dm-ответ"


@dataclass
class Choice:
    message: "M"


@dataclass
class M:
    content: str
    tool_calls: list | None = None


@dataclass
class CompletionResponse:
    choices: list[Choice]


async def test_dm():
    user = User(id=555, is_bot=False, first_name="Test")
    chat = Chat(id=555, type="private", first_name="Test")
    msg = Message(
        message_id=1,
        date=datetime(2024, 1, 1, 0, 0, 0),
        chat=chat,
        from_user=user,
        text="привет бот",
    )
    update = Update(update_id=1, message=msg)

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    captured_methods = []

    async def capture(bot_instance, method: SendMessage, timeout=None):
        captured_methods.append(method)
        return {"ok": True, "result": True}

    with patch.object(bot.session, "make_request", capture):
        with patch("bot.client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=CompletionResponse(choices=[Choice(message=M(content=TEST_ANSWER))])
            )
            await dp.feed_update(bot=bot, update=update)

    assert len(captured_methods) == 2, captured_methods
    assert captured_methods[0].text == "Думаю..."
    assert captured_methods[1].text == TEST_ANSWER

    from bot import dialog_memory as bot_dialog_memory
    ctx = bot_dialog_memory.get_context(555)
    assert len(ctx) == 2
    assert ctx[0].content == "привет бот"
    assert ctx[1].content == TEST_ANSWER

    print("DM_TEST_PASSED")


if __name__ == "__main__":
    asyncio.run(test_dm())
