import asyncio
import os
from dataclasses import dataclass
from datetime import datetime

import config

config.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
config.OPENAI_API_KEY = "sk-test"
config.OPENAI_BASE_URL = "http://localhost:9999"
config.OPENAI_MODEL = "test-model"
config.MEMORY_DB_PATH = "test_len.db"

if os.path.exists("test_len.db"):
    os.remove("test_len.db")

from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.types import Update, User, Message, Chat
from bot import ANSWER_MAX_CHAR, OPENAI_MAX_TOKENS, dp

from storage import DialogMemory

@dataclass
class Choice:
    message: "M"
@dataclass
class M:
    content: str
    tool_calls: list | None = None
@dataclass
class Resp:
    choices: list[Choice]

async def main():
    long = "x" * 10000
    huge_input = "y" * 10000
    user = User(id=999, is_bot=False, first_name="Test")
    chat = Chat(id=999, type="private", first_name="Test")
    msg = Message(message_id=1, date=datetime(2024, 1, 1), chat=chat, from_user=user, text=huge_input)
    update = Update(update_id=1, message=msg)
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    captured = []
    async def fake(bot_instance, method, timeout=None):
        captured.append((type(method).__name__, method))
        return {"ok": True, "result": True}
    with patch.object(bot.session, "make_request", fake):
        with patch("bot.client") as mc:
            mc.chat.completions.create = AsyncMock(return_value=Resp(choices=[Choice(message=M(content=long))]))
            await dp.feed_update(bot=bot, update=update)
    create_kwargs = mc.chat.completions.create.call_args.kwargs
    last_user_msg = [m for m in create_kwargs["messages"] if m["role"] == "user"][-1]
    assert len(last_user_msg["content"]) == ANSWER_MAX_CHAR, len(last_user_msg["content"])
    assert create_kwargs["max_tokens"] == OPENAI_MAX_TOKENS, create_kwargs["max_tokens"]
    assert len(captured[1][1].text) == ANSWER_MAX_CHAR, len(captured[1][1].text)
    # память сохранилась
    from bot import dialog_memory as bot_dialog_memory
    ctx = bot_dialog_memory.get_context(999)
    assert len(ctx) == 2
    assert len(ctx[0].content) == ANSWER_MAX_CHAR
    assert len(ctx[1].content) == ANSWER_MAX_CHAR

    print("LENGTH_LIMIT_OK")

asyncio.run(main())
