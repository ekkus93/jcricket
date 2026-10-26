from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.server import create_app

CODEX_TOKEN = "c" * 32
CLAUDE_TOKEN = "d" * 32


def _app(tmp_path: Path, monkeypatch) -> Starlette:
    monkeypatch.setenv("TEST_CODEX_TOKEN", CODEX_TOKEN)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", CLAUDE_TOKEN)
    return create_app(
        AppConfig(
            database_path=tmp_path / "db.sqlite3",
            profiles={
                "4k": ModelProfile(model="small", context_tokens=4096),
                "32k": ModelProfile(model="medium", context_tokens=32768),
                "128k": ModelProfile(model="large", context_tokens=131072),
                "256k": ModelProfile(model="huge", context_tokens=262144),
            },
            token_env={"codex": "TEST_CODEX_TOKEN", "claude-code": "TEST_CLAUDE_TOKEN"},
        )
    )


def _call(tool: str, arguments: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [("ask_second_brain", {"question": "hello"}), ("list_models", {})],
)
@pytest.mark.parametrize(
    "authorization", [None, "Bearer " + "x" * 32, "Basic " + CODEX_TOKEN]
)
def test_unauthenticated_calls_to_each_tool_never_reach_backend(
    tmp_path: Path, monkeypatch, tool: str, arguments: dict, authorization: str | None
) -> None:
    app = _app(tmp_path, monkeypatch)
    calls: list[str] = []

    async def record_ask(*args, **kwargs):
        calls.append("ask")
        raise AssertionError("service must not be called")

    async def record_models():
        calls.append("models")
        raise AssertionError("ollama must not be called")

    app.state.service.ask = record_ask
    app.state.ollama.models = record_models
    headers = {
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }
    if authorization:
        headers["Authorization"] = authorization
    with TestClient(app) as client:
        response = client.post("/mcp", json=_call(tool, arguments), headers=headers)
    assert response.status_code == 401
    assert calls == []


def test_forged_identity_in_arguments_and_headers_is_ignored(
    tmp_path: Path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)
    seen: list[str] = []

    async def record_ask(principal, *args, **kwargs):
        seen.append(principal)
        raise AssertionError("stop after recording the principal")

    app.state.service.ask = record_ask
    headers = {
        "Authorization": "Bearer " + CODEX_TOKEN,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
        "X-Forwarded-User": "claude-code",
        "X-Principal": "claude-code",
    }
    arguments = {
        "question": "whose conversation is this?",
        "principal": "claude-code",
        "client_id": "claude-code",
        "owner": "claude-code",
    }
    with TestClient(app) as client:
        response = client.post(
            "/mcp", json=_call("ask_second_brain", arguments), headers=headers
        )
    assert response.status_code == 200
    assert seen == ["codex"]
