import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from config import MEMORY_DB_PATH


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime


class Memory:
    """Хранит контекст диалога per-user в SQLite."""

    def __init__(self, db_path: str, context_size: int = 20):
        self.db_path = db_path
        self.context_size = context_size
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id, id)"
            )
            conn.commit()

    def add(self, user_id: int, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (user_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, role, content, datetime.now(timezone.utc).isoformat()),
            )
            # обрезаем хвост, оставляя последние context_size сообщений
            conn.execute(
                """
                DELETE FROM messages
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM messages
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (user_id, user_id, self.context_size),
            )
            conn.commit()

    def get_context(self, user_id: int) -> list[Message]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user_id,),
            ).fetchall()
            return [
                Message(
                    role=r["role"],
                    content=r["content"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
                for r in rows
            ]

    def clear(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
            conn.commit()


class Facts:
    """Долговременные факты и воспоминания о пользователе (SQLite)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_facts_user ON facts(user_id, id)"
            )
            conn.commit()

    def add(self, user_id: int, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO facts (user_id, content, created_at) VALUES (?, ?, ?)",
                (user_id, content, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def search(self, user_id: int, query: str, limit: int = 10) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT content FROM facts
                WHERE user_id = ? AND content LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, f"%{query}%", limit),
            ).fetchall()
            return [r["content"] for r in rows]

    def get_all(self, user_id: int, limit: int = 50) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT content FROM facts
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [r["content"] for r in reversed(rows)]

    def delete(self, user_id: int, fact_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM facts WHERE user_id = ? AND id = ?", (user_id, fact_id)
            )
            conn.commit()
            return cur.rowcount > 0
