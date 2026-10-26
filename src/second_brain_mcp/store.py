"""SQLite persistence for principal-isolated conversations."""

from __future__ import annotations

import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import ServiceError


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Conversation:
    id: str
    principal: str
    model_profile: str | None
    model_tag: str
    context_limit_tokens: int


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    context_text: str | None = None
    mode: str | None = None
    model_profile: str | None = None
    model_tag: str | None = None
    context_limit_tokens: int | None = None


@dataclass(frozen=True)
class ModelSelection:
    model_profile: str | None
    model_tag: str
    context_limit_tokens: int
    completion_tokens: int | None = None


class ConversationStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        self._lock = threading.RLock()
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self.connect()
        try:
            yield connection
            if connection.in_transaction:
                connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError(
                    "conversation database schema is newer than this application"
                )
            if version == 0:
                db.execute("PRAGMA journal_mode = WAL")
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    """CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    principal TEXT NOT NULL,
                    model_profile TEXT,
                    model_tag TEXT NOT NULL,
                    context_limit_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
                )
                db.execute(
                    """CREATE INDEX IF NOT EXISTS conversations_principal_updated
                    ON conversations(principal, updated_at DESC);
                    """
                )
                db.execute(
                    """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    context_text TEXT,
                    mode TEXT,
                    created_at TEXT NOT NULL
                )"""
                )
                db.execute(
                    """CREATE INDEX IF NOT EXISTS messages_conversation_id
                    ON messages(conversation_id, id)"""
                )
                db.execute("PRAGMA user_version = 1")
                db.commit()
                version = 1
            if version == 1:
                db.execute("BEGIN IMMEDIATE")
                columns = {
                    row["name"]
                    for row in db.execute("PRAGMA table_info(messages)").fetchall()
                }
                if "model_profile" not in columns:
                    db.execute("ALTER TABLE messages ADD COLUMN model_profile TEXT")
                if "model_tag" not in columns:
                    db.execute("ALTER TABLE messages ADD COLUMN model_tag TEXT")
                if "context_limit_tokens" not in columns:
                    db.execute(
                        "ALTER TABLE messages ADD COLUMN context_limit_tokens INTEGER"
                    )
                db.execute("PRAGMA user_version = 2")
                db.commit()

    def get(self, principal: str, conversation_id: str) -> Conversation | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM conversations WHERE id = ? AND principal = ?",
                (conversation_id, principal),
            ).fetchone()
        return _conversation(row) if row else None

    def get_any(self, conversation_id: str) -> dict[str, Any] | None:
        """Return conversation metadata for an administrative caller."""
        with self._connection() as db:
            row = db.execute(
                "SELECT id, principal, model_profile, model_tag, "
                "context_limit_tokens, created_at, updated_at "
                "FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def history(self, conversation_id: str) -> list[Turn]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT role, content, context_text, mode, model_profile, "
                "model_tag, context_limit_tokens FROM messages "
                "WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [Turn(**dict(row)) for row in rows]

    def record_turn(
        self,
        principal: str,
        conversation_id: str | None,
        selection: ModelSelection,
        question: str,
        context: str | None,
        answer: str,
        mode: str,
        *,
        new_conversation: bool = False,
    ) -> str:
        """Atomically create/update a conversation and append one complete turn."""
        is_new = new_conversation or conversation_id is None
        conversation_id = conversation_id or secrets.token_urlsafe(24)
        now = _now()
        with self._lock, self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not is_new:
                row = db.execute(
                    "SELECT principal FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                if row is None or row["principal"] != principal:
                    raise ServiceError("conversation_unavailable")
                db.execute(
                    "UPDATE conversations SET model_profile = ?, model_tag = ?, "
                    "context_limit_tokens = ?, updated_at = ? WHERE id = ?",
                    (
                        selection.model_profile,
                        selection.model_tag,
                        selection.context_limit_tokens,
                        now,
                        conversation_id,
                    ),
                )
            else:
                db.execute(
                    "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        conversation_id,
                        principal,
                        selection.model_profile,
                        selection.model_tag,
                        selection.context_limit_tokens,
                        now,
                        now,
                    ),
                )
            db.executemany(
                "INSERT INTO messages(conversation_id, role, content, "
                "context_text, mode, model_profile, model_tag, "
                "context_limit_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        conversation_id,
                        "user",
                        question,
                        context,
                        mode,
                        selection.model_profile,
                        selection.model_tag,
                        selection.context_limit_tokens,
                        now,
                    ),
                    (
                        conversation_id,
                        "assistant",
                        answer,
                        None,
                        mode,
                        selection.model_profile,
                        selection.model_tag,
                        selection.context_limit_tokens,
                        now,
                    ),
                ],
            )
            db.commit()
        return conversation_id

    def list(self, principal: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as db:
            if principal:
                rows = db.execute(
                    "SELECT id, principal, model_profile, model_tag, created_at, "
                    "updated_at FROM conversations WHERE principal = ? "
                    "ORDER BY updated_at DESC",
                    (principal,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id, principal, model_profile, model_tag, created_at, "
                    "updated_at FROM conversations ORDER BY updated_at DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def show(self, conversation_id: str) -> list[Turn]:
        return self.history(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        with self._lock, self._connection() as db:
            cursor = db.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
        return cursor.rowcount > 0

    def purge(self, older_than_days: int) -> int:
        if older_than_days < 1:
            raise ValueError("older_than_days must be positive")
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        with self._lock, self._connection() as db:
            cursor = db.execute(
                "DELETE FROM conversations WHERE updated_at < ?", (cutoff,)
            )
        return cursor.rowcount


def _conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(
        row["id"],
        row["principal"],
        row["model_profile"],
        row["model_tag"],
        row["context_limit_tokens"],
    )
