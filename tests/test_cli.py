from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from second_brain_mcp.cli import _conversations
from second_brain_mcp.store import ConversationStore


def test_purge_requires_confirmation_and_confirmation_flag(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    store = ConversationStore(tmp_path / "db.sqlite3")
    conversation = store.create("codex", "32k", "tag", 32768)
    cutoff_date = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    with store.connect() as db:
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (cutoff_date, conversation.id),
        )
    args = Namespace(
        action="purge",
        principal=None,
        conversation_id=None,
        older_than=1,
        yes=False,
    )
    monkeypatch.setattr("builtins.input", lambda _: "n")
    _conversations(store.path, args)
    assert len(store.list()) == 1
    args.yes = True
    _conversations(store.path, args)
    assert "Deleted 1 conversations" in capsys.readouterr().out
    assert store.list() == []


def test_delete_requires_an_existing_id(tmp_path: Path) -> None:
    args = Namespace(
        action="delete",
        principal=None,
        conversation_id="missing",
        older_than=None,
        yes=True,
    )
    with pytest.raises(SystemExit, match="conversation not found"):
        _conversations(tmp_path / "db.sqlite3", args)
