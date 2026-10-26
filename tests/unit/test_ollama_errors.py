"""Ollama adapter error paths: chat, ask-path inventory, /api/show, and parsing."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest

from second_brain_mcp.ollama import OllamaClient, OllamaError, verify_context_windows
from second_brain_mcp.service import SecondBrainService
from second_brain_mcp.store import ConversationStore

UNAVAILABLE = "ollama_unavailable: Ollama is unavailable or rejected the request"
TIMEOUT = "ollama_timeout: Ollama request timed out"
BAD = "ollama_bad_response: Ollama returned malformed data"

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


def _time_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("slow", request=request)


# TC-10: chat response limits and failures


@pytest.mark.asyncio
async def test_chat_rejects_answer_over_response_byte_limit(app_config: Any) -> None:
    app_config.limits.response_bytes = 10

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "x" * 11}})

    async with _client(handler) as http:
        with pytest.raises(OllamaError) as exc_info:
            await OllamaClient(app_config, http).chat("qwen:32k", [], 32768)
    assert str(exc_info.value) == BAD


@pytest.mark.asyncio
async def test_chat_accepts_answer_exactly_at_response_byte_limit(
    app_config: Any,
) -> None:
    app_config.limits.response_bytes = 10

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "é" * 5}})

    async with _client(handler) as http:
        result = await OllamaClient(app_config, http).chat("qwen:32k", [], 32768)
    assert result.answer == "é" * 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(500, json={"error": "boom"}), UNAVAILABLE),
        (httpx.Response(200, content=b"not json"), BAD),
    ],
)
async def test_chat_http_error_and_malformed_body(
    app_config: Any, response: httpx.Response, expected: str
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return response

    async with _client(handler) as http:
        with pytest.raises(OllamaError) as exc_info:
            await OllamaClient(app_config, http).chat("qwen:32k", [], 32768)
    assert str(exc_info.value) == expected


# TC-11: Ollama unavailable on the ask path


def _tags_failure(kind: str) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/tags":
            raise AssertionError(f"unexpected call to {request.url.path}")
        if kind == "refused":
            return _refuse(request)
        if kind == "timeout":
            return _time_out(request)
        if kind == "not-a-list":
            return httpx.Response(200, json={"models": "nope"})
        return httpx.Response(200, content=b"not json")

    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("refused", UNAVAILABLE),
        ("timeout", TIMEOUT),
        ("not-a-list", BAD),
        ("not-json", BAD),
    ],
)
async def test_ask_reports_installed_tag_lookup_failures(
    app_config: Any, kind: str, expected: str
) -> None:
    store = ConversationStore(app_config.database_path)
    async with _client(_tags_failure(kind)) as http:
        service = SecondBrainService(app_config, OllamaClient(app_config, http), store)
        with pytest.raises(OllamaError) as exc_info:
            await service.ask("codex", "hello")
    assert str(exc_info.value) == expected
    assert store.list() == []


@pytest.mark.asyncio
async def test_disabled_inventory_cache_fetches_tags_for_every_ask(
    app_config: Any,
) -> None:
    app_config.limits.inventory_cache_seconds = 0
    tag_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tag_requests
        if request.url.path == "/api/tags":
            tag_requests += 1
            return httpx.Response(
                200, json={"models": [{"name": app_config.profiles["32k"].model}]}
            )
        return httpx.Response(200, json={"message": {"content": "answer"}})

    async with _client(handler) as http:
        service = SecondBrainService(
            app_config,
            OllamaClient(app_config, http),
            ConversationStore(app_config.database_path),
        )
        await service.ask("codex", "first")
        await service.ask("codex", "second")
    assert tag_requests == 2


# TC-12: /api/show failures


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (lambda request: httpx.Response(500, json={"error": "boom"}), UNAVAILABLE),
        (_time_out, TIMEOUT),
        (lambda request: httpx.Response(200, json=["not", "an", "object"]), BAD),
        (lambda request: httpx.Response(200, content=b"not json"), BAD),
    ],
)
async def test_show_failures_are_sanitized(
    app_config: Any, handler: Callable[[httpx.Request], httpx.Response], expected: str
) -> None:
    async def wrapped(request: httpx.Request) -> httpx.Response:
        return handler(request)

    async with _client(wrapped) as http:
        with pytest.raises(OllamaError) as exc_info:
            await OllamaClient(app_config, http).show("qwen:32k")
    assert str(exc_info.value) == expected


@pytest.mark.asyncio
async def test_show_treats_malformed_fields_as_absent(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "parameters": {"num_ctx": 4096},
                "model_info": {"qwen35.context_length": "262144"},
            },
        )

    async with _client(handler) as http:
        assert await OllamaClient(app_config, http).show("qwen:32k") == (None, None)


@pytest.mark.asyncio
async def test_context_window_check_continues_after_missing_tag(
    app_config: Any,
) -> None:
    budgets = {p.model: p.context_tokens for p in app_config.profiles.values()} | {
        tag: model.context_tokens for tag, model in app_config.allowed_models.items()
    }
    missing = {app_config.profiles["4k"].model, app_config.profiles["128k"].model}

    async def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(await request.aread())["model"]
        if model in missing:
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json={"parameters": f"num_ctx {budgets[model]}"})

    async with _client(handler) as http:
        report = await verify_context_windows(app_config, http)
    assert report.errors == [
        'profile 4k maps to tag "qwen:4k", which is not installed in Ollama',
        'profile 128k maps to tag "qwen:128k", which is not installed in Ollama',
    ]
    assert report.warnings == []


# TC-13: inventory parsing edge cases


@pytest.mark.asyncio
async def test_inventory_ignores_bad_ps_entries_and_duplicate_tags(
    app_config: Any,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen:32k"}, {"name": "qwen:32k"}]}
            )
        return httpx.Response(
            200,
            json={"models": ["not-an-object", {"name": "  "}, {"context_length": 9}]},
        )

    async with _client(handler) as http:
        inventory = await OllamaClient(app_config, http).models()
    assert [model["name"] for model in inventory["models"]] == ["qwen:32k"]
    assert inventory["models"][0]["loaded"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("list_shaped", ["/api/tags", "/api/ps"])
async def test_inventory_rejects_list_shaped_bodies(
    app_config: Any, list_shaped: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == list_shaped:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"models": []})

    async with _client(handler) as http:
        with pytest.raises(OllamaError) as exc_info:
            await OllamaClient(app_config, http).models()
    assert str(exc_info.value) == BAD


@pytest.mark.asyncio
async def test_context_window_warning_is_reported_once_per_tag(
    app_config: Any,
) -> None:
    app_config.allowed_models = {"qwen:4k": app_config.allowed_models["other:tag"]}
    app_config.allowed_models["qwen:4k"].context_tokens = 4096

    async def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(await request.aread())["model"]
        if model == "qwen:4k":
            return httpx.Response(200, json={"parameters": "temperature 1"})
        budget = next(
            p.context_tokens for p in app_config.profiles.values() if p.model == model
        )
        return httpx.Response(200, json={"parameters": f"num_ctx {budget}"})

    async with _client(handler) as http:
        report = await verify_context_windows(app_config, http)
    assert report.errors == []
    assert report.warnings == [
        'tag "qwen:4k" does not pin num_ctx; if the model ignores request num_ctx, '
        "its window is Ollama's default context length, which may be smaller "
        "than 4096"
    ]


# R3-12: the startup check uses its own short metadata timeout


@pytest.mark.asyncio
async def test_context_window_check_builds_client_with_metadata_timeout(
    app_config: Any, monkeypatch
) -> None:
    app_config.limits.metadata_timeout_seconds = 7
    app_config.limits.request_timeout_seconds = 300
    created: list[httpx.AsyncClient] = []
    real_client = httpx.AsyncClient

    def recording_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": "not found"})

        client = real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("second_brain_mcp.ollama.httpx.AsyncClient", recording_client)
    report = await verify_context_windows(app_config)

    assert len(report.errors) == len(app_config.profiles) + len(
        app_config.allowed_models
    )
    [client] = created
    # httpx.MockTransport does not enforce httpx.Timeout (verified separately), so
    # the wiring is asserted on the client's timeout object instead.
    assert client.timeout == httpx.Timeout(
        7, connect=app_config.limits.connect_timeout_seconds
    )
    assert client.timeout.read == 7 and client.timeout.read != 300
    assert str(client.base_url).rstrip("/") == app_config.ollama_base_url


@pytest.mark.asyncio
async def test_close_only_closes_a_client_the_adapter_created(app_config: Any) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    async with _client(handler) as injected:
        await OllamaClient(app_config, injected).close()
        assert injected.is_closed is False

    owner = OllamaClient(app_config)
    await owner.close()
    assert owner._client.is_closed is True
