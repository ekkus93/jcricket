from typing import Any

import httpx
import pytest

from second_brain_mcp.errors import OllamaError
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
async def test_continuation_rejects_revoked_direct_model(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello", model="other:tag")
    app_config.allowed_models.pop("other:tag")
    with pytest.raises(ServiceError) as exc_info:
        await service.ask("codex", "continue", conversation_id=first["conversation_id"])
    assert exc_info.value.code == "model_not_approved"
    assert store.get("codex", first["conversation_id"]).model_tag == "other:tag"


@pytest.mark.asyncio
async def test_missing_profile_model_error_names_profile_and_tag(
    app_config: Any,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        pytest.fail("ask path must not request the running-model inventory")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        service = SecondBrainService(
            app_config,
            OllamaClient(app_config, http),
            ConversationStore(app_config.database_path),
        )
        with pytest.raises(ServiceError) as exc_info:
            await service.ask("codex", "hello", model_profile="32k")
    assert exc_info.value.code == "model_not_installed"
    assert "32k" in str(exc_info.value)
    assert app_config.profiles["32k"].model in str(exc_info.value)


@pytest.mark.asyncio
async def test_ask_accepts_installed_tag_beyond_inventory_display_limit(
    app_config: Any,
) -> None:
    import asyncio

    app_config.profiles["32k"].model = "model-249"
    app_config.limits.inventory_cache_seconds = 30
    tag_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tag_calls
        if request.url.path == "/api/tags":
            tag_calls += 1
            return httpx.Response(
                200,
                json={"models": [{"name": f"model-{index}"} for index in range(250)]},
            )
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": "ok"}})
        pytest.fail("ask path must not request /api/ps")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        service = SecondBrainService(
            app_config,
            OllamaClient(app_config, http),
            ConversationStore(app_config.database_path),
        )
        results = await asyncio.gather(
            service.ask("codex", "one"), service.ask("codex", "two")
        )
    assert tag_calls == 1
    assert [result["model"] for result in results] == ["model-249", "model-249"]


@pytest.mark.asyncio
async def test_continuation_uses_current_profile_mapping_and_budget(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello", model_profile="32k")
    app_config.profiles["32k"].model = "other:tag"
    app_config.profiles["32k"].context_tokens = 16384
    resumed = await service.ask(
        "codex", "continue", conversation_id=first["conversation_id"]
    )
    stored = store.get("codex", first["conversation_id"])
    assert resumed["model"] == "other:tag"
    assert resumed["context_limit_tokens"] == 16384
    assert stored.model_tag == "other:tag"
    assert stored.context_limit_tokens == 16384


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["ollama_timeout", "ollama_unavailable"])
async def test_failed_selection_change_does_not_modify_conversation(
    code: str, app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello", model_profile="32k")
    before = store.get("codex", first["conversation_id"])

    async def fail_chat(*args, **kwargs):
        raise OllamaError(code)

    service.ollama.chat = fail_chat
    with pytest.raises(OllamaError):
        await service.ask(
            "codex",
            "switch and continue",
            conversation_id=first["conversation_id"],
            model_profile="128k",
        )
    after = store.get("codex", first["conversation_id"])
    assert after == before
    assert len(store.history(first["conversation_id"])) == 2


@pytest.mark.asyncio
async def test_oversized_continuation_does_not_change_selection(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello", model_profile="32k")
    before = store.get("codex", first["conversation_id"])
    with pytest.raises(ServiceError) as exc_info:
        await service.ask(
            "codex",
            "x" * 5000,
            conversation_id=first["conversation_id"],
            model_profile="4k",
        )
    assert exc_info.value.code == "context_too_large"
    assert store.get("codex", first["conversation_id"]) == before
    assert len(store.history(first["conversation_id"])) == 2


@pytest.mark.asyncio
async def test_cancelled_selection_change_does_not_modify_conversation(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    import asyncio

    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello", model_profile="32k")
    before = store.get("codex", first["conversation_id"])
    started = asyncio.Event()

    async def blocked_chat(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    service.ollama.chat = blocked_chat
    task = asyncio.create_task(
        service.ask(
            "codex",
            "cancel me",
            conversation_id=first["conversation_id"],
            model_profile="128k",
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store.get("codex", first["conversation_id"]) == before
    assert len(store.history(first["conversation_id"])) == 2
    assert service._conversation_locks == {}


@pytest.mark.asyncio
async def test_busy_continuation_does_not_change_selection(
    app_config: Any,
) -> None:
    import asyncio

    app_config.limits.queue_depth = 0
    store = ConversationStore(app_config.database_path)
    started = asyncio.Event()
    release = asyncio.Event()
    chat_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": profile.model}
                        for profile in app_config.profiles.values()
                    ]
                },
            )
        if request.url.path == "/api/chat":
            chat_calls += 1
            if chat_calls > 1:
                started.set()
                await release.wait()
            return httpx.Response(200, json={"message": {"content": "answer"}})
        pytest.fail("ask path must not request /api/ps")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        service = SecondBrainService(app_config, OllamaClient(app_config, http), store)
        first = await service.ask("codex", "initial", model_profile="32k")
        baseline = store.get("codex", first["conversation_id"])
        active = asyncio.create_task(
            service.ask(
                "codex",
                "switch",
                conversation_id=first["conversation_id"],
                model_profile="128k",
            )
        )
        await started.wait()
        with pytest.raises(ServiceError) as exc_info:
            await service.ask(
                "codex",
                "busy",
                conversation_id=first["conversation_id"],
                model_profile="4k",
            )
        assert exc_info.value.code == "busy"
        assert store.get("codex", first["conversation_id"]) == baseline
        release.set()
        await active


@pytest.mark.asyncio
async def test_deleted_conversation_during_inference_cannot_be_recreated(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    import asyncio

    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "hello")
    started = asyncio.Event()
    release = asyncio.Event()
    original_chat = service.ollama.chat

    async def blocked_chat(*args, **kwargs):
        started.set()
        await release.wait()
        return await original_chat(*args, **kwargs)

    service.ollama.chat = blocked_chat
    task = asyncio.create_task(
        service.ask("codex", "continue", conversation_id=first["conversation_id"])
    )
    await started.wait()
    assert store.delete(first["conversation_id"])
    release.set()
    with pytest.raises(ServiceError) as exc_info:
        await task
    assert exc_info.value.code == "conversation_unavailable"
    assert store.list() == []


def test_history_pairing_skips_unpaired_rows(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    messages, trimmed = service._build_messages(
        [
            Turn("user", "stray unpaired row"),
            Turn("user", "paired question"),
            Turn("assistant", "paired answer"),
        ],
        "new question",
        None,
        "discuss",
        32768,
    )
    assert trimmed is True
    assert [message["content"] for message in messages[1:-1]] == [
        "paired question",
        "paired answer",
    ]


@pytest.mark.asyncio
async def test_conversation_locks_are_removed_after_many_asks(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    service = SecondBrainService(
        app_config,
        OllamaClient(app_config, mock_ollama),
        ConversationStore(app_config.database_path),
    )
    for index in range(50):
        await service.ask("codex", f"question {index}")
        assert service._conversation_locks == {}


@pytest.mark.asyncio
async def test_admission_limit_rejects_before_backend_or_database_write(
    app_config: Any,
) -> None:
    import asyncio

    app_config.limits.queue_depth = 0
    chat_started = asyncio.Event()
    release = asyncio.Event()
    chat_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": app_config.profiles["32k"].model}]},
            )
        if request.url.path == "/api/chat":
            chat_calls += 1
            chat_started.set()
            await release.wait()
            return httpx.Response(
                200, json={"message": {"content": "answer"}, "eval_count": 1}
            )
        pytest.fail("ask path must not request /api/ps")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        store = ConversationStore(app_config.database_path)
        service = SecondBrainService(app_config, OllamaClient(app_config, http), store)
        first = asyncio.create_task(service.ask("codex", "first"))
        await chat_started.wait()
        with pytest.raises(ServiceError) as exc_info:
            await service.ask("codex", "must be rejected")
        assert exc_info.value.code == "busy"
        assert chat_calls == 1
        assert store.list() == []
        release.set()
        await first
        assert len(store.list()) == 1


@pytest.mark.asyncio
async def test_admitted_queue_waits_and_completes(
    app_config: Any,
) -> None:
    import asyncio

    app_config.limits.queue_depth = 1
    chat_started = asyncio.Event()
    release = asyncio.Event()
    chat_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": app_config.profiles["32k"].model}]},
            )
        if request.url.path == "/api/chat":
            chat_calls += 1
            if chat_calls == 1:
                chat_started.set()
                await release.wait()
            return httpx.Response(
                200, json={"message": {"content": "answer"}, "eval_count": 1}
            )
        pytest.fail("ask path must not request /api/ps")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as http:
        service = SecondBrainService(
            app_config,
            OllamaClient(app_config, http),
            ConversationStore(app_config.database_path),
        )
        first = asyncio.create_task(service.ask("codex", "first"))
        await chat_started.wait()
        second = asyncio.create_task(service.ask("codex", "second"))
        await asyncio.sleep(0)
        assert chat_calls == 1
        release.set()
        results = await asyncio.gather(first, second)
    assert chat_calls == 2
    assert len({result["conversation_id"] for result in results}) == 2


@pytest.mark.asyncio
async def test_later_continuation_reads_selection_after_lock(
    app_config: Any, mock_ollama: httpx.AsyncClient
) -> None:
    import asyncio

    store = ConversationStore(app_config.database_path)
    service = SecondBrainService(
        app_config, OllamaClient(app_config, mock_ollama), store
    )
    first = await service.ask("codex", "first", model_profile="32k")
    original_chat = service.ollama.chat
    switched_chat_started = asyncio.Event()
    release_switch = asyncio.Event()

    async def controlled_chat(model, messages, context):
        if (
            model == app_config.profiles["128k"].model
            and not switched_chat_started.is_set()
        ):
            switched_chat_started.set()
            await release_switch.wait()
        return await original_chat(model, messages, context)

    service.ollama.chat = controlled_chat
    switched = asyncio.create_task(
        service.ask(
            "codex",
            "switch model",
            conversation_id=first["conversation_id"],
            model_profile="128k",
        )
    )
    await switched_chat_started.wait()
    later = asyncio.create_task(
        service.ask("codex", "follow up", conversation_id=first["conversation_id"])
    )
    while service._conversation_locks[first["conversation_id"]][1] < 2:
        await asyncio.sleep(0)
    release_switch.set()
    switched_result, later_result = await asyncio.gather(switched, later)
    assert switched_result["model_profile"] == "128k"
    assert later_result["model_profile"] == "128k"
    assert store.get("codex", first["conversation_id"]).model_profile == "128k"


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
    assert service._conversation_locks == {}
