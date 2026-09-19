import asyncio
import os
from dataclasses import dataclass

import config

config.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
config.OPENAI_API_KEY = "sk-test"
config.OPENAI_BASE_URL = "http://localhost:9999"
config.OPENAI_MODEL = "test-model"
config.MEMORY_DB_PATH = "test_inline.db"

if os.path.exists("test_inline.db"):
    os.remove("test_inline.db")

from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.methods import AnswerInlineQuery
from aiogram.types import Update, User, InlineQuery

from bot import dp
from storage import Memory

TEST_ANSWER = "inline-ответ"


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


async def test_inline():
    user = User(id=777, is_bot=False, first_name="Test")
    inline_query = InlineQuery(id="q1", from_user=user, query="тестовый запрос", offset="")
    update = Update(update_id=1, inline_query=inline_query)

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    captured_method = None

    async def capture_answer(bot_instance, method: AnswerInlineQuery, timeout=None):
        nonlocal captured_method
        captured_method = method
        return {"ok": True, "result": True}

    with patch.object(bot.session, "make_request", capture_answer):
        with patch("bot.client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(
                return_value=CompletionResponse(choices=[Choice(message=M(content=TEST_ANSWER))])
            )
            await dp.feed_update(bot=bot, update=update)

    assert captured_method is not None, "answer_inline_query не был вызван"
    assert len(captured_method.results) == 1
    result = captured_method.results[0]
    assert result.input_message_content.message_text == TEST_ANSWER
    assert result.description == TEST_ANSWER[:100]
    assert captured_method.cache_time == 0
    assert captured_method.is_personal is True

    memory = Memory("test_inline.db")
    ctx = memory.get_context(777)
    assert len(ctx) == 2
    assert ctx[0].content == "тестовый запрос"
    assert ctx[1].content == TEST_ANSWER

    os.remove("test_inline.db")
    print("INLINE_TEST_PASSED")


if __name__ == "__main__":
    asyncio.run(test_inline())
