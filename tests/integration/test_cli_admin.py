"""Admin CLI paths and in-process dispatch through ``main()``."""

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import second_brain_mcp.server
from second_brain_mcp import cli
from second_brain_mcp.ollama import ContextWindowReport
from second_brain_mcp.prompts import system_prompt
from second_brain_mcp.store import ConversationStore, ModelSelection

CONFIG = """database_path: {database}
profiles:
  4k: {{model: a, context_tokens: 4096}}
  32k: {{model: b, context_tokens: 32768}}
  128k: {{model: c, context_tokens: 131072}}
  256k: {{model: d, context_tokens: 262144}}
token_env: {{codex: ADMIN_CODEX_TOKEN, claude-code: ADMIN_CLAUDE_TOKEN}}
"""


def _args(action: str, **values) -> Namespace:
    defaults = {
        "conversation_id": None,
        "principal": None,
        "older_than": None,
        "yes": False,
        "output": None,
    }
    return Namespace(action=action, **(defaults | values))


def _store_with_two_principals(path: Path) -> tuple[ConversationStore, str, str]:
    store = ConversationStore(path)
    selection = ModelSelection("32k", "b", 32768)
    codex = store.record_turn(
        "codex", None, selection, "q1", None, "a1", "discuss", new_conversation=True
    )
    claude = store.record_turn(
        "claude-code",
        None,
        selection,
        "q2",
        None,
        "a2",
        "discuss",
        new_conversation=True,
    )
    return store, codex, claude


def test_get_any_prints_metadata_or_reports_unknown(tmp_path: Path, capsys) -> None:
    store, codex, _claude = _store_with_two_principals(tmp_path / "db.sqlite3")
    cli._conversations(store.path, _args("get-any", conversation_id=codex))
    metadata = json.loads(capsys.readouterr().out)
    assert (metadata["id"], metadata["principal"]) == (codex, "codex")
    with pytest.raises(SystemExit, match="conversation not found"):
        cli._conversations(store.path, _args("get-any", conversation_id="missing"))


@pytest.mark.parametrize(("principal", "expected"), [(None, 2), ("codex", 1)])
def test_export_all_to_stdout(
    tmp_path: Path, capsys, principal: str | None, expected: int
) -> None:
    store, codex, _claude = _store_with_two_principals(tmp_path / "db.sqlite3")
    cli._conversations(store.path, _args("export", principal=principal))
    records = json.loads(capsys.readouterr().out)
    assert len(records) == expected
    if principal:
        assert records[0]["conversation"]["id"] == codex
        assert [turn["content"] for turn in records[0]["turns"]] == ["q1", "a1"]


def test_export_unknown_id_creates_no_file(tmp_path: Path) -> None:
    store, _codex, _claude = _store_with_two_principals(tmp_path / "db.sqlite3")
    output = tmp_path / "export.json"
    with pytest.raises(SystemExit, match="conversation not found"):
        cli._conversations(
            store.path, _args("export", conversation_id="missing", output=output)
        )
    assert not output.exists()


def test_purge_without_age_or_retention_is_refused(tmp_path: Path) -> None:
    store, _codex, _claude = _store_with_two_principals(tmp_path / "db.sqlite3")
    with pytest.raises(SystemExit) as exc_info:
        cli._conversations(store.path, _args("purge"))
    assert str(exc_info.value) == (
        "purge requires --older-than or configured retention_days"
    )
    assert len(store.list()) == 2


def test_interactive_yes_confirms_delete(tmp_path: Path, monkeypatch) -> None:
    store, codex, claude = _store_with_two_principals(tmp_path / "db.sqlite3")

    class InteractiveInput:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("second_brain_mcp.cli.sys.stdin", InteractiveInput())
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    cli._conversations(store.path, _args("delete", conversation_id=codex))
    assert [row["id"] for row in store.list()] == [claude]


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("ADMIN_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("ADMIN_CLAUDE_TOKEN", "d" * 32)
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG.format(database=tmp_path / "db.sqlite3"), encoding="utf-8")
    return path


def test_main_check_config_reports_valid(
    config_file: Path, monkeypatch, capsys
) -> None:
    async def verified(config):
        return ContextWindowReport([], [])

    monkeypatch.setattr(cli, "verify_context_windows", verified)
    monkeypatch.setattr(
        sys, "argv", ["second-brain", "--config", str(config_file), "check-config"]
    )
    cli.main()
    assert capsys.readouterr().out == "Configuration is valid.\n"


def test_main_dispatches_conversations_list(
    config_file: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["second-brain", "--config", str(config_file), "conversations", "list"],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out) == []


def test_main_serve_runs_server_with_loaded_config(
    config_file: Path, monkeypatch
) -> None:
    started = []

    async def verified(config):
        return ContextWindowReport([], [])

    monkeypatch.setattr(cli, "verify_context_windows", verified)
    monkeypatch.setattr(second_brain_mcp.server, "run", started.append)
    monkeypatch.setattr(
        sys, "argv", ["second-brain", "--config", str(config_file), "serve"]
    )
    cli.main()
    assert len(started) == 1
    assert started[0].database_path == config_file.parent / "db.sqlite3"
    assert started[0].profiles["32k"].model == "b"


def test_system_prompt_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError) as exc_info:
        system_prompt("nope")
    assert str(exc_info.value) == "unsupported mode: nope"
