"""Opt-in end-to-end checks against the configured local Ollama service."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from second_brain_mcp.config import load_config

pytestmark = pytest.mark.live


def _config_path() -> Path:
    if os.environ.get("SECOND_BRAIN_LIVE") != "1":
        pytest.skip("set SECOND_BRAIN_LIVE=1 to run local service checks")
    value = os.environ.get("SECOND_BRAIN_CONFIG")
    if not value:
        pytest.skip("SECOND_BRAIN_CONFIG must point to a private config.yaml")
    path = Path(value).expanduser()
    if not path.is_file():
        pytest.skip("SECOND_BRAIN_CONFIG does not exist")
    return path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_until_ready(process: subprocess.Popen, base_url: str) -> None:
    deadline = time.monotonic() + 30
    async with httpx.AsyncClient(timeout=1) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("live MCP server exited during startup")
            try:
                if (await client.get(base_url + "/healthz")).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise TimeoutError("live MCP server did not become ready")


async def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        await asyncio.to_thread(process.wait, timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        await asyncio.to_thread(process.wait, timeout=10)


@pytest.mark.asyncio
async def test_live_ollama_mcp_and_restart_persistence(tmp_path: Path) -> None:
    source_config = load_config(_config_path())
    credentials = source_config.credentials()
    for principal in ("codex", "claude-code"):
        assert principal in credentials
    port = _free_port()
    live_config = source_config.model_dump(mode="json")
    live_config["database_path"] = str(tmp_path / "live.sqlite3")
    live_config["port"] = port
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(live_config), encoding="utf-8")
    base_url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "second_brain_mcp.cli",
        "--config",
        str(config_path),
        "serve",
    ]
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    async def open_session(token: str):
        http_client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(360),
        )
        transport = streamable_http_client(base_url + "/mcp", http_client=http_client)
        streams = await transport.__aenter__()
        session = ClientSession(streams[0], streams[1])
        await session.__aenter__()
        await session.initialize()
        return http_client, transport, session

    async def close_session(http_client, transport, session):
        await session.__aexit__(None, None, None)
        await transport.__aexit__(None, None, None)
        await http_client.aclose()

    try:
        await _wait_until_ready(process, base_url)
        http_client, transport, session = await open_session(credentials["codex"])
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == {
            "ask_second_brain",
            "list_models",
        }
        ask_tool = next(tool for tool in tools.tools if tool.name == "ask_second_brain")
        mode_schema = ask_tool.inputSchema["properties"]["mode"]
        assert mode_schema["enum"] == [
            "discuss",
            "brainstorm",
            "critic",
            "review",
            "solve",
        ]
        inventory_result = await session.call_tool("list_models", {})
        assert not inventory_result.isError
        inventory = inventory_result.structuredContent
        assert inventory is not None
        model_entries = {item["name"]: item for item in inventory["models"]}
        for profile in source_config.profiles.values():
            assert profile.model in model_entries
            assert model_entries[profile.model]["selectable"] is True
        assert "truncated" in inventory

        invalid = await session.call_tool(
            "ask_second_brain", {"question": "", "mode": "discuss"}
        )
        assert invalid.isError
        error_text = " ".join(
            item.text for item in invalid.content if hasattr(item, "text")
        )
        assert error_text.endswith("invalid_input: question must not be empty")

        first = await session.call_tool(
            "ask_second_brain",
            {
                "question": "Live check: give a one sentence greeting.",
                "model_profile": "32k",
            },
        )
        assert not first.isError
        first_data = first.structuredContent
        assert first_data["usage"] is not None
        conversation_id = first_data["conversation_id"]
        second = await session.call_tool(
            "ask_second_brain",
            {
                "question": "Continue with one short follow-up.",
                "conversation_id": conversation_id,
            },
        )
        assert not second.isError
        await close_session(http_client, transport, session)

        other_http_client, other_transport, other_session = await open_session(
            credentials["claude-code"]
        )
        denied = await other_session.call_tool(
            "ask_second_brain",
            {"question": "cross-principal check", "conversation_id": conversation_id},
        )
        assert denied.isError
        denied_text = " ".join(
            item.text for item in denied.content if hasattr(item, "text")
        )
        assert "conversation_unavailable" in denied_text
        await close_session(other_http_client, other_transport, other_session)

        await _stop(process)
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).resolve().parents[2],
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await _wait_until_ready(process, base_url)
        http_client, transport, session = await open_session(credentials["codex"])
        third = await session.call_tool(
            "ask_second_brain",
            {"question": "Continue after restart.", "conversation_id": conversation_id},
        )
        assert not third.isError
        await close_session(http_client, transport, session)
    finally:
        await _stop(process)
