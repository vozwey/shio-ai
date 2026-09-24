import json
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
        self._store: list[Message] = []

    def add(self, user_id: int, role: str, content: str) -> None:
        self._store.append(
            Message(role=role, content=content, created_at=datetime.now(timezone.utc))
        )
        self._trim()

    def _trim(self) -> None:
        while len(self._store) > self.context_size:
            for i, m in enumerate(self._store):
                if m.role == "system":
                    del self._store[i]
                    break
            else:
                del self._store[0]

    def add_system_prompt(self, prompt: str) -> None:
        self._store.append(
            Message(role="system", content=prompt, created_at=datetime.now(timezone.utc))
        )

    def get_context(self, user_id: int) -> list[Message]:
        return list(self._store)

    def all_messages(self) -> list[Message]:
        return list(self._store)

    def clear(self, id: int) -> None:
        self._store.clear()


@dataclass
class MemoryPair:
    id: int
    name: str
    value: str
    tags: list[str] = field(default_factory=list)
    user_id: int | None = None


class Memory:

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pairs: list[MemoryPair] = []
        self._init_db()
        self._load()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS memory ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, "
                "value TEXT NOT NULL, "
                "tags TEXT NOT NULL DEFAULT '[]', "
                "user_id INTEGER)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_tags ON memory (tags)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_user_id ON memory (user_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT id, name, value, tags, user_id FROM memory ORDER BY id ASC"
            )
            self._pairs = [
                MemoryPair(
                    id=r[0],
                    name=r[1],
                    value=r[2],
                    tags=json.loads(r[3] or "[]"),
                    user_id=r[4],
                )
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def add(
        self,
        name: str,
        value: str,
        tags: list[str] | None = None,
        user_id: int | None = None,
    ) -> None:
        tags = tags or []
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO memory (name, value, tags, user_id) VALUES (?, ?, ?, ?)",
                (name, value, json.dumps(tags, ensure_ascii=False), user_id),
            )
            conn.commit()
        finally:
            conn.close()
        self._pairs.append(
            MemoryPair(
                id=self._pairs[-1].id + 1 if self._pairs else 1,
                name=name,
                value=value,
                tags=tags,
                user_id=user_id,
            )
        )

    def get_all(self, limit: int = 100) -> list[tuple[str, str]]:
        return [(p.name, p.value) for p in self._pairs[:limit]]

    def get_all_full(self, limit: int = 100) -> list[MemoryPair]:
        return list(self._pairs[:limit])

    def get_all_tags(self) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()
        for p in self._pairs:
            for t in p.tags:
                if t not in seen:
                    seen.add(t)
                    tags.append(t)
        return tags

    def get_by_tag(self, tag: str, limit: int = 50) -> list[MemoryPair]:
        q = tag.lower()
        return [p for p in self._pairs if any(q in t.lower() for t in p.tags)][:limit]

    def search(
        self, query: str, tag: str | None = None, limit: int = 20
    ) -> list[MemoryPair]:
        q = query.lower()
        pairs = self._pairs
        if tag:
            t = tag.lower()
            pairs = [p for p in pairs if any(t in x.lower() for x in p.tags)]
        return [
            p
            for p in pairs
            if q in p.name.lower()
            or q in p.value.lower()
            or any(q in x.lower() for x in p.tags)
        ][:limit]

    def delete(self, name: str) -> bool:
        pair = next((p for p in self._pairs if p.name == name), None)
        if pair is None:
            return False
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM memory WHERE id = ?", (pair.id,))
            conn.commit()
        finally:
            conn.close()
        self._pairs = [p for p in self._pairs if p.id != pair.id]
        return True
