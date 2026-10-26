"""Shared mock fixtures for backend-isolated tests."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.store import Conversation, ConversationStore, ModelSelection

MODEL_TAGS = {
    "4k": "qwen:4k",
    "32k": "qwen:32k",
    "128k": "qwen:128k",
    "256k": "qwen:256k",
}
BUDGETS = {"4k": 4096, "32k": 32768, "128k": 131072, "256k": 262144}


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        database_path=tmp_path / "conversations.sqlite3",
        profiles={
            name: ModelProfile(model=MODEL_TAGS[name], context_tokens=budget)
            for name, budget in BUDGETS.items()
        },
        allowed_models={"other:tag": 8192},
        token_env={"codex": "CODEX_MCP_TOKEN", "claude-code": "CLAUDE_CODE_MCP_TOKEN"},
    )


@pytest.fixture
async def mock_ollama() -> AsyncIterator[httpx.AsyncClient]:
    """Provide a deterministic in-memory Ollama API stub."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": name,
                            "size": 42,
                            "details": {
                                "parameter_size": "9B",
                                "quantization_level": "Q4",
                            },
                        }
                        for name in [*MODEL_TAGS.values(), "other:tag"]
                    ]
                },
            )
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": MODEL_TAGS["32k"],
                            "context_length": 32768,
                            "size_vram": 100,
                        }
                    ]
                },
            )
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {"role": "assistant", "content": "mock answer"},
                    "prompt_eval_count": 12,
                    "eval_count": 3,
                    "total_duration": 1_000_000,
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    ) as client:
        yield client


DEFAULT_SELECTION = ModelSelection("32k", "tag", 32768)


@pytest.fixture
def make_conversation():
    """Create a conversation with one complete turn through ``record_turn``."""

    def make(
        store: ConversationStore,
        principal: str = "codex",
        selection: ModelSelection = DEFAULT_SELECTION,
    ) -> Conversation:
        conversation_id = store.record_turn(
            principal,
            None,
            selection,
            "seed question",
            None,
            "seed answer",
            "discuss",
            new_conversation=True,
        )
        conversation = store.get(principal, conversation_id)
        assert conversation is not None
        return conversation

    return make
