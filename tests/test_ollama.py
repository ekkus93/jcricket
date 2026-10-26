import json
from typing import Any

import httpx
import pytest

from second_brain_mcp.ollama import OllamaClient, OllamaError


@pytest.mark.asyncio
async def test_chat_request_never_contains_tools(app_config: Any) -> None:
    sent: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(await request.aread()))
        return httpx.Response(200, json={"message": {"content": "answer"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        client = OllamaClient(app_config, http)
        result = await client.chat(
            "qwen:32k", [{"role": "user", "content": "hi"}], 32768
        )
    assert result.answer == "answer"
    assert sent[0]["stream"] is False
    assert sent[0]["think"] is False
    assert "tools" not in sent[0]


@pytest.mark.asyncio
async def test_model_inventory_reports_profiles_and_loaded_status(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    result = await OllamaClient(app_config, mock_ollama).models()
    entries = {item["name"]: item for item in result["models"]}
    assert entries["qwen:32k"]["loaded"] is True
    assert entries["qwen:32k"]["loaded_context_tokens"] == 32768
    assert entries["qwen:32k"]["selectable"] is True
    assert entries["other:tag"]["selectable"] is True
    assert result["default_profile"] == "32k"


@pytest.mark.asyncio
async def test_malformed_chat_response_is_sanitized(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": None}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        with pytest.raises(OllamaError, match="invalid chat response"):
            await OllamaClient(app_config, http).chat("qwen:32k", [], 32768)


@pytest.mark.asyncio
async def test_timeout_is_categorized(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private details")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        with pytest.raises(OllamaError, match="timed out"):
            await OllamaClient(app_config, http).chat("qwen:32k", [], 32768)
