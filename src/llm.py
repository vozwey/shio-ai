from dataclasses import dataclass
import json
import logging

from src.config import (
    ANSWER_MAX_CHAR,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_REASONING_EFFORT,
    OPENAI_TEMPERATURE,
    TOOL_RESULT_MAX_CHAR,
)

from src.core import client, dialog_memory
from src.tools.registry import execute_tool, get_tools_schema, inject_tools_prompt
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

presets = {
    f.name: f.read_text(encoding="utf-8").strip()
    for f in PROMPTS_DIR.iterdir()
    if f.is_file()
}


def _elide(text: str, head: int = 25, tail: int = 25) -> str:
    if len(text) <= head + tail + 3:
        return text
    return f"{text[:head]}...{text[-tail:]}"


def _log_value(value) -> str:
    if isinstance(value, str):
        return _elide(value)
    return _elide(json.dumps(value, ensure_ascii=False))


@dataclass
class UserInfo:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None


def get_preset(preset: str) -> str:
    prompt = presets.get(preset, presets["default"])

    return inject_tools_prompt(prompt)


def get_presets() -> list[str]:
    return sorted(presets)


def _who_block(user_info: UserInfo | None) -> str:
    if not user_info:
        return ""
    who = f"{user_info.first_name}"
    if user_info.last_name:
        who += f" {user_info.last_name}"
    if user_info.username:
        who += f" (@{user_info.username})"
    return f"\n\nСобеседник: {who} (uid={user_info.id})."


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[обрезано]"


def build_messages(
    user_id: int,
    new_text: str,
    user_info: UserInfo | None = None,
    image_urls: list[str] | None = None,
) -> list[dict]:
    history = dialog_memory.get_context(user_id)
    system_msgs = [m for m in history if m.role == "system"]
    non_system = [m for m in history if m.role != "system"]
    if system_msgs:
        system_content = system_msgs[-1].content
    else:
        system_content = get_preset("default")
    messages = [{"role": "system", "content": system_content + _who_block(user_info)}]
    messages.extend({"role": m.role, "content": m.content} for m in non_system)
    if image_urls:
        content: list[dict] = [{"type": "text", "text": new_text}]
        content.extend(
            {"type": "image_url", "image_url": {"url": u}} for u in image_urls
        )
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": new_text})
    logger.debug(">>> LLM input (%d messages):", len(messages))
    for m in messages:
        logger.debug("    [%s] %s", m["role"], _log_value(m["content"]))
    return messages


async def ask_llm(
    user_id: int,
    text: str,
    user_info: UserInfo | None = None,
    image_urls: list[str] | None = None,
) -> str:
    text = text[:ANSWER_MAX_CHAR]
    messages = build_messages(user_id, text, user_info, image_urls)
    answer = ""

    while True:
        create_kwargs = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature": OPENAI_TEMPERATURE,
            "max_tokens": OPENAI_MAX_TOKENS,
            "tools": get_tools_schema(),
            "tool_choice": "auto",
        }
        if OPENAI_REASONING_EFFORT is not None:
            create_kwargs["reasoning_effort"] = OPENAI_REASONING_EFFORT
        response = await client.chat.completions.create(**create_kwargs)
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            logger.info(">>> tool_calls:")
            for tc in message.tool_calls:
                logger.info(
                    "    - %s(%s)", tc.function.name, _log_value(tc.function.arguments)
                )
            messages = [
                m
                for m in messages
                if m["role"] != "tool"
                and not (m["role"] == "assistant" and m.get("tool_calls"))
            ]
            messages.append(message.model_dump(mode="json", exclude_unset=True))
            from src.tools.registry import execute_tool

            for tc in message.tool_calls:
                result = await execute_tool(
                    user_id, tc.function.name, tc.function.arguments
                )
                logger.info("    <- %s = %s", tc.function.name, _log_value(result))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _truncate(result, TOOL_RESULT_MAX_CHAR),
                    }
                )
            continue

        answer = message.content

        if not answer:
            continue
        break

    logger.info("<<< LLM answer: %s", _log_value(answer))

    answer = answer[:ANSWER_MAX_CHAR]
    vanswer = answer.translate(
        str.maketrans(
            {
                "з": "z",
                "З": "Z",
                "в": "v",
                "В": "V",
            }
        )
    )

    dialog_memory.add(user_id, "user", text)
    dialog_memory.add(user_id, "assistant", answer)

    return vanswer
