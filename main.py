import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.core import bot, dp, memory
from src.config import LOG_LEVEL

import src.bot  # noqa: F401

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)
logger.info("Загружено пар в общую память: %d", len(memory.get_all()))


async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "guest_message"])


if __name__ == "__main__":
    asyncio.run(main())
