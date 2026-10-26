import asyncio
import json
from typing import Any

import httpx
import pytest

from second_brain_mcp.ollama import OllamaClient, OllamaError
from second_brain_mcp.schemas import ModelInventory


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
async def test_chat_warnings_use_reported_counts_without_content(
    app_config: Any, caplog
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"content": "private answer marker"},
                "prompt_eval_count": 40000,
                "eval_count": 100,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        await OllamaClient(app_config, http).chat(
            "qwen:32k", [{"role": "user", "content": "private prompt marker"}], 32768
        )
    assert "category=estimate_exceeded" in caplog.text
    assert "category=context_saturated" in caplog.text
    assert "private answer marker" not in caplog.text
    assert "private prompt marker" not in caplog.text


@pytest.mark.asyncio
async def test_model_inventory_reports_profiles_and_loaded_status(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    result = await OllamaClient(app_config, mock_ollama).models()
    ModelInventory.model_validate(result)
    entries = {item["name"]: item for item in result["models"]}
    assert entries["qwen:32k"]["loaded"] is True
    assert entries["qwen:32k"]["loaded_context_tokens"] == 32768
    assert entries["qwen:32k"]["selectable"] is True
    assert entries["other:tag"]["selectable"] is True
    assert result["default_profile"] == "32k"
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_model_inventory_caps_entries_but_pins_selectable_tags(
    app_config: Any,
) -> None:
    app_config.profiles["32k"].model = "model-280"
    app_config.allowed_models["model-299"] = app_config.allowed_models["other:tag"]

    async def handler(request: httpx.Request) -> httpx.Response:
        models = [{"name": f"model-{index}"} for index in range(300)]
        return httpx.Response(200, json={"models": models})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        result = await OllamaClient(app_config, http).models()
    names = [item["name"] for item in result["models"]]
    assert len(names) == 200
    assert "model-280" in names
    assert "model-299" in names
    assert result["truncated"] is True
    ModelInventory.model_validate(result)


@pytest.mark.asyncio
async def test_malformed_chat_response_is_sanitized(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": None}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        with pytest.raises(OllamaError, match="^ollama_bad_response:"):
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


@pytest.mark.asyncio
async def test_inventory_skips_invalid_entries_and_normalizes_optional_fields(
    app_config: Any,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "good:tag", "details": None, "size": "big"},
                        {"name": "string-details:tag", "details": "x"},
                        {
                            "name": "bad-fields:tag",
                            "details": {
                                "parameter_size": 9,
                                "quantization_level": "Q4",
                            },
                            "size": -1,
                        },
                        {"name": ""},
                        None,
                        {"name": 5},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "good:tag",
                        "context_length": -1,
                        "size_vram": "large",
                    },
                    {"name": "bad-running:tag", "context_length": True},
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        result = await OllamaClient(app_config, http).models()
    entries = {item["name"]: item for item in result["models"]}
    assert set(entries) == {"good:tag", "string-details:tag", "bad-fields:tag"}
    assert entries["good:tag"]["parameter_size"] is None
    assert entries["good:tag"]["installed_size_bytes"] is None
    assert entries["good:tag"]["loaded_context_tokens"] is None
    assert entries["good:tag"]["loaded_vram_bytes"] is None
    assert entries["string-details:tag"]["parameter_size"] is None
    assert entries["bad-fields:tag"]["parameter_size"] is None
    assert entries["bad-fields:tag"]["quantization"] == "Q4"
    assert entries["bad-fields:tag"]["installed_size_bytes"] is None


@pytest.mark.asyncio
async def test_empty_inventory_is_valid(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        inventory = await OllamaClient(app_config, http).models()
    assert inventory["models"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,response",
    [
        ("/api/tags", httpx.Response(200, json={"models": None})),
        ("/api/tags", httpx.Response(200, text="not json")),
        ("/api/tags", httpx.Response(500, json={"error": "secret"})),
        ("/api/ps", httpx.Response(500, json={"error": "secret"})),
    ],
)
async def test_inventory_errors_are_sanitized(
    app_config: Any, path: str, response: httpx.Response
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return (
            response
            if request.url.path == path
            else httpx.Response(200, json={"models": []})
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        with pytest.raises(OllamaError) as exc_info:
            await OllamaClient(app_config, http).models()
    assert exc_info.value.code in {"ollama_unavailable", "ollama_bad_response"}
    assert "secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_inventory_timeouts_are_sanitized(app_config: Any) -> None:
    for timeout_path in ("/api/tags", "/api/ps"):

        async def handler(
            request: httpx.Request, _timeout_path: str = timeout_path
        ) -> httpx.Response:
            if request.url.path == _timeout_path:
                raise httpx.ReadTimeout("secret")
            return httpx.Response(200, json={"models": []})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://ollama.test"
        ) as http:
            with pytest.raises(OllamaError, match="^ollama_timeout:"):
                await OllamaClient(app_config, http).models()


@pytest.mark.asyncio
async def test_installed_tag_cache_is_complete_shared_and_tags_only(
    app_config: Any,
) -> None:
    calls = {"tags": 0, "ps": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            calls["ps"] += 1
        else:
            calls["tags"] += 1
        return httpx.Response(
            200,
            json={"models": [{"name": f"model-{index}"} for index in range(250)]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        client = OllamaClient(app_config, http)
        first, second = await asyncio.gather(
            client.installed_tags(), client.installed_tags()
        )
    assert len(first) == 250
    assert first == second
    assert calls == {"tags": 1, "ps": 0}


@pytest.mark.asyncio
async def test_installed_tag_cache_does_not_cache_failures(app_config: Any) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"models": [{"name": "qwen:32k"}]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        client = OllamaClient(app_config, http)
        with pytest.raises(OllamaError, match="^ollama_unavailable:"):
            await client.installed_tags()
        assert await client.installed_tags() == {"qwen:32k"}
    assert calls == 2
