"""Stable, sanitized errors exposed by the service and MCP tools."""

from __future__ import annotations

import logging

ERROR_MESSAGES = {
    "invalid_input": "the request is invalid",
    "conversation_unavailable": "conversation is unavailable",
    "model_not_approved": "the selected model is not approved by the server",
    "model_not_installed": "the selected model is not installed in Ollama",
    "context_too_large": (
        "current question and context exceed this model's prompt budget"
    ),
    "busy": "server is busy; retry shortly",
    "ollama_unavailable": "Ollama is unavailable or rejected the request",
    "ollama_timeout": "Ollama request timed out",
    "ollama_bad_response": "Ollama returned malformed data",
    "unauthorized": "authenticated principal required",
    "internal_error": "the server could not complete the request",
}

# Caller mistakes are routine; backend trouble needs attention; the rest is a fault.
ERROR_LOG_LEVELS = {
    "invalid_input": logging.INFO,
    "conversation_unavailable": logging.INFO,
    "model_not_approved": logging.INFO,
    "context_too_large": logging.INFO,
    "busy": logging.WARNING,
    "model_not_installed": logging.WARNING,
    "ollama_unavailable": logging.WARNING,
    "ollama_timeout": logging.WARNING,
    "ollama_bad_response": logging.WARNING,
    "unauthorized": logging.ERROR,
    "internal_error": logging.ERROR,
}


class SecondBrainError(RuntimeError):
    """A fixed-code, safe-to-return error."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in ERROR_MESSAGES:
            raise ValueError(f"unknown Second Brain error code: {code}")
        self.code = code
        self.message = message or ERROR_MESSAGES[code]
        super().__init__(f"{code}: {self.message}")


class ServiceError(SecondBrainError):
    """Validated request, conversation, and admission error."""


class OllamaError(SecondBrainError):
    """Sanitized error raised for Ollama failures."""
