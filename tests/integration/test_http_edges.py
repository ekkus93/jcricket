"""Unknown paths, the unauthorized safeguard, and the tool-error fallback."""

import logging
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.applications import Starlette
from starlette.testclient import TestClient

from second_brain_mcp.auth import current_principal
from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.errors import SecondBrainError
from second_brain_mcp.server import create_app

TOKEN = "c" * 32


def _app(tmp_path: Path, monkeypatch) -> Starlette:
    monkeypatch.setenv("EDGE_CODEX_TOKEN", TOKEN)
    monkeypatch.setenv("EDGE_CLAUDE_TOKEN", "d" * 32)
    return create_app(
        AppConfig(
            database_path=tmp_path / "db.sqlite3",
            profiles={
                "4k": ModelProfile(model="small", context_tokens=4096),
                "32k": ModelProfile(model="medium", context_tokens=32768),
                "128k": ModelProfile(model="large", context_tokens=131072),
                "256k": ModelProfile(model="huge", context_tokens=262144),
            },
            token_env={"codex": "EDGE_CODEX_TOKEN", "claude-code": "EDGE_CLAUDE_TOKEN"},
        )
    )


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/unknown"), ("POST", "/mcp/extra")]
)
def test_unknown_paths_return_404_with_request_id(
    tmp_path: Path, monkeypatch, method: str, path: str
) -> None:
    with TestClient(_app(tmp_path, monkeypatch)) as client:
        response = client.request(method, path, headers={"Host": "127.0.0.1"})
    assert response.status_code == 404
    assert response.json() == {"error": "not found"}
    assert len(response.headers["x-request-id"]) == 32


def test_current_principal_without_authentication_is_unauthorized() -> None:
    with pytest.raises(SecondBrainError) as exc_info:
        current_principal()
    assert str(exc_info.value) == "unauthorized: authenticated principal required"


def test_unexpected_tool_error_falls_back_to_internal_error(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG, logger="second_brain_mcp")

    async def broken_call_tool(self, name, arguments):
        try:
            raise RuntimeError("secret-marker")
        except RuntimeError as exc:
            raise ToolError("boom") from exc

    monkeypatch.setattr(FastMCP, "call_tool", broken_call_tool)
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_models", "arguments": {}},
    }
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Host": "127.0.0.1",
        "Accept": "application/json, text/event-stream",
    }
    with TestClient(_app(tmp_path, monkeypatch)) as client:
        result = client.post("/mcp", json=request, headers=headers).json()["result"]

    assert result["isError"] is True
    assert result["content"] == [
        {
            "type": "text",
            "text": "internal_error: the server could not complete the request",
        }
    ]
    assert "secret-marker" not in str(result)
    assert "boom" not in str(result)
    assert any(
        record.levelno == logging.ERROR
        and "unexpected_error_type=RuntimeError" in record.getMessage()
        for record in caplog.records
    )
