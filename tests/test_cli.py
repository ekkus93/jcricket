import json
import stat
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from second_brain_mcp.cli import _conversations
from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.store import ConversationStore, ModelSelection


def _config(path: Path, retention_days: int | None = 30) -> AppConfig:
    return AppConfig(
        database_path=path,
        retention_days=retention_days,
        profiles={
            name: ModelProfile(model=f"tag:{name}", context_tokens=size)
            for name, size in {
                "4k": 4096,
                "32k": 32768,
                "128k": 131072,
                "256k": 262144,
            }.items()
        },
    )


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
    with pytest.raises(SystemExit, match="Cancelled"):
        _conversations(store.path, args)
    assert len(store.list()) == 1
    args.yes = True
    _conversations(store.path, args)
    assert "Deleted 1 conversations" in capsys.readouterr().out
    assert store.list() == []


def test_purge_uses_configured_retention(tmp_path: Path, capsys) -> None:
    config = _config(tmp_path / "db.sqlite3", retention_days=7)
    store = ConversationStore(config.database_path)
    conversation = store.create("codex", "32k", "tag", 32768)
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    with store.connect() as db:
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (old, conversation.id),
        )
    _conversations(
        config,
        Namespace(action="purge", older_than=None, yes=True),
    )
    assert "Deleted 1" in capsys.readouterr().out
    assert store.list() == []


def test_export_creates_private_file_and_refuses_overwrite(tmp_path: Path) -> None:
    config = _config(tmp_path / "db.sqlite3")
    store = ConversationStore(config.database_path)
    selection = ModelSelection("32k", "tag:32k", 32768)
    conversation_id = "conversation-export"
    store.record_turn(
        "codex",
        conversation_id,
        selection,
        "question",
        None,
        "answer",
        "discuss",
        new_conversation=True,
    )
    output = tmp_path / "export.json"
    _conversations(
        config,
        Namespace(
            action="export",
            conversation_id=conversation_id,
            principal=None,
            output=output,
        ),
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    exported = json.loads(output.read_text())
    assert exported[0]["conversation"]["principal"] == "codex"
    assert exported[0]["turns"][0]["content"] == "question"
    with pytest.raises(FileExistsError):
        _conversations(
            config,
            Namespace(
                action="export",
                conversation_id=conversation_id,
                principal=None,
                output=output,
            ),
        )


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
