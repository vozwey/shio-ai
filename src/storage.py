import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Message:
    role: str
    content: str
    created_at: datetime


class DialogMemory:

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
        out: list[Message] = []
        for msgs in self._store.values():
            out.extend(msgs)
        return out


class Memory:

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pairs: list[tuple[str, str]] = []
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, "
                "value TEXT NOT NULL)"
            )
            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("SELECT name, value FROM memory ORDER BY id ASC")
            self._pairs = [(r[0], r[1]) for r in cur.fetchall()]
        finally:
            conn.close()

    def add(self, name: str, value: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("INSERT INTO memory (name, value) VALUES (?, ?)", (name, value))
            conn.commit()
        finally:
            conn.close()
        self._pairs.append((name, value))

    def get_all(self, limit: int = 100) -> list[tuple[str, str]]:
        return list(self._pairs[:limit])

    def search(self, query: str, limit: int = 20) -> list[tuple[str, str]]:
        q = query.lower()
        return [p for p in self._pairs if q in p[0].lower() or q in p[1].lower()][:limit]

    def delete(self, name: str) -> bool:
        if not any(n == name for n, _ in self._pairs):
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM memory WHERE name = ?", (name,))
            conn.commit()
        finally:
            conn.close()
        self._pairs = [(n, v) for n, v in self._pairs if n != name]
        return True
