import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime


class DialogMemory:
    """Per-user контекст диалога — только в оперативной памяти (RAM).

    При перезапуске бота переписки теряются. Хранит последние
    context_size сообщений каждого пользователя, обрезая хвост.
    """

    def __init__(self, context_size: int = 20):
        self.context_size = context_size
        self._store: dict[int, list[Message]] = {}

    def add(self, user_id: int, role: str, content: str) -> None:
        msgs = self._store.setdefault(user_id, [])
        msgs.append(Message(role=role, content=content, created_at=datetime.now(timezone.utc)))
        del msgs[: -self.context_size]

    def get_context(self, user_id: int) -> list[Message]:
        return list(self._store.get(user_id, []))

    def all_messages(self) -> list[Message]:
        """Все сообщения всех пользователей (любые роли) — для поиска по чатам."""
        out: list[Message] = []
        for msgs in self._store.values():
            out.extend(msgs)
        return out


class Memory:
    """Общая память пар «название — значение» (строки) на всех пользователей.

    Загружается из SQLite при старте бота, дальше живёт только в оперативной
    памяти. db_path игнорируется после загрузки (оставлен для совместимости).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pairs: list[tuple[str, str]] = []
        self._load()

    def _load(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                cur = conn.execute("SELECT name, value FROM memory ORDER BY id ASC")
                self._pairs = [(r[0], r[1]) for r in cur.fetchall()]
            finally:
                conn.close()
        except sqlite3.OperationalError:
            # таблицы ещё нет — начинаем с пустой памяти
            self._pairs = []

    def add(self, name: str, value: str) -> None:
        self._pairs.append((name, value))

    def get_all(self, limit: int = 100) -> list[tuple[str, str]]:
        return list(self._pairs[:limit])

    def search(self, query: str, limit: int = 20) -> list[tuple[str, str]]:
        q = query.lower()
        return [p for p in self._pairs if q in p[0].lower() or q in p[1].lower()][:limit]

    def delete(self, name: str) -> bool:
        for i, (n, _) in enumerate(self._pairs):
            if n == name:
                del self._pairs[i]
                return True
        return False
