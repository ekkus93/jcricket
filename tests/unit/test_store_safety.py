"""Store guards: newer schemas, purge arguments, and already-migrated columns."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from second_brain_mcp.store import ConversationStore


def test_newer_schema_is_refused_and_left_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE future (value TEXT)")
        db.execute("INSERT INTO future VALUES ('keep me')")
        db.execute("PRAGMA user_version = 3")
        db.commit()
    before = path.read_bytes()

    with pytest.raises(RuntimeError) as exc_info:
        ConversationStore(path)

    assert str(exc_info.value) == (
        "conversation database schema is newer than this application"
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("age", [0, -1])
def test_purge_rejects_non_positive_age(
    tmp_path: Path, make_conversation, age: int
) -> None:
    store = ConversationStore(tmp_path / "db.sqlite3")
    conversation = make_conversation(store)
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    with closing(store.connect()) as db, db:
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (old, conversation.id),
        )

    with pytest.raises(ValueError) as exc_info:
        store.purge(age)

    assert str(exc_info.value) == "older_than_days must be positive"
    assert [row["id"] for row in store.list()] == [conversation.id]


def test_v1_database_with_all_new_columns_only_bumps_version(tmp_path: Path) -> None:
    path = tmp_path / "v1-complete.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            """CREATE TABLE conversations (
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, model_profile TEXT,
                model_tag TEXT NOT NULL, context_limit_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, context_text TEXT,
                mode TEXT, created_at TEXT NOT NULL, model_profile TEXT,
                model_tag TEXT, context_limit_tokens INTEGER);
            PRAGMA user_version = 1;"""
        )
        schema_before = db.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()

    store = ConversationStore(path)

    with closing(store.connect()) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        schema_after = db.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
    assert [tuple(row) for row in schema_after] == [tuple(row) for row in schema_before]
