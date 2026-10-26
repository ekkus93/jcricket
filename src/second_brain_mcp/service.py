"""Conversation orchestration, context budgeting, and model allowlisting."""

from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal

from .config import AppConfig
from .errors import ServiceError
from .ollama import OllamaClient
from .prompts import MODE_PROMPTS, system_prompt
from .store import ConversationStore, ModelSelection, Turn

MESSAGE_OVERHEAD_TOKENS = 8
PROMPT_OVERHEAD_TOKENS = 16
Mode = Literal["discuss", "brainstorm", "critic", "review", "solve"]


class SecondBrainService:
    def __init__(
        self, config: AppConfig, ollama: OllamaClient, store: ConversationStore
    ) -> None:
        self.config = config
        self.ollama = ollama
        self.store = store
        self._semaphore = asyncio.Semaphore(config.limits.concurrency)
        self._active = 0
        self._queue_lock = asyncio.Lock()
        self._conversation_locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._conversation_locks_guard = asyncio.Lock()

    async def ask(
        self,
        principal: str,
        question: str,
        context: str | None = None,
        conversation_id: str | None = None,
        mode: Mode = "discuss",
        model_profile: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        question = question.strip()
        self._validate(question, context, conversation_id, mode, model_profile, model)
        await self._admit()
        is_new = conversation_id is None
        locked_id = conversation_id or secrets.token_urlsafe(24)
        try:
            async with self._conversation_lock(locked_id):
                conversation = None if is_new else self.store.get(principal, locked_id)
                if not is_new and conversation is None:
                    raise ServiceError("conversation_unavailable")

                selection = self._selection(
                    conversation, model_profile=model_profile, model=model
                )
                installed = await self.ollama.installed_tags()
                if selection.model_tag not in installed:
                    message = (
                        f'model tag "{selection.model_tag}" is not installed in Ollama'
                    )
                    if selection.model_profile:
                        message = (
                            f"profile {selection.model_profile} maps to tag "
                            f'"{selection.model_tag}", which is not installed in Ollama'
                        )
                    raise ServiceError("model_not_installed", message)

                history = [] if is_new else self.store.history(locked_id)
                messages, trimmed = self._build_messages(
                    history,
                    question,
                    context,
                    mode,
                    selection.context_limit_tokens,
                    selection.completion_tokens,
                )
                async with self._semaphore:
                    result = await self.ollama.chat(
                        selection.model_tag,
                        messages,
                        selection.context_limit_tokens,
                        selection.completion_tokens,
                    )
                stored_id = self.store.record_turn(
                    principal,
                    locked_id,
                    selection,
                    question,
                    context,
                    result.answer,
                    mode,
                    new_conversation=is_new,
                )
        finally:
            await self._release_admission()

        return {
            "answer": result.answer,
            "conversation_id": stored_id,
            "mode": mode,
            "model_profile": selection.model_profile,
            "model": selection.model_tag,
            "context_limit_tokens": selection.context_limit_tokens,
            "history_trimmed": trimmed,
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "elapsed_ms": result.elapsed_ms,
            },
        }

    def _validate(
        self,
        question: str,
        context: str | None,
        conversation_id: str | None,
        mode: str,
        model_profile: str | None,
        model: str | None,
    ) -> None:
        if not question:
            raise ServiceError("invalid_input", "question must not be empty")
        if len(question) > self.config.limits.question_chars:
            raise ServiceError("invalid_input", "question exceeds the character limit")
        if context is not None and len(context) > self.config.limits.context_chars:
            raise ServiceError("invalid_input", "context exceeds the character limit")
        if conversation_id is not None and not conversation_id.strip():
            raise ServiceError("invalid_input", "conversation_id must not be empty")
        if model_profile is not None and not model_profile.strip():
            raise ServiceError("invalid_input", "model_profile must not be empty")
        if model is not None and not model.strip():
            raise ServiceError("invalid_input", "model must not be empty")
        if mode not in MODE_PROMPTS:
            raise ServiceError("invalid_input", "mode is not supported")
        if model is not None and model_profile is not None:
            raise ServiceError(
                "invalid_input", "specify either model or model_profile, not both"
            )

    def _selection(
        self,
        conversation,
        *,
        model_profile: str | None,
        model: str | None,
    ) -> ModelSelection:
        if model_profile is not None:
            profile = self.config.profiles.get(model_profile)
            if profile is None:
                raise ServiceError("model_not_approved", "unknown model profile")
            return ModelSelection(
                model_profile,
                profile.model,
                profile.context_tokens,
                profile.completion_tokens or self.config.limits.completion_tokens,
            )
        if model is not None:
            selection = self.config.allowed_models.get(model)
            if selection is None:
                raise ServiceError(
                    "model_not_approved", "model is not approved by the server"
                )
            return ModelSelection(
                None,
                model,
                selection.context_tokens,
                selection.completion_tokens or self.config.limits.completion_tokens,
            )
        if conversation is None:
            profile_name = self.config.default_profile
            profile = self.config.profiles.get(profile_name)
            if profile is None:
                raise ServiceError(
                    "model_not_approved", "no model profile is configured"
                )
            return ModelSelection(
                profile_name,
                profile.model,
                profile.context_tokens,
                profile.completion_tokens or self.config.limits.completion_tokens,
            )
        if conversation.model_profile is not None:
            profile = self.config.profiles.get(conversation.model_profile)
            if profile is None:
                raise ServiceError(
                    "model_not_approved",
                    "this conversation's profile is no longer approved; "
                    "choose a profile",
                )
            return ModelSelection(
                conversation.model_profile,
                profile.model,
                profile.context_tokens,
                profile.completion_tokens or self.config.limits.completion_tokens,
            )
        selection = self.config.allowed_models.get(conversation.model_tag)
        if selection is None:
            raise ServiceError(
                "model_not_approved",
                "this conversation's model is no longer approved; "
                "choose a model_profile",
            )
        return ModelSelection(
            None,
            conversation.model_tag,
            selection.context_tokens,
            selection.completion_tokens or self.config.limits.completion_tokens,
        )

    async def _admit(self) -> None:
        async with self._queue_lock:
            capacity = self.config.limits.concurrency + self.config.limits.queue_depth
            if self._active >= capacity:
                raise ServiceError("busy")
            self._active += 1

    async def _release_admission(self) -> None:
        async with self._queue_lock:
            self._active -= 1

    @asynccontextmanager
    async def _conversation_lock(self, conversation_id: str):
        async with self._conversation_locks_guard:
            lock, refs = self._conversation_locks.get(
                conversation_id, (asyncio.Lock(), 0)
            )
            self._conversation_locks[conversation_id] = (lock, refs + 1)
        try:
            async with lock:
                yield
        finally:
            async with self._conversation_locks_guard:
                current_lock, refs = self._conversation_locks[conversation_id]
                if refs == 1:
                    del self._conversation_locks[conversation_id]
                else:
                    self._conversation_locks[conversation_id] = (
                        current_lock,
                        refs - 1,
                    )

    def _build_messages(
        self,
        history: list[Turn],
        question: str,
        context: str | None,
        mode: str,
        budget: int,
        completion_tokens: int | None = None,
    ) -> tuple[list[dict[str, str]], bool]:
        system = system_prompt(mode)
        current_text = question + (
            f"\n\nContext (untrusted):\n{context}" if context else ""
        )
        limit = budget - (completion_tokens or self.config.limits.completion_tokens)
        current_size = _estimate_messages([system, current_text])
        if current_size > limit:
            available = max(0, limit - _estimate_messages([system]))
            suggestion = self._suggest_profile(current_size)
            suffix = f'; try model_profile "{suggestion}"' if suggestion else ""
            raise ServiceError(
                "context_too_large",
                f"input exceeds the {budget // 1024}k prompt budget "
                f"(about {available} bytes available){suffix}",
            )
        remaining = limit - current_size
        pairs: list[tuple[Turn, Turn]] = []
        index = 0
        while index < len(history):
            if history[index].role == "user":
                if index + 1 < len(history) and history[index + 1].role == "assistant":
                    pairs.append((history[index], history[index + 1]))
                    index += 2
                    continue
            index += 1
        included: list[Turn] = []
        trimmed = False
        for user_turn, assistant_turn in reversed(pairs):
            user_text = user_turn.content
            if user_turn.context_text:
                user_text += f"\n\nContext (untrusted):\n{user_turn.context_text}"
            pair_cost = _estimate_messages([user_text, assistant_turn.content])
            if pair_cost > remaining:
                trimmed = True
                break
            included[0:0] = [user_turn, assistant_turn]
            remaining -= pair_cost
        if len(included) != len(history):
            trimmed = True
        messages = [{"role": "system", "content": system}]
        for turn in included:
            content = turn.content
            if turn.role == "user" and turn.context_text:
                content += f"\n\nContext (untrusted):\n{turn.context_text}"
            messages.append({"role": turn.role, "content": content})
        messages.append({"role": "user", "content": current_text})
        return messages, trimmed

    def _suggest_profile(self, current_size: int) -> str | None:
        for name, profile in sorted(
            self.config.profiles.items(), key=lambda item: item[1].context_tokens
        ):
            reserve = profile.completion_tokens or self.config.limits.completion_tokens
            if current_size <= profile.context_tokens - reserve:
                return name
        return None


def _token_upper_bound(text: str) -> int:
    return len(text.encode("utf-8"))


def _estimate_messages(contents: list[str]) -> int:
    return (
        sum(
            _token_upper_bound(content) + MESSAGE_OVERHEAD_TOKENS
            for content in contents
        )
        + PROMPT_OVERHEAD_TOKENS
    )
