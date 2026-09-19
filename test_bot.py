import asyncio
import os
from dataclasses import dataclass

import config

config.TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
config.OPENAI_API_KEY = "sk-test"
config.OPENAI_BASE_URL = "http://localhost:9999"
config.OPENAI_MODEL = "test-model"
config.MEMORY_DB_PATH = "test_bot.db"

if os.path.exists("test_bot.db"):
    os.remove("test_bot.db")

from unittest.mock import AsyncMock, patch

from storage import DialogMemory

TEST_ANSWER = "Привет, это тестовый ответ!"


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


async def test_full_cycle():
    dialog_memory = DialogMemory()
    user_id = 42

    with patch("bot.client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=CompletionResponse(choices=[Choice(message=M(content=TEST_ANSWER))])
        )

        from bot import ask_llm

        answer = await ask_llm(user_id, "Привет!")
        assert answer == TEST_ANSWER, answer

    from bot import dialog_memory as bot_dialog_memory
    ctx = bot_dialog_memory.get_context(user_id)
    assert len(ctx) == 2, ctx
    assert ctx[0].role == "user" and ctx[0].content == "Привет!", ctx
    assert ctx[1].role == "assistant" and ctx[1].content == TEST_ANSWER, ctx

    with patch("bot.client") as mock_client:
        captured = None

        async def capture(**kwargs):
            nonlocal captured
            captured = kwargs["messages"]
            return CompletionResponse(choices=[Choice(message=M(content="ок"))])

        mock_client.chat.completions.create = AsyncMock(side_effect=capture)
        from bot import ask_llm

        await ask_llm(user_id, "Как дела?")

    assert captured is not None
    assert captured[0]["role"] == "system"
    assert captured[1]["role"] == "user" and captured[1]["content"] == "Привет!"
    assert captured[2]["role"] == "assistant" and captured[2]["content"] == TEST_ANSWER
    assert captured[3]["role"] == "user" and captured[3]["content"] == "Как дела?"

    print("ALL_TESTS_PASSED")


if __name__ == "__main__":
    asyncio.run(test_full_cycle())
