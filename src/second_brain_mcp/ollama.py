"""Read-only discovery and tool-free chat access to the Ollama HTTP API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from .config import AppConfig


class OllamaError(RuntimeError):
    """Sanitized error raised for unavailable or invalid Ollama responses."""


@dataclass(frozen=True)
class ChatResult:
    answer: str
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_ms: int | None


class OllamaClient:
    def __init__(
        self, config: AppConfig, client: httpx.AsyncClient | None = None
    ) -> None:
        self.config = config
        timeout = httpx.Timeout(
            config.limits.request_timeout_seconds,
            connect=config.limits.connect_timeout_seconds,
        )
        self._client = client or httpx.AsyncClient(
            base_url=config.ollama_base_url, timeout=timeout
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self, model: str, messages: list[dict[str, str]], context: int
    ) -> ChatResult:
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "think": False,
                    "options": {
                        "num_ctx": context,
                        "num_predict": self.config.limits.completion_tokens,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload.get("message", {}).get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise OllamaError("Ollama returned an invalid chat response")
            answer = answer.strip()
            if len(answer.encode("utf-8")) > self.config.limits.response_bytes:
                raise OllamaError("Ollama response exceeded the configured size limit")
            return ChatResult(
                answer=answer,
                prompt_tokens=_optional_int(payload.get("prompt_eval_count")),
                completion_tokens=_optional_int(payload.get("eval_count")),
                elapsed_ms=_duration_ms(payload),
            )
        except httpx.TimeoutException as exc:
            raise OllamaError("Ollama request timed out") from exc
        except httpx.HTTPError as exc:
            raise OllamaError("Ollama is unavailable or rejected the request") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise OllamaError("Ollama returned malformed data") from exc

    async def models(self) -> dict[str, Any]:
        try:
            tags_response, ps_response = await asyncio.gather(
                self._client.get("/api/tags"), self._client.get("/api/ps")
            )
            tags_response.raise_for_status()
            ps_response.raise_for_status()
            tags = tags_response.json().get("models", [])
            running = ps_response.json().get("models", [])
            if not isinstance(tags, list) or not isinstance(running, list):
                raise OllamaError("Ollama returned malformed model inventory")
        except httpx.TimeoutException as exc:
            raise OllamaError("Ollama model discovery timed out") from exc
        except httpx.HTTPError as exc:
            raise OllamaError("Ollama model discovery is unavailable") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise OllamaError("Ollama returned malformed model inventory") from exc

        running_by_name = {
            item.get("name"): item
            for item in running
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        profiles_by_model: dict[str, list[tuple[str, int]]] = {}
        for profile_name, profile in self.config.profiles.items():
            profiles_by_model.setdefault(profile.model, []).append(
                (profile_name, profile.context_tokens)
            )
        results = []
        for item in tags[:200]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            loaded = running_by_name.get(name)
            profiles = profiles_by_model.get(name, [])
            direct_budget = self.config.allowed_models.get(name)
            results.append(
                {
                    "name": name,
                    "parameter_size": item.get("details", {}).get("parameter_size"),
                    "quantization": item.get("details", {}).get("quantization_level"),
                    "installed_size_bytes": item.get("size"),
                    "loaded": loaded is not None,
                    "loaded_context_tokens": loaded.get("context_length")
                    if loaded
                    else None,
                    "loaded_vram_bytes": loaded.get("size_vram") if loaded else None,
                    "selectable": bool(profiles or direct_budget),
                    "profiles": [profile_name for profile_name, _ in profiles],
                    "configured_context_limit_tokens": (
                        max((budget for _, budget in profiles), default=direct_budget)
                    ),
                }
            )
        return {"models": results, "default_profile": self.config.default_profile}


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _duration_ms(payload: dict[str, Any]) -> int | None:
    value = payload.get("total_duration")
    return round(value / 1_000_000) if isinstance(value, int) and value >= 0 else None
