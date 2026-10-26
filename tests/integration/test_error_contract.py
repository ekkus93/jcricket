import logging
import sqlite3
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.server import create_app

TOKEN = "c" * 32
INTERNAL = "internal_error: the server could not complete the request"


def _app(tmp_path: Path, monkeypatch) -> Starlette:
    monkeypatch.setenv("TEST_CODEX_TOKEN", TOKEN)
    monkeypatch.setenv("TEST_CLAUDE_TOKEN", "d" * 32)
    return create_app(
        AppConfig(
            # Port 9 on loopback refuses connections, simulating an Ollama outage.
            ollama_base_url="http://127.0.0.1:9",
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


def _call(app: Starlette, tool: str, arguments: dict) -> dict:
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    with TestClient(app) as client:
        response = client.post("/mcp", json=request, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def _assert_error(result: dict, text: str) -> None:
    assert result["isError"] is True
    assert result["content"] == [{"type": "text", "text": text}]
    assert result.get("structuredContent") is None


def test_service_error_text_is_exactly_code_and_message(
    tmp_path: Path, monkeypatch
) -> None:
    result = _call(_app(tmp_path, monkeypatch), "ask_second_brain", {"question": "   "})
    _assert_error(result, "invalid_input: question must not be empty")


def test_argument_validation_error_names_field_without_value(
    tmp_path: Path, monkeypatch
) -> None:
    result = _call(
        _app(tmp_path, monkeypatch),
        "ask_second_brain",
        {"question": "hi", "mode": "nope"},
    )
    _assert_error(result, "invalid_input: invalid value for mode")
    assert "nope" not in str(result)


@pytest.mark.parametrize(
    "error",
    [sqlite3.OperationalError("secret-marker"), AttributeError("secret-marker")],
)
def test_unexpected_exceptions_return_exact_internal_error(
    tmp_path: Path, monkeypatch, error: Exception
) -> None:
    app = _app(tmp_path, monkeypatch)

    async def fail(*args, **kwargs):
        raise error

    app.state.service.ask = fail
    result = _call(app, "ask_second_brain", {"question": "hello"})
    _assert_error(result, INTERNAL)
    assert "secret-marker" not in str(result)


def test_response_validation_failure_returns_internal_error(
    tmp_path: Path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch)

    async def malformed(*args, **kwargs):
        return {
            "answer": "secret-marker",
            "conversation_id": "id",
            "mode": "discuss",
            "model_profile": "32k",
            "model": "medium",
            "context_limit_tokens": "not-a-number",
            "history_trimmed": False,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "elapsed_ms": 1},
        }

    app.state.service.ask = malformed
    result = _call(app, "ask_second_brain", {"question": "hello"})
    _assert_error(result, INTERNAL)
    assert "secret-marker" not in str(result)


def test_unknown_tool_is_invalid_input(tmp_path: Path, monkeypatch) -> None:
    result = _call(_app(tmp_path, monkeypatch), "delete_everything", {})
    _assert_error(result, "invalid_input: unknown tool")


def test_list_models_outage_returns_exact_error(tmp_path: Path, monkeypatch) -> None:
    result = _call(_app(tmp_path, monkeypatch), "list_models", {})
    _assert_error(
        result, "ollama_unavailable: Ollama is unavailable or rejected the request"
    )


def _category_levels(caplog) -> dict[str, int]:
    return {
        record.getMessage().split("category=")[1].split()[0]: record.levelno
        for record in caplog.records
        if record.name == "second_brain_mcp.server"
        and "status=error category=" in record.getMessage()
    }


def test_error_log_level_follows_category(tmp_path: Path, monkeypatch, caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="second_brain_mcp")
    app = _app(tmp_path, monkeypatch)
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }

    def call(client: TestClient, tool: str, arguments: dict) -> None:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }
        assert client.post("/mcp", json=request, headers=headers).status_code == 200

    async def fail(*args, **kwargs):
        raise RuntimeError("boom")

    with TestClient(app) as client:
        call(client, "ask_second_brain", {"question": "   "})
        call(client, "list_models", {})
        app.state.service.ask = fail
        call(client, "ask_second_brain", {"question": "hello"})
    levels = _category_levels(caplog)
    assert levels["invalid_input"] == logging.INFO
    assert levels["ollama_unavailable"] == logging.WARNING
    assert levels["internal_error"] == logging.ERROR


# R3-23 / R3-24: fallback log fields and unknown-tool detection

R44_FIELDS = (
    "request_id",
    "rpc_id",
    "tool",
    "principal",
    "status",
    "category",
    "mode",
    "profile",
    "model",
    "context_limit_tokens",
    "history_trimmed",
    "elapsed_ms",
    "prompt_tokens",
    "completion_tokens",
    "conversation_id_hash",
)


def _rpc(client: TestClient, rpc_id: int, tool: str, arguments: dict) -> dict:
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }
    request = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    response = client.post("/mcp", json=request, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_fallback_error_logs_carry_every_r44_field(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="second_brain_mcp")
    with TestClient(_app(tmp_path, monkeypatch)) as client:
        _rpc(client, 4242, "ask_second_brain", {"question": "hi", "mode": "nope"})
        _rpc(client, 4343, "delete_everything", {})
    records = {
        rpc_id: next(
            record.getMessage()
            for record in caplog.records
            if f"rpc_id={rpc_id} " in record.getMessage()
            and "status=error" in record.getMessage()
        )
        for rpc_id in (4242, 4343)
    }
    for rpc_id, line in records.items():
        for field in R44_FIELDS:
            assert line.count(f"{field}=") == 1, (rpc_id, field, line)
        assert "principal=codex " in line
        assert "category=invalid_input" in line
    assert "tool=ask_second_brain" in records[4242]
    assert "tool=delete_everything" in records[4343]


def test_unknown_tool_is_not_detected_from_sdk_message_text(
    tmp_path: Path, monkeypatch
) -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError

    async def sdk_wording(self, name, arguments):
        raise ToolError("Unknown tool: delete_everything")

    monkeypatch.setattr(FastMCP, "call_tool", sdk_wording)
    with TestClient(_app(tmp_path, monkeypatch)) as client:
        result = _rpc(client, 7, "list_models", {})
    _assert_error(result, INTERNAL)


@pytest.mark.asyncio
async def test_call_tool_outside_a_request_logs_placeholder_ids(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="second_brain_mcp")
    mcp = _app(tmp_path, monkeypatch).state.mcp_server

    result = await mcp.call_tool("delete_everything", {})

    assert result.isError is True
    assert result.content[0].text == "invalid_input: unknown tool"
    [line] = [
        record.getMessage()
        for record in caplog.records
        if "status=error" in record.getMessage()
    ]
    assert "rpc_id=- " in line
    assert "principal=- " in line
    assert "tool=delete_everything " in line
