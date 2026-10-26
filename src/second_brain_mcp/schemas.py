"""Public structured MCP tool response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Usage(OutputModel):
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_ms: int | None


class AskResponse(OutputModel):
    answer: str
    conversation_id: str
    mode: str
    model_profile: str | None
    model: str
    context_limit_tokens: int
    history_trimmed: bool
    usage: Usage


class ModelInfo(OutputModel):
    name: str
    parameter_size: str | None
    quantization: str | None
    installed_size_bytes: int | None
    loaded: bool
    loaded_context_tokens: int | None
    loaded_vram_bytes: int | None
    selectable: bool
    profiles: list[str]
    configured_context_limit_tokens: int | None


class ModelInventory(OutputModel):
    models: list[ModelInfo]
    default_profile: str
    truncated: bool
