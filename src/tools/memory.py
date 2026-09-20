from typing import Annotated

from src.config import SEARCH_MAX_RESULTS, SNIPPET_CONTEXT_CHARS
from src.core import dialog_memory, memory
from src.tools.registry import tool


def _snippet(text: str, query: str, radius: int) -> str | None:
    idx = text.lower().find(query.lower())
    if idx == -1:
        return None
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


@tool("Запомнить важный факт о человеке, группе или мире. Передавай название, значение, теги (список, например ['Про nakiperu', 'музыка']) и, при необходимости, uid владельца.")
def add_memory(
    name: str,
    value: str,
    tags: Annotated[list[str] | None, "Список тегов/категорий факта"] = None,
    owner_uid: Annotated[int | None, "uid владельца факта (если факт о конкретном человеке)"] = None,
) -> str:
    memory.add(name, value, tags=tags, user_id=owner_uid)
    return f"Сохранено: {name} = {value}"


@tool("Показать все уникальные теги (категории) сохранённых фактов — например, 'Про nakiperu'. Используй, чтобы узнать, какие категории вообще есть.")
def list_memory_tags() -> str:
    tags = memory.get_all_tags()
    if not tags:
        return "Тегов пока нет."
    return "\n".join(tags)


@tool("Показать все факты из категории (тега). Передавай точное название тега.")
def get_memory_by_tag(tag: str) -> str:
    pairs = memory.get_by_tag(tag)
    if not pairs:
        return f"Фактов с тегом '{tag}' нет."
    return "\n".join(f"{p.name} = {p.value}" for p in pairs)


@tool("Поиск по текущим диалогам (все роли, все пользователи), сохранённым парам памяти и их тегам. Возвращает сниппеты с найденным словом. Можно дополнительно указать тег для поиска только внутри категории.")
def search_memory(
    query: str,
    tag: Annotated[str | None, "Искать только внутри тега/категории"] = None,
) -> str:
    results: list[str] = []
    for msg in dialog_memory.all_messages():
        snip = _snippet(msg.content, query, SNIPPET_CONTEXT_CHARS)
        if snip:
            results.append(f"[чат:{msg.role}] {snip}")
    for p in memory.search(query, tag=tag, limit=SEARCH_MAX_RESULTS):
        tags = ", ".join(p.tags) if p.tags else "без тегов"
        owner = f" (uid={p.user_id})" if p.user_id else ""
        results.append(f"[память{owner}] [{tags}] {p.name} = {p.value}")
    if not results:
        return "Ничего не найдено."
    return "\n".join(results)


@tool("Показать все сохранённые пары «название — значение» с тегами и владельцем.")
def list_memory() -> str:
    pairs = memory.get_all_full()
    if not pairs:
        return "Память пуста."
    lines: list[str] = []
    for p in pairs:
        tags = ", ".join(p.tags) if p.tags else "без тегов"
        owner = f" (uid={p.user_id})" if p.user_id else ""
        lines.append(f"[{tags}]{owner} {p.name} = {p.value}")
    return "\n".join(lines)


@tool("Удалить пару из памяти по названию.")
def delete_memory(name: str) -> str:
    if memory.delete(name):
        return f"Удалено: {name}"
    return f"Пара '{name}' не найдена."
