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


@tool("Запомнить важную пару «название — значение» о пользователе или информацию на будущее (имя, предпочтения, данные, воспоминания). Память общая на всех пользователей. Передавай название и значение отдельными полями.")
def add_memory(name: str, value: str) -> str:
    memory.add(name, value)
    return f"Сохранено: {name} = {value}"


@tool("Поиск по текущим диалогам (все роли, все пользователи) и сохранённым парам памяти. Возвращает сниппеты с найденным словом.")
def search_memory(query: str) -> str:
    results: list[str] = []
    for msg in dialog_memory.all_messages():
        snip = _snippet(msg.content, query, SNIPPET_CONTEXT_CHARS)
        if snip:
            results.append(f"[чат:{msg.role}] {snip}")
    for n, v in memory.search(query):
        results.append(f"[память] {n} = {v}")
    if not results:
        return "Ничего не найдено."
    return "\n".join(results[:SEARCH_MAX_RESULTS])


@tool("Показать все сохранённые пары «название — значение».")
def list_memory() -> str:
    pairs = memory.get_all()
    if not pairs:
        return "Память пуста."
    return "\n".join(f"{n} = {v}" for n, v in pairs)
