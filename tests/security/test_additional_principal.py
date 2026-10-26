"""A configured third principal (such as ``chatgpt``) is authenticated and isolated."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.server import create_app
from second_brain_mcp.store import ModelSelection

TOKENS = {
    "codex": "c" * 32,
    "claude-code": "d" * 32,
    "chatgpt": "e" * 32,
}


def _app(tmp_path: Path, monkeypatch):
    for principal, token in TOKENS.items():
        monkeypatch.setenv(f"{principal.upper().replace('-', '_')}_TEST_TOKEN", token)
    return create_app(
        AppConfig(
            database_path=tmp_path / "db.sqlite3",
            profiles={
                "4k": ModelProfile(model="small", context_tokens=4096),
                "32k": ModelProfile(model="medium", context_tokens=32768),
                "128k": ModelProfile(model="large", context_tokens=131072),
                "256k": ModelProfile(model="huge", context_tokens=262144),
            },
            token_env={
                principal: f"{principal.upper().replace('-', '_')}_TEST_TOKEN"
                for principal in TOKENS
            },
        )
    )


def _ask_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + token,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }


def _ask_request() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "ask_second_brain", "arguments": {"question": "hi"}},
    }


@pytest.mark.parametrize("principal", sorted(TOKENS))
def test_each_configured_token_maps_to_its_own_principal(
    tmp_path: Path, monkeypatch, principal: str
) -> None:
    app = _app(tmp_path, monkeypatch)
    seen: list[str] = []

    async def record(seen_principal, *args, **kwargs):
        seen.append(seen_principal)
        raise AssertionError("stop after recording the principal")

    app.state.service.ask = record
    with TestClient(app) as client:
        client.post(
            "/mcp", json=_ask_request(), headers=_ask_headers(TOKENS[principal])
        )
    assert seen == [principal]


def test_unconfigured_token_is_rejected(tmp_path: Path, monkeypatch) -> None:
    app = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/mcp", json=_ask_request(), headers=_ask_headers("f" * 32)
        )
    assert response.status_code == 401


def test_third_principal_conversations_are_isolated(
    tmp_path: Path, monkeypatch
) -> None:
    store = _app(tmp_path, monkeypatch).state.service.store
    selection = ModelSelection("32k", "medium", 32768)
    conversation_id = store.record_turn(
        "chatgpt", None, selection, "q", None, "a", "discuss", new_conversation=True
    )
    assert store.get("chatgpt", conversation_id) is not None
    assert store.get("codex", conversation_id) is None
    assert store.get("claude-code", conversation_id) is None
