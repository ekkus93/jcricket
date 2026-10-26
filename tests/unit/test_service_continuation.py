"""Continuation selection and remaining service validation branches."""

import json
from contextlib import closing
from typing import Any

import httpx
import pytest

from second_brain_mcp.errors import ServiceError
from second_brain_mcp.ollama import OllamaClient
from second_brain_mcp.service import SecondBrainService
from second_brain_mcp.store import ConversationStore, ModelSelection


def _service(app_config: Any, http: httpx.AsyncClient) -> SecondBrainService:
    return SecondBrainService(
        app_config,
        OllamaClient(app_config, http),
        ConversationStore(app_config.database_path),
    )


# TC-20: direct-model continuation


@pytest.mark.asyncio
async def test_direct_model_continuation_uses_current_budget(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = _service(app_config, mock_ollama)
    first = await service.ask("codex", "hello", model="other:tag")
    assert first["context_limit_tokens"] == 8192
    app_config.allowed_models["other:tag"].context_tokens = 16384

    resumed = await service.ask(
        "codex", "follow up", conversation_id=first["conversation_id"]
    )

    assert resumed["model"] == "other:tag"
    assert resumed["model_profile"] is None
    assert resumed["context_limit_tokens"] == 16384
    stored = service.store.get("codex", first["conversation_id"])
    assert (stored.model_profile, stored.model_tag, stored.context_limit_tokens) == (
        None,
        "other:tag",
        16384,
    )


# TC-21: stored profile no longer configured


@pytest.mark.asyncio
async def test_continuation_rejects_profile_missing_from_config(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = _service(app_config, mock_ollama)
    conversation_id = service.store.record_turn(
        "codex",
        None,
        ModelSelection("legacy", "qwen:32k", 32768),
        "q",
        None,
        "a",
        "discuss",
        new_conversation=True,
    )

    with pytest.raises(ServiceError) as exc_info:
        await service.ask("codex", "continue", conversation_id=conversation_id)

    assert str(exc_info.value) == (
        "model_not_approved: this conversation's profile is no longer approved; "
        "choose a profile"
    )
    assert len(service.store.history(conversation_id)) == 2


# TC-22: remaining validation branches


@pytest.mark.asyncio
async def test_missing_direct_model_names_the_tag(app_config: Any) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "qwen:32k"}]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        with pytest.raises(ServiceError) as exc_info:
            await _service(app_config, http).ask("codex", "hi", model="other:tag")
    assert str(exc_info.value) == (
        'model_not_installed: model tag "other:tag" is not installed in Ollama'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {"conversation_id": "   "},
            "invalid_input: conversation_id must not be empty",
        ),
        ({"mode": "nope"}, "invalid_input: mode is not supported"),
    ],
)
async def test_service_rejects_blank_conversation_id_and_unknown_mode(
    app_config: Any, mock_ollama: httpx.AsyncClient, arguments: dict, message: str
) -> None:
    with pytest.raises(ServiceError) as exc_info:
        await _service(app_config, mock_ollama).ask("codex", "hi", **arguments)
    assert str(exc_info.value) == message


@pytest.mark.asyncio
async def test_orphan_assistant_row_is_left_out_of_the_prompt(
    app_config: Any,
) -> None:
    sent: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen:32k"}]})
        sent.append(json.loads(await request.aread()))
        return httpx.Response(200, json={"message": {"content": "answer"}})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        service = _service(app_config, http)
        store = service.store
        with closing(store.connect()) as db, db:
            db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("orphan-id", "codex", "32k", "qwen:32k", 32768, "t", "t"),
            )
            db.execute(
                "INSERT INTO messages(conversation_id, role, content, created_at) "
                "VALUES ('orphan-id', 'assistant', 'orphan reply', 't')"
            )
        store.record_turn(
            "codex",
            "orphan-id",
            ModelSelection("32k", "qwen:32k", 32768),
            "first question",
            None,
            "first answer",
            "discuss",
        )
        await service.ask("codex", "current", conversation_id="orphan-id")

    contents = [message["content"] for message in sent[0]["messages"][1:]]
    assert contents == ["first question", "first answer", "current"]
