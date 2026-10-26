from typing import Any

import httpx
import pytest

from second_brain_mcp.ollama import OllamaClient
from second_brain_mcp.prompts import MODE_PROMPTS, system_prompt
from second_brain_mcp.service import SecondBrainService, ServiceError
from second_brain_mcp.store import ConversationStore, Turn


@pytest.mark.parametrize("mode", list(MODE_PROMPTS))
def test_each_mode_has_distinct_instruction(mode: str) -> None:
    prompt = system_prompt(mode)
    assert f"Mode: {mode}." in prompt
    assert MODE_PROMPTS[mode] in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["4k", "32k", "128k", "256k"])
async def test_profiles_select_exact_mapping(
    profile: str, app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    result = await service.ask("codex", "hello", model_profile=profile)
    assert result["model"] == app_config.profiles[profile].model
    assert result["context_limit_tokens"] == app_config.profiles[profile].context_tokens
    assert result["model_profile"] == profile


@pytest.mark.asyncio
async def test_rejects_conflicting_and_unapproved_models(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    with pytest.raises(ServiceError, match="either model or model_profile"):
        await service.ask("codex", "hi", model="other:tag", model_profile="32k")
    with pytest.raises(ServiceError, match="not approved"):
        await service.ask("codex", "hi", model="qwen:unknown")


@pytest.mark.asyncio
async def test_rejects_invalid_input_and_unknown_model(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    with pytest.raises(ServiceError, match="must not be empty"):
        await service.ask("codex", "   ")
    with pytest.raises(ServiceError, match="unknown model profile"):
        await service.ask("codex", "hi", model_profile="unknown")
    with pytest.raises(ServiceError, match="is unavailable"):
        await service.ask("claude-code", "hi", conversation_id="foreign-id")


@pytest.mark.asyncio
async def test_persistence_continuity_and_principal_isolation(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    first = await service.ask("codex", "remember this")
    resumed = await service.ask(
        "codex", "follow up", conversation_id=first["conversation_id"]
    )
    assert resumed["conversation_id"] == first["conversation_id"]
    history = ConversationStore(app_config.database_path).history(
        first["conversation_id"]
    )
    assert [turn.role for turn in history] == ["user", "assistant", "user", "assistant"]
    assert (
        ConversationStore(app_config.database_path).get(
            "claude-code", first["conversation_id"]
        )
        is None
    )


def test_context_budget_trims_old_pairs_and_rejects_large_current_input(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    history = [
        Turn("user", "old " * 1000),
        Turn("assistant", "answer " * 1000),
    ]
    messages, trimmed = service._build_messages(
        history, "new question", None, "discuss", 4096
    )
    assert trimmed is True
    assert len(messages) == 2
    with pytest.raises(ServiceError, match="prompt budget"):
        service._build_messages([], "x" * 5000, None, "discuss", 4096)


@pytest.mark.asyncio
async def test_approved_direct_model_returns_null_profile(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    result = await service.ask("codex", "hello", model="other:tag")
    assert result["model"] == "other:tag"
    assert result["model_profile"] is None
    assert result["context_limit_tokens"] == 8192


@pytest.mark.asyncio
async def test_cancellation_does_not_leave_empty_or_partial_conversation(
    app_config: Any,
) -> None:
    import asyncio

    chat_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            chat_started.set()
            await asyncio.Event().wait()
        if request.url.path in {"/api/tags", "/api/ps"}:
            models = (
                [{"name": app_config.profiles["32k"].model}]
                if request.url.path == "/api/tags"
                else []
            )
            return httpx.Response(200, json={"models": models})
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        store = ConversationStore(app_config.database_path)
        service = SecondBrainService(app_config, OllamaClient(app_config, http), store)
        task = asyncio.create_task(service.ask("codex", "cancel me"))
        await chat_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert store.list() == []
