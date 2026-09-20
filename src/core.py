from aiogram import Bot, Dispatcher
from openai import AsyncOpenAI

from src.config import (
    CONTEXT_SIZE,
    MEMORY_DB_PATH,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    TELEGRAM_BOT_TOKEN,
)
from src.storage import DialogMemory, Memory

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
client_kwargs: dict[str, str] = {"base_url": OPENAI_BASE_URL}
if OPENAI_API_KEY is not None:
    client_kwargs["api_key"] = OPENAI_API_KEY
client = AsyncOpenAI(**client_kwargs)
memory = Memory(MEMORY_DB_PATH)
dialog_memory = DialogMemory(context_size=CONTEXT_SIZE)

__all__ = ["bot", "dp", "client", "memory", "dialog_memory"]
