from dataclasses import dataclass

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


@dataclass
class UserInfo:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None


def get_system_prompt() -> str:
    with open("src/prompts/system.txt", encoding="utf-8") as f:
        template = f.read().strip()
    return inject_tools_prompt(template)


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
    system_content = get_system_prompt()
    if user_info:
        who = f"{user_info.first_name}"
        if user_info.last_name:
            who += f" {user_info.last_name}"
        if user_info.username:
            who += f" (@{user_info.username})"
        system_content += f"\n\nСобеседник: {who} (uid={user_info.id})."
    messages = [{"role": "system", "content": system_content}]
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
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _truncate(result, TOOL_RESULT_MAX_CHAR),
                    }
                )
            continue

        answer = message.content
        if answer is None:
            continue
        break

    answer = answer[:ANSWER_MAX_CHAR]
    dialog_memory.add(user_id, "user", text)
    dialog_memory.add(user_id, "assistant", answer)
    return answer
