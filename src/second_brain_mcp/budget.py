"""Conservative prompt-size estimates shared by budgeting, validation, and logging."""

from __future__ import annotations

from collections.abc import Iterable

MESSAGE_OVERHEAD_TOKENS = 8
PROMPT_OVERHEAD_TOKENS = 16
MIN_INPUT_TOKENS = 256


def token_upper_bound(text: str) -> int:
    # UTF-8 byte count is an upper bound for byte-level tokenizers.
    return len(text.encode("utf-8"))


def estimate_messages(contents: Iterable[str]) -> int:
    return (
        sum(
            token_upper_bound(content) + MESSAGE_OVERHEAD_TOKENS for content in contents
        )
        + PROMPT_OVERHEAD_TOKENS
    )


def available_input(context_tokens: int, completion_tokens: int, system: str) -> int:
    """Largest current input, in bytes, that fits beside ``system``."""
    return (
        context_tokens
        - completion_tokens
        - estimate_messages([system])
        - MESSAGE_OVERHEAD_TOKENS
    )
