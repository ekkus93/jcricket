from pathlib import Path

from starlette.applications import Starlette
from starlette.testclient import TestClient

from second_brain_mcp.config import AppConfig, Limits, ModelProfile
from second_brain_mcp.server import create_app


def _configured_app(tmp_path: Path, limits: Limits | None = None) -> Starlette:
    config = AppConfig(
        database_path=tmp_path / "db.sqlite3",
        limits=limits or Limits(),
        profiles={
            "4k": ModelProfile(model="small", context_tokens=4096),
            "32k": ModelProfile(model="medium", context_tokens=32768),
            "128k": ModelProfile(model="large", context_tokens=131072),
            "256k": ModelProfile(model="huge", context_tokens=262144),
        },
        token_env={"codex": "TEST_CODEX_TOKEN", "claude-code": "TEST_CLAUDE_TOKEN"},
    )
    return create_app(config)


def test_only_two_mcp_tools_and_expected_arguments(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    app = _configured_app(tmp_path)
    tools = app.state.mcp_server._tool_manager.list_tools()
    assert {tool.name for tool in tools} == {"ask_second_brain", "list_models"}
    ask = next(tool for tool in tools if tool.name == "ask_second_brain")
    assert set(ask.parameters["properties"]) == {
        "question",
        "context",
        "conversation_id",
        "mode",
        "model_profile",
        "model",
    }


def test_auth_is_required_for_mcp_and_health_is_minimal(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        denied = client.post(
            "/mcp",
            json={},
            headers={"Host": "127.0.0.1", "Origin": "http://127.0.0.1"},
        )
        assert denied.status_code == 401
        assert denied.json()["error"] == "authentication required"


def test_authentication_maps_separate_tokens_to_principals(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    with TestClient(_configured_app(tmp_path)) as client:
        response = client.post(
            "/mcp",
            json=initialize,
            headers={
                "Authorization": "Bearer cccccccccccccccccccccccccccccccc",
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["serverInfo"]["name"] == "Second Brain"
        client.app.state.ollama.models = _fake_models
        headers = {
            "Authorization": "Bearer " + "c" * 32,
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        }
        tools = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        assert [tool["name"] for tool in tools.json()["result"]["tools"]] == [
            "ask_second_brain",
            "list_models",
        ]
        result = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_models", "arguments": {}},
            },
            headers=headers,
        )
        assert result.status_code == 200, result.text
        assert result.json()["result"]["structuredContent"]["default_profile"] == "32k"


async def _fake_models():
    return {"models": [], "default_profile": "32k"}


def test_rejects_untrusted_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        response = client.post(
            "/mcp",
            json={},
            headers={
                "Authorization": "Bearer " + "c" * 32,
                "Host": "127.0.0.1",
                "Origin": "https://attacker.invalid",
            },
        )
    assert response.status_code == 403


def test_rate_limit_is_per_principal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path, Limits(requests_per_minute=1))) as client:
        headers = {
            "Authorization": "Bearer " + "c" * 32,
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        }
        first = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            headers=headers,
        )
        assert first.status_code == 200
        second = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=headers,
        )
        assert second.status_code == 429
