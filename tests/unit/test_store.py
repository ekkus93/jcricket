import sqlite3
import stat
import threading
from pathlib import Path

import pytest

from second_brain_mcp.errors import ServiceError
from second_brain_mcp.store import ConversationStore, ModelSelection


def test_new_database_uses_wal_foreign_keys_version_and_restrictive_mode(
    tmp_path: Path,
) -> None:
    path = tmp_path / "private" / "brain.sqlite3"
    store = ConversationStore(path)
    with store.connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_v1_schema_migrates_and_preserves_messages(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            """CREATE TABLE conversations (
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, model_profile TEXT,
                model_tag TEXT NOT NULL, context_limit_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, context_text TEXT,
                mode TEXT, created_at TEXT NOT NULL);
            INSERT INTO conversations
                VALUES ('old-id','codex','32k','tag',32768,'t','t');
            INSERT INTO messages(conversation_id,role,content,created_at)
                VALUES ('old-id','user','hello','t');
            PRAGMA user_version = 1;"""
        )
    store = ConversationStore(path)
    assert store.history("old-id")[0].content == "hello"
    with store.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_partially_migrated_v1_schema_migrates_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "partial-v1.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            """CREATE TABLE conversations (
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, model_profile TEXT,
                model_tag TEXT NOT NULL, context_limit_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, context_text TEXT,
                mode TEXT, created_at TEXT NOT NULL, model_profile TEXT);
            PRAGMA user_version = 1;"""
        )
    ConversationStore(path)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
        assert {"model_profile", "model_tag", "context_limit_tokens"} <= columns
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_migration_failure_rolls_back_version_and_added_columns(
    tmp_path: Path,
) -> None:
    path = tmp_path / "migration-rollback.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            """CREATE TABLE conversations (
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, model_profile TEXT,
                model_tag TEXT NOT NULL, context_limit_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, context_text TEXT,
                mode TEXT, created_at TEXT NOT NULL);
            PRAGMA user_version = 1;"""
        )

    store = ConversationStore.__new__(ConversationStore)
    store.path = path
    store._lock = threading.RLock()
    original_connect = ConversationStore.connect.__get__(store)

    class FailingMigrationConnection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if "ADD COLUMN model_tag" in sql:
                raise sqlite3.OperationalError("injected migration failure")
            return super().execute(sql, parameters)

    def failing_connect():
        connection = sqlite3.connect(
            path, timeout=5, check_same_thread=False, factory=FailingMigrationConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    store.connect = failing_connect
    with pytest.raises(sqlite3.OperationalError, match="injected migration failure"):
        store._initialize()
    store.connect = original_connect
    with store._connection() as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(messages)")}
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert not {"model_profile", "model_tag", "context_limit_tokens"} & columns


def test_complete_turn_stores_model_and_context_metadata(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "db.sqlite3")
    conversation = store.create("codex", "32k", "tag", 32768)
    store.add_turn(
        conversation.id, "question", "facts", "answer", "critic", "32k", "tag", 32768
    )
    turns = store.history(conversation.id)
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].context_text == "facts"
    assert turns[0].model_tag == "tag"
    assert turns[1].context_limit_tokens == 32768


def test_record_turn_creates_and_updates_selection_atomically(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "record.sqlite3")
    selection = ModelSelection("32k", "tag-a", 32768)
    conversation_id = store.record_turn(
        "codex", None, selection, "first", None, "answer", "discuss"
    )
    assert store.get("codex", conversation_id).model_tag == "tag-a"
    updated = ModelSelection("128k", "tag-b", 131072)
    same_id = store.record_turn(
        "codex",
        conversation_id,
        updated,
        "next",
        "context",
        "second answer",
        "critic",
    )
    assert same_id == conversation_id
    assert store.get("codex", conversation_id).model_tag == "tag-b"
    turns = store.history(conversation_id)
    assert [turn.role for turn in turns] == ["user", "assistant", "user", "assistant"]
    assert turns[-2].context_limit_tokens == 131072
    assert turns[-2].mode == "critic"


def test_record_turn_rejects_unknown_and_foreign_ids(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "ownership.sqlite3")
    selection = ModelSelection("32k", "tag", 32768)
    for identifier in ("missing-id", None):
        if identifier is None:
            continue
        with pytest.raises(ServiceError) as exc_info:
            store.record_turn("codex", identifier, selection, "q", None, "a", "discuss")
        assert (
            str(exc_info.value)
            == "conversation_unavailable: conversation is unavailable"
        )
    created = store.record_turn("codex", None, selection, "q", None, "a", "discuss")
    with pytest.raises(ServiceError) as exc_info:
        store.record_turn("claude-code", created, selection, "q", None, "a", "discuss")
    assert (
        str(exc_info.value) == "conversation_unavailable: conversation is unavailable"
    )
    assert len(store.history(created)) == 2


def test_record_turn_rolls_back_new_conversation_on_insert_failure(
    tmp_path: Path,
) -> None:
    class FailingConnection(sqlite3.Connection):
        def executemany(self, sql, parameters, /):
            if "INSERT INTO messages" in sql:
                raise sqlite3.OperationalError("injected failure")
            return super().executemany(sql, parameters)

    store = ConversationStore(tmp_path / "rollback.sqlite3")
    existing_id = store.record_turn(
        "codex",
        None,
        ModelSelection("32k", "old-tag", 32768),
        "original question",
        None,
        "original answer",
        "discuss",
    )

    def failing_connect():
        connection = sqlite3.connect(
            store.path, timeout=5, check_same_thread=False, factory=FailingConnection
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    original_connect = store.connect
    store.connect = failing_connect
    with pytest.raises(sqlite3.OperationalError, match="injected failure"):
        store.record_turn(
            "codex",
            "new-id",
            ModelSelection("32k", "tag", 32768),
            "question",
            None,
            "answer",
            "discuss",
            new_conversation=True,
        )
    store.connect = original_connect
    assert [row["id"] for row in store.list()] == [existing_id]
    store.connect = failing_connect
    with pytest.raises(sqlite3.OperationalError, match="injected failure"):
        store.record_turn(
            "codex",
            existing_id,
            ModelSelection("128k", "new-tag", 131072),
            "question",
            None,
            "answer",
            "critic",
        )
    store.connect = original_connect
    unchanged = store.get("codex", existing_id)
    assert unchanged.model_profile == "32k"
    assert unchanged.model_tag == "old-tag"
    assert unchanged.context_limit_tokens == 32768
    assert len(store.history(existing_id)) == 2


def test_store_closes_every_opened_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConversationStore(tmp_path / "connection-count.sqlite3")
    opened = 0
    closed = 0
    original_connect = sqlite3.connect

    class CountingConnection(sqlite3.Connection):
        def close(self) -> None:
            nonlocal closed
            closed += 1
            super().close()

    def connect(*args, **kwargs):
        nonlocal opened
        opened += 1
        kwargs["factory"] = CountingConnection
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    first = store.create("codex", "32k", "tag", 32768)
    store.get("codex", first.id)
    store.history(first.id)
    store.add_turn(first.id, "q", None, "a", "discuss", "32k", "tag", 32768)
    store.record_turn(
        "codex",
        first.id,
        ModelSelection("32k", "tag", 32768),
        "q2",
        None,
        "a2",
        "discuss",
    )
    store.list()
    store.delete(first.id)
    store.purge(1)
    assert opened == closed


def test_sqlite_write_contention_rolls_back_cleanly(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "contention.sqlite3"
    store = ConversationStore(path)
    original_connect = store.connect

    def short_timeout_connect():
        connection = original_connect()
        connection.execute("PRAGMA busy_timeout = 1")
        return connection

    monkeypatch.setattr(store, "connect", short_timeout_connect)
    blocker = sqlite3.connect(path, timeout=0, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            store.create("codex", "32k", "tag", 32768)
    finally:
        blocker.rollback()
        blocker.close()
    assert store.list() == []
