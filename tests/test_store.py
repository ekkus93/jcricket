import sqlite3
import stat
from pathlib import Path

from second_brain_mcp.store import ConversationStore


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
