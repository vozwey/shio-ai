from src.config import (
    ANSWER_MAX_CHAR,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    TOOL_MAX_ITERATIONS,
    TOOL_RESULT_MAX_CHAR,
)

from src.core import client, dialog_memory
from src.tools.registry import execute_tool, get_tools_schema, inject_tools_prompt


def get_system_prompt() -> str:
    with open("src/prompts/system.txt", encoding="utf-8") as f:
        template = f.read().strip()
    return inject_tools_prompt(template)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...[обрезано]"


def build_messages(
    user_id: int, new_text: str, image_urls: list[str] | None = None
) -> list[dict]:
    messages = [{"role": "system", "content": get_system_prompt()}]
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
    user_id: int, text: str, image_urls: list[str] | None = None
) -> str:
    text = text[:ANSWER_MAX_CHAR]
    messages = build_messages(user_id, text, image_urls)
    answer = ""

    for _ in range(TOOL_MAX_ITERATIONS):
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=OPENAI_MAX_TOKENS,
            tools=get_tools_schema(),
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            messages.append(message)
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

        answer = message.content or ""
        break
    else:
        answer = "Превышено число итераций инструментов."

    answer = answer[:ANSWER_MAX_CHAR]
    dialog_memory.add(user_id, "user", text)
    dialog_memory.add(user_id, "assistant", answer)
    return answer
