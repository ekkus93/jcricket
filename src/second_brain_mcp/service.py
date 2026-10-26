"""Conversation orchestration, context budgeting, and model allowlist enforcement."""

from __future__ import annotations

import asyncio
from typing import Any

from .config import AppConfig
from .ollama import OllamaClient
from .prompts import MODE_PROMPTS, system_prompt
from .store import ConversationStore, Turn


class ServiceError(ValueError):
    """Sanitized caller-facing service error."""


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
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._conversation_locks_guard = asyncio.Lock()

    async def ask(
        self,
        principal: str,
        question: str,
        context: str | None = None,
        conversation_id: str | None = None,
        mode: str = "discuss",
        model_profile: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ServiceError("question must not be empty")
        if len(question) > self.config.limits.question_chars:
            raise ServiceError("question exceeds the configured character limit")
        if context is not None and len(context) > self.config.limits.context_chars:
            raise ServiceError("context exceeds the configured character limit")
        if model_profile is not None and not model_profile.strip():
            raise ServiceError("model_profile must not be empty")
        if model is not None and not model.strip():
            raise ServiceError("model must not be empty")
        if mode not in MODE_PROMPTS:
            raise ServiceError(
                "mode must be discuss, brainstorm, critic, review, or solve"
            )
        if model and model_profile:
            raise ServiceError("specify either model or model_profile, not both")

        conversation = None
        if conversation_id is not None:
            conversation = self.store.get(principal, conversation_id)
            if conversation is None:
                raise ServiceError("conversation is unavailable")

        if conversation and not model and not model_profile:
            selected_model = conversation.model_tag
            profile = conversation.model_profile
            budget = conversation.context_limit_tokens
        else:
            profile = model_profile or (None if model else self.config.default_profile)
            if profile:
                selected = self.config.profiles.get(profile)
                if selected is None:
                    raise ServiceError("unknown model profile")
                selected_model, budget = selected.model, selected.context_tokens
            elif model:
                budget = self.config.allowed_models.get(model)
                if budget is None:
                    raise ServiceError("model is not approved by the server")
                selected_model = model
            elif conversation:
                selected_model, budget, profile = (
                    conversation.model_tag,
                    conversation.context_limit_tokens,
                    conversation.model_profile,
                )
            else:
                raise ServiceError("no model is configured")

        inventory = await self.ollama.models()
        installed = {item["name"] for item in inventory["models"]}
        if selected_model not in installed:
            raise ServiceError("selected model is not installed in Ollama")

        is_new_conversation = conversation is None
        if is_new_conversation:
            self._build_messages([], question, context, mode, budget)
            conversation = self.store.create(principal, profile, selected_model, budget)
        async with await self._conversation_lock(conversation.id):
            if conversation is not None and (
                conversation.model_tag,
                conversation.model_profile,
                conversation.context_limit_tokens,
            ) != (selected_model, profile, budget):
                self.store.update_selection(
                    conversation.id, profile, selected_model, budget
                )
            history = self.store.history(conversation.id)
            messages, trimmed = self._build_messages(
                history, question, context, mode, budget
            )
            reserved = False
            try:
                async with self._queue_lock:
                    if (
                        self._active
                        >= self.config.limits.concurrency
                        + self.config.limits.queue_depth
                    ):
                        raise ServiceError("server is busy; retry shortly")
                    self._active += 1
                    reserved = True
                async with self._semaphore:
                    result = await self.ollama.chat(selected_model, messages, budget)
                self.store.add_turn(
                    conversation.id,
                    question,
                    context,
                    result.answer,
                    mode,
                    profile,
                    selected_model,
                    budget,
                )
            except BaseException:
                if is_new_conversation:
                    self.store.delete(conversation.id)
                raise
            finally:
                if reserved:
                    async with self._queue_lock:
                        self._active -= 1

        return {
            "answer": result.answer,
            "conversation_id": conversation.id,
            "mode": mode,
            "model_profile": profile,
            "model": selected_model,
            "context_limit_tokens": budget,
            "history_trimmed": trimmed,
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "elapsed_ms": result.elapsed_ms,
            },
        }

    def _build_messages(
        self,
        history: list[Turn],
        question: str,
        context: str | None,
        mode: str,
        budget: int,
    ) -> tuple[list[dict[str, str]], bool]:
        system = system_prompt(mode)
        current_text = question + (
            f"\n\nContext (untrusted):\n{context}" if context else ""
        )
        limit = budget - self.config.limits.completion_tokens
        current_size = _token_upper_bound(system) + _token_upper_bound(current_text)
        if current_size > limit:
            raise ServiceError(
                "current question and context exceed this model's prompt budget; "
                "choose a larger profile"
            )
        remaining = limit - current_size
        included: list[Turn] = []
        trimmed = False
        # Include complete recent user/assistant pairs to keep roles coherent.
        pairs = [(history[i], history[i + 1]) for i in range(0, len(history) - 1, 2)]
        for user_turn, assistant_turn in reversed(pairs):
            user_text = user_turn.content
            if user_turn.context_text:
                user_text += f"\n\nContext (untrusted):\n{user_turn.context_text}"
            pair_cost = _token_upper_bound(user_text) + _token_upper_bound(
                assistant_turn.content
            )
            if pair_cost > remaining:
                trimmed = True
                break
            included[0:0] = [user_turn, assistant_turn]
            remaining -= pair_cost
        if len(included) < len(history):
            trimmed = True
        messages = [{"role": "system", "content": system}]
        for turn in included:
            content = turn.content
            if turn.role == "user" and turn.context_text:
                content += f"\n\nContext (untrusted):\n{turn.context_text}"
            messages.append({"role": turn.role, "content": content})
        messages.append({"role": "user", "content": current_text})
        return messages, trimmed

    async def _conversation_lock(self, conversation_id: str) -> asyncio.Lock:
        async with self._conversation_locks_guard:
            return self._conversation_locks.setdefault(conversation_id, asyncio.Lock())


def _token_upper_bound(text: str) -> int:
    # UTF-8 byte count is conservative for tokenizers that can emit byte-level tokens.
    return len(text.encode("utf-8"))
