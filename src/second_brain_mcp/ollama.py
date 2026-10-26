"""Read-only discovery and tool-free chat access to the Ollama HTTP API."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import AppConfig
from .errors import OllamaError

MAX_LISTED_MODELS = 200
logger = logging.getLogger(__name__)


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
        self._installed_tags_cache: set[str] | None = None
        self._installed_tags_expires = 0.0
        self._installed_tags_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        context: int,
        completion_tokens: int | None = None,
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
                        "num_predict": completion_tokens
                        or self.config.limits.completion_tokens,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            answer = payload.get("message", {}).get("content")
            if not isinstance(answer, str) or not answer.strip():
                raise OllamaError("ollama_bad_response")
            answer = answer.strip()
            if len(answer.encode("utf-8")) > self.config.limits.response_bytes:
                raise OllamaError("ollama_bad_response")
            prompt_tokens = _optional_int(payload.get("prompt_eval_count"))
            completion_count = _optional_int(payload.get("eval_count"))
            estimate = (
                sum(len(item["content"].encode("utf-8")) + 8 for item in messages) + 16
            )
            if prompt_tokens is not None and prompt_tokens > estimate:
                logger.warning(
                    "category=estimate_exceeded estimate=%d prompt_tokens=%d",
                    estimate,
                    prompt_tokens,
                )
            if (
                prompt_tokens is not None
                and completion_count is not None
                and prompt_tokens + completion_count >= context
            ):
                logger.warning(
                    "category=context_saturated prompt_tokens=%d "
                    "completion_tokens=%d context_tokens=%d",
                    prompt_tokens,
                    completion_count,
                    context,
                )
            return ChatResult(
                answer=answer,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_count,
                elapsed_ms=_duration_ms(payload),
            )
        except httpx.TimeoutException as exc:
            raise OllamaError("ollama_timeout") from exc
        except httpx.HTTPError as exc:
            raise OllamaError("ollama_unavailable") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise OllamaError("ollama_bad_response") from exc

    async def models(self) -> dict[str, Any]:
        try:
            tags_response, ps_response = await asyncio.gather(
                self._client.get("/api/tags"), self._client.get("/api/ps")
            )
            tags_response.raise_for_status()
            ps_response.raise_for_status()
            tags_payload = tags_response.json()
            running_payload = ps_response.json()
            if not isinstance(tags_payload, dict) or not isinstance(
                running_payload, dict
            ):
                raise OllamaError("ollama_bad_response")
            tags = tags_payload.get("models")
            running = running_payload.get("models")
            if not isinstance(tags, list) or not isinstance(running, list):
                raise OllamaError("ollama_bad_response")
        except httpx.TimeoutException as exc:
            raise OllamaError("ollama_timeout") from exc
        except httpx.HTTPError as exc:
            raise OllamaError("ollama_unavailable") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise OllamaError("ollama_bad_response") from exc

        running_by_name = {}
        for item in running:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            running_by_name[name] = item
        profiles_by_model: dict[str, list[tuple[str, int]]] = {}
        for profile_name, profile in self.config.profiles.items():
            profiles_by_model.setdefault(profile.model, []).append(
                (profile_name, profile.context_tokens)
            )
        results = []
        seen: set[str] = set()
        for item in tags:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            if name in seen:
                continue
            seen.add(name)
            details = item.get("details")
            if not isinstance(details, dict):
                details = {}
            loaded = running_by_name.get(name)
            profiles = profiles_by_model.get(name, [])
            direct_selection = self.config.allowed_models.get(name)
            results.append(
                {
                    "name": name,
                    "parameter_size": _optional_str(details.get("parameter_size")),
                    "quantization": _optional_str(details.get("quantization_level")),
                    "installed_size_bytes": _optional_nonnegative_int(item.get("size")),
                    "loaded": loaded is not None,
                    "loaded_context_tokens": _optional_nonnegative_int(
                        loaded.get("context_length")
                    )
                    if loaded
                    else None,
                    "loaded_vram_bytes": _optional_nonnegative_int(
                        loaded.get("size_vram")
                    )
                    if loaded
                    else None,
                    "selectable": bool(profiles or direct_selection),
                    "profiles": [profile_name for profile_name, _ in profiles],
                    "configured_context_limit_tokens": (
                        max(
                            (budget for _, budget in profiles),
                            default=(
                                direct_selection.context_tokens
                                if direct_selection
                                else None
                            ),
                        )
                    ),
                }
            )
        required_names = list(
            dict.fromkeys(
                [profile.model for profile in self.config.profiles.values()]
                + list(self.config.allowed_models)
            )
        )
        by_name = {item["name"]: item for item in results}
        required = [by_name[name] for name in required_names if name in by_name]
        required_set = {item["name"] for item in required}
        remaining = [item for item in results if item["name"] not in required_set]
        bounded = (required + remaining)[:MAX_LISTED_MODELS]
        return {
            "models": bounded,
            "default_profile": self.config.default_profile,
            "truncated": len(results) > len(bounded),
        }

    async def installed_tags(self) -> set[str]:
        """Return the complete installed-tag set, sharing short-lived lookups."""
        ttl = self.config.limits.inventory_cache_seconds
        if ttl == 0:
            return await self._fetch_installed_tags()
        async with self._installed_tags_lock:
            now = time.monotonic()
            if (
                self._installed_tags_cache is not None
                and now < self._installed_tags_expires
            ):
                return set(self._installed_tags_cache)
            tags = await self._fetch_installed_tags()
            self._installed_tags_cache = tags
            self._installed_tags_expires = time.monotonic() + ttl
            return set(tags)

    async def _fetch_installed_tags(self) -> set[str]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
            models = payload.get("models") if isinstance(payload, dict) else None
            if not isinstance(models, list):
                raise OllamaError("ollama_bad_response")
            return {
                item["name"]
                for item in models
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and item["name"].strip()
            }
        except httpx.TimeoutException as exc:
            raise OllamaError("ollama_timeout") from exc
        except httpx.HTTPError as exc:
            raise OllamaError("ollama_unavailable") from exc
        except (ValueError, TypeError, AttributeError) as exc:
            raise OllamaError("ollama_bad_response") from exc


def _optional_int(value: Any) -> int | None:
    return _optional_nonnegative_int(value)


def _optional_nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _duration_ms(payload: dict[str, Any]) -> int | None:
    value = payload.get("total_duration")
    return round(value / 1_000_000) if isinstance(value, int) and value >= 0 else None
