import json
import os
import stat
import subprocess
import sys
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from second_brain_mcp.cli import _conversations, _verify_context_windows, main
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
    make_conversation, tmp_path: Path, monkeypatch, capsys
) -> None:
    store = ConversationStore(tmp_path / "db.sqlite3")
    conversation = make_conversation(store)
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
        _conversations(store.path, None, args)
    assert len(store.list()) == 1
    args.yes = True
    _conversations(store.path, None, args)
    assert "Deleted 1 conversations" in capsys.readouterr().out
    assert store.list() == []


def test_purge_uses_configured_retention(
    make_conversation, tmp_path: Path, capsys
) -> None:
    config = _config(tmp_path / "db.sqlite3", retention_days=7)
    store = ConversationStore(config.database_path)
    conversation = make_conversation(store)
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    with store.connect() as db:
        db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (old, conversation.id),
        )
    _conversations(
        config.database_path,
        config.retention_days,
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
        config.database_path,
        config.retention_days,
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
            config.database_path,
            config.retention_days,
            Namespace(
                action="export",
                conversation_id=conversation_id,
                principal=None,
                output=output,
            ),
        )


def test_list_filter_show_unknown_and_delete_paths(tmp_path: Path, capsys) -> None:
    config = _config(tmp_path / "db.sqlite3")
    store = ConversationStore(config.database_path)
    selected = ModelSelection("32k", "tag:32k", 32768)
    codex_id = "codex-conversation"
    claude_id = "claude-conversation"
    for principal, identifier in (("codex", codex_id), ("claude-code", claude_id)):
        store.record_turn(
            principal,
            identifier,
            selected,
            "question",
            None,
            "answer",
            "discuss",
            new_conversation=True,
        )

    _conversations(
        config.database_path,
        config.retention_days,
        Namespace(action="list", principal="codex"),
    )
    listed = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in listed] == [codex_id]
    _conversations(
        config.database_path,
        config.retention_days,
        Namespace(action="show", conversation_id=codex_id),
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["conversation"]["principal"] == "codex"
    assert len(shown["turns"]) == 2
    with pytest.raises(SystemExit, match="conversation not found"):
        _conversations(
            config.database_path,
            config.retention_days,
            Namespace(action="show", conversation_id="missing"),
        )
    with pytest.raises(SystemExit, match="Cancelled"):
        _conversations(
            config.database_path,
            config.retention_days,
            Namespace(action="delete", conversation_id=codex_id, yes=False),
        )
    _conversations(
        config.database_path,
        config.retention_days,
        Namespace(action="delete", conversation_id=codex_id, yes=True),
    )
    assert store.get_any(codex_id) is None
    assert store.get_any(claude_id) is not None


def test_eof_at_delete_confirmation_is_cancelled(
    make_conversation, tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path / "db.sqlite3")
    store = ConversationStore(config.database_path)
    conversation = make_conversation(store)

    class InteractiveInput:
        def isatty(self):
            return True

    monkeypatch.setattr("second_brain_mcp.cli.sys.stdin", InteractiveInput())
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: (_ for _ in ()).throw(EOFError())
    )
    with pytest.raises(SystemExit, match="Cancelled"):
        _conversations(
            config.database_path,
            config.retention_days,
            Namespace(action="delete", conversation_id=conversation.id, yes=False),
        )
    assert store.get_any(conversation.id) is not None


def test_delete_requires_an_existing_id(tmp_path: Path) -> None:
    args = Namespace(
        action="delete",
        principal=None,
        conversation_id="missing",
        older_than=None,
        yes=True,
    )
    with pytest.raises(SystemExit, match="conversation not found"):
        _conversations(tmp_path / "db.sqlite3", None, args)


VALID_PROFILES = """profiles:
  4k: {model: a, context_tokens: 4096}
  32k: {model: b, context_tokens: 32768}
  128k: {model: c, context_tokens: 131072}
  256k: {model: d, context_tokens: 262144}
token_env: {codex: CLI_CODEX_TOKEN, claude-code: CLI_CLAUDE_TOKEN}
"""


def _write_invalid_config(tmp_path: Path, extra: str) -> Path:
    config_path = tmp_path / "config.yaml"
    body = VALID_PROFILES
    if extra.startswith("token_env:"):
        body = body.replace(
            "token_env: {codex: CLI_CODEX_TOKEN, claude-code: CLI_CLAUDE_TOKEN}\n", ""
        )
    config_path.write_text(body + extra, encoding="utf-8")
    return config_path


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ("log_level: LOUD\n", "log_level must be"),
        ("allowed_models: {x: 1024}\n", "completion_tokens must be less than"),
        ("allowed_models: {x: 2400}\n", "leaves too little prompt budget"),
        ("allowed_models: {b: 8192}\n", "different allowed-model budget"),
        ("limits: {inventory_cache_seconds: 301}\n", "inventory_cache_seconds"),
        (
            "token_env: {codex: bad-name, claude-code: CLI_CLAUDE_TOKEN}\n",
            "token_env values must be environment variable names",
        ),
        (
            "allowed_models: {REPLACE_WITH_TAG: 8192}\n",
            "model tag placeholders must be replaced",
        ),
        ("", "missing environment variables for configured principals"),
    ],
)
def test_check_config_reports_errors_without_traceback(
    tmp_path: Path, monkeypatch, capsys, extra: str, message: str
) -> None:
    config_path = _write_invalid_config(tmp_path, extra)
    monkeypatch.delenv("CLI_CODEX_TOKEN", raising=False)
    monkeypatch.delenv("CLI_CLAUDE_TOKEN", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["second-brain", "--config", str(config_path), "check-config"]
    )
    # In-process: main() ends in SystemExit(1) and nothing else escapes it, so
    # there is no traceback; the entry-point test below checks a real process.
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("second-brain: ")
    assert message in err


def test_check_config_entry_point_exits_1_without_traceback(tmp_path: Path) -> None:
    """The one subprocess test: the console entry point really runs as a program."""
    config_path = _write_invalid_config(tmp_path, "log_level: LOUD\n")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CLI_CODEX_TOKEN", "CLI_CLAUDE_TOKEN"}
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "second_brain_mcp.cli",
            "--config",
            str(config_path),
            "check-config",
        ],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 1
    assert "log_level must be" in result.stderr
    assert "Traceback" not in result.stderr


def _unreachable_config(tmp_path: Path) -> AppConfig:
    return _config(tmp_path / "db.sqlite3").model_copy(
        update={"ollama_base_url": "http://127.0.0.1:9"}
    )


def test_check_config_fails_when_context_windows_cannot_be_verified(
    tmp_path: Path, capsys
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _verify_context_windows(_unreachable_config(tmp_path), required=True)
    assert exc_info.value.code == 1
    assert capsys.readouterr().err == (
        "second-brain: could not verify model context windows: "
        "ollama_unavailable: Ollama is unavailable or rejected the request\n"
    )


def test_serve_warns_and_continues_when_context_windows_cannot_be_verified(
    tmp_path: Path, capsys
) -> None:
    _verify_context_windows(_unreachable_config(tmp_path), required=False)
    assert capsys.readouterr().err == (
        "second-brain: warning: could not verify model context windows: "
        "ollama_unavailable: Ollama is unavailable or rejected the request\n"
    )


def test_context_window_errors_and_warnings_are_reported(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from second_brain_mcp.ollama import ContextWindowReport

    async def report(config):
        return ContextWindowReport(["first error", "second error"], ["a warning"])

    monkeypatch.setattr("second_brain_mcp.cli.verify_context_windows", report)
    with pytest.raises(SystemExit) as exc_info:
        _verify_context_windows(_config(tmp_path / "db.sqlite3"), required=False)
    assert exc_info.value.code == 1
    assert capsys.readouterr().err == (
        "second-brain: warning: a warning\n"
        "second-brain: first error\n"
        "second-brain: second error\n"
    )
