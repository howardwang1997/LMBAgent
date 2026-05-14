"""Persistent chat memory store.

SQLite-backed store for conversation history and long-term memory.
Tables:
  - chat_sessions: session metadata
  - chat_messages: individual messages within sessions
  - chat_memory: long-term key-value memory (user preferences, facts, summaries)
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


_DEFAULT_DB_PATH = Path.home() / ".lmbagent" / "chat.db"


class ChatMemory:
    _instance: ChatMemory | None = None

    def __new__(cls, db_path: str | Path | None = None) -> ChatMemory:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | Path | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True

        if db_path is None:
            db_path = _DEFAULT_DB_PATH
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_call_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON chat_messages(session_id, id);

            CREATE TABLE IF NOT EXISTS chat_memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

    def create_session(self, title: str | None = None) -> str:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO chat_sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, title or "New Chat", now, now),
        )
        self._conn.commit()
        return session_id

    def list_sessions(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_messages(self, session_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, created_at FROM chat_messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, tool_calls, tool_call_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, role, content, tool_calls, tool_call_id, now),
        )
        self._conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
        self._conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
        self._conn.commit()

    def update_session_title(self, session_id: str, title: str) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
            (title, now, session_id),
        )
        self._conn.commit()

    def set_memory(self, key: str, value: str) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO chat_memory (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        self._conn.commit()

    def get_memory(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM chat_memory WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def get_all_memory(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM chat_memory").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def clear_memory(self) -> None:
        self._conn.execute("DELETE FROM chat_memory")
        self._conn.commit()

    def clear_all(self) -> None:
        self._conn.executescript(
            "DELETE FROM chat_messages; DELETE FROM chat_sessions; DELETE FROM chat_memory;"
        )
