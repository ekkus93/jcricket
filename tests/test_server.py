import asyncio
import itertools
import logging
import sqlite3
from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from second_brain_mcp.auth import LocalAuthMiddleware
from second_brain_mcp.config import AppConfig, Limits, ModelProfile
from second_brain_mcp.server import create_app
from second_brain_mcp.store import ModelSelection


def _configured_app(
    tmp_path: Path,
    limits: Limits | None = None,
    trusted_hosts: list[str] | None = None,
) -> Starlette:
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
        trusted_hosts=trusted_hosts or [],
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
    assert ask.parameters["properties"]["mode"]["enum"] == [
        "discuss",
        "brainstorm",
        "critic",
        "review",
        "solve",
    ]
    profile_schema = ask.parameters["properties"]["model_profile"]
    profile_enum = profile_schema.get("enum") or profile_schema["anyOf"][0]["enum"]
    assert profile_enum == ["4k", "32k", "128k", "256k"]


@pytest.mark.parametrize(
    "exception",
    [
        sqlite3.OperationalError("private SQL marker"),
        AttributeError("private parser marker"),
    ],
)
def test_ask_handler_sanitizes_unexpected_exceptions(
    tmp_path: Path, monkeypatch, exception: Exception
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    app = _configured_app(tmp_path)

    async def fail_ask(*args, **kwargs):
        raise exception

    app.state.service.ask = fail_ask
    headers = {
        "Authorization": "Bearer " + "c" * 32,
        "Host": "127.0.0.1",
        "Origin": "http://127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ask_second_brain",
                    "arguments": {"question": "private prompt marker"},
                },
            },
            headers=headers,
        )
    result = response.json()["result"]
    assert result["isError"] is True
    content = " ".join(part.get("text", "") for part in result["content"])
    # FastMCP adds its standard tool-name prefix around the handler error.
    assert content.endswith("internal_error: the server could not complete the request")
    assert "private SQL marker" not in content
    assert "private parser marker" not in content


def test_list_models_handler_sanitizes_unexpected_exceptions(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    app = _configured_app(tmp_path)

    async def fail_models():
        raise AttributeError("private inventory marker")

    app.state.ollama.models = fail_models
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "list_models", "arguments": {}},
            },
            headers={
                "Authorization": "Bearer " + "c" * 32,
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
                "Accept": "application/json, text/event-stream",
            },
        )
    result = response.json()["result"]
    content = " ".join(part.get("text", "") for part in result["content"])
    assert result["isError"] is True
    assert content.endswith("internal_error: the server could not complete the request")
    assert "private inventory marker" not in content


def test_auth_is_required_for_mcp_and_health_is_minimal(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/healthz", headers={"Host": "example.invalid"}).json() == {
            "status": "ok"
        }
        denied = client.post(
            "/mcp",
            json={},
            headers={"Host": "127.0.0.1", "Origin": "http://127.0.0.1"},
        )
        assert denied.status_code == 401
        assert denied.json()["error"] == "authentication required"
        assert len(denied.headers["x-request-id"]) == 32
        forbidden = client.post(
            "/mcp",
            json={},
            headers={"Host": "example.invalid", "Origin": "http://example.invalid"},
        )
        assert forbidden.status_code == 403
        assert len(forbidden.headers["x-request-id"]) == 32


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


@pytest.mark.parametrize(
    "authorization",
    ["Bearer", "Bearer  " + "c" * 32, b"Bearer caf\xe9"],
)
def test_malformed_authorization_headers_return_401(
    tmp_path: Path, monkeypatch, authorization: str
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Authorization": authorization,
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
            },
        )
    assert response.status_code == 401
    assert len(response.headers["x-request-id"]) == 32


def test_bearer_scheme_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Authorization": "bearer " + "c" * 32,
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200, response.text
    assert len(response.headers["x-request-id"]) == 32


def test_request_ids_are_server_generated_for_same_rpc_id(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        client.app.state.ollama.models = _fake_models
        headers = {
            "Authorization": "Bearer " + "c" * 32,
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        }
        request = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/list",
            "params": {},
        }
        first = client.post("/mcp", json=request, headers=headers)
        second = client.post("/mcp", json=request, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_mcp_rejects_mode_outside_published_enum(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(_configured_app(tmp_path)) as client:
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "ask_second_brain",
                    "arguments": {"question": "hello", "mode": "unsafe"},
                },
            },
            headers={
                "Authorization": "Bearer " + "c" * 32,
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True


def test_tool_logs_are_correlatable_and_do_not_contain_content(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "token-marker-" + "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    caplog.set_level(logging.INFO)
    app = _configured_app(tmp_path)

    async def ask(*args, **kwargs):
        return {
            "answer": "answer-marker",
            "conversation_id": "conversation-marker",
            "mode": "discuss",
            "model_profile": "32k",
            "model": "qwen:32k",
            "context_limit_tokens": 32768,
            "history_trimmed": False,
            "usage": {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "elapsed_ms": 10,
            },
        }

    app.state.service.ask = ask
    with TestClient(app) as client:
        client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ask_second_brain",
                    "arguments": {
                        "question": "question-marker",
                        "context": "context-marker",
                    },
                },
            },
            headers={
                "Authorization": "Bearer token-marker-" + "c" * 32,
                "Host": "127.0.0.1",
                "Origin": "http://127.0.0.1",
                "Accept": "application/json, text/event-stream",
            },
        )
    records = "\n".join(record.getMessage() for record in caplog.records)
    for marker in (
        "question-marker",
        "context-marker",
        "answer-marker",
        "token-marker-",
        "conversation-marker",
    ):
        assert marker not in records
    assert "model=qwen:32k" in records
    assert "conversation_id_hash=" in records
    assert "request_id=" in records


def test_fastmcp_settings_ignore_environment_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    monkeypatch.setenv("FASTMCP_DEBUG", "true")
    monkeypatch.setenv("FASTMCP_HOST", "0.0.0.0")
    app = _configured_app(tmp_path)
    settings = app.state.mcp_server.settings
    assert settings.debug is False
    assert settings.host == "127.0.0.1"
    assert settings.streamable_http_path == "/mcp"
    assert settings.stateless_http is True


def test_server_runs_one_worker(app_config, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_MCP_TOKEN", "c" * 32)
    monkeypatch.setenv("CLAUDE_CODE_MCP_TOKEN", "d" * 32)
    captured = {}
    monkeypatch.setattr(
        "second_brain_mcp.server.uvicorn.run", lambda *a, **kw: captured.update(kw)
    )
    from second_brain_mcp.server import run

    run(app_config)
    assert captured["workers"] == 1


def test_configured_trusted_host_is_accepted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    with TestClient(
        _configured_app(tmp_path, trusted_hosts=["brain.example"])
    ) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Authorization": "Bearer " + "c" * 32,
                "Host": "brain.example",
                "Origin": "https://brain.example",
                "Accept": "application/json, text/event-stream",
            },
        )
        rejected = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={
                "Authorization": "Bearer " + "c" * 32,
                "Host": "other.example",
                "Origin": "https://other.example",
            },
        )
    assert response.status_code == 200
    assert rejected.status_code == 403


@pytest.mark.asyncio
async def test_concurrent_tool_calls_keep_principal_ownership(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEST_CODEX_TOKEN", "c" * 32)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    app = _configured_app(tmp_path)
    sequence = itertools.count()

    async def persist(
        principal,
        question,
        context=None,
        conversation_id=None,
        mode="discuss",
        model_profile=None,
        model=None,
    ):
        identifier = f"owned-{next(sequence)}"
        selection = ModelSelection("32k", "qwen:32k", 32768)
        app.state.service.store.record_turn(
            principal,
            identifier,
            selection,
            question,
            context,
            "ok",
            mode,
            new_conversation=True,
        )
        return {
            "answer": "ok",
            "conversation_id": identifier,
            "mode": mode,
            "model_profile": "32k",
            "model": "qwen:32k",
            "context_limit_tokens": 32768,
            "history_trimmed": False,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "elapsed_ms": 1},
        }

    app.state.service.ask = persist
    headers = {
        "codex": {
            "Authorization": "Bearer " + "c" * 32,
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        },
        "claude-code": {
            "Authorization": "Bearer " + "d" * 32,
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        },
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            responses = await asyncio.gather(
                *[
                    client.post(
                        "/mcp",
                        json={
                            "jsonrpc": "2.0",
                            "id": index,
                            "method": "tools/call",
                            "params": {
                                "name": "ask_second_brain",
                                "arguments": {"question": str(index)},
                            },
                        },
                        headers=headers["codex" if index % 2 == 0 else "claude-code"],
                    )
                    for index in range(20)
                ]
            )
    assert all(response.status_code == 200 for response in responses)
    ids = [
        response.json()["result"]["structuredContent"]["conversation_id"]
        for response in responses
    ]
    store = app.state.service.store
    owners = {store.get_any(identifier)["principal"] for identifier in ids}
    assert owners == {"codex", "claude-code"}
    assert all(
        store.get(owner, identifier) is not None
        for owner in owners
        for identifier in ids
        if store.get_any(identifier)["principal"] == owner
    )


@pytest.mark.asyncio
async def test_authorization_token_with_trailing_newline_is_rejected() -> None:
    async def app(scope, receive, send):
        pytest.fail("invalid credentials must not reach the app")

    middleware = LocalAuthMiddleware(app, {"codex": "c" * 32}, host="127.0.0.1")
    messages = []
    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [
            (b"host", b"127.0.0.1"),
            (b"authorization", b"Bearer " + b"c" * 32 + b"\n"),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)
    response_start = next(
        item for item in messages if item["type"] == "http.response.start"
    )
    assert response_start["status"] == 401


async def _fake_models():
    return {"models": [], "default_profile": "32k", "truncated": False}


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


@pytest.mark.asyncio
async def test_authenticated_scope_exposes_principal_in_user() -> None:
    captured = {}

    async def app(scope, receive, send):
        captured["user"] = scope.get("user")

    middleware = LocalAuthMiddleware(app, {"codex": "c" * 32}, host="127.0.0.1")
    scope = {
        "type": "http",
        "path": "/mcp",
        "headers": [
            (b"host", b"127.0.0.1"),
            (b"authorization", b"Bearer " + b"c" * 32),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        pass

    await middleware(scope, receive, send)
    assert captured["user"].username == "codex"
