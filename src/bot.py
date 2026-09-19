import base64
import hashlib
import logging

from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from src.core import bot, dp
from src.llm import ask_llm

logger = logging.getLogger(__name__)


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
