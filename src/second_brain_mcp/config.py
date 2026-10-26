"""Validated application configuration loaded from YAML and environment."""

from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .budget import MIN_INPUT_TOKENS, available_input
from .prompts import MODE_PROMPTS, system_prompt


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelProfile(StrictModel):
    model: str = Field(min_length=1)
    context_tokens: int = Field(gt=0, le=262_144)
    completion_tokens: int | None = Field(default=None, gt=0)


class AllowedModel(StrictModel):
    context_tokens: int = Field(gt=0, le=262_144)
    completion_tokens: int | None = Field(default=None, gt=0)


class Limits(StrictModel):
    request_bytes: int = Field(default=262_144, gt=0, le=10_485_760)
    response_bytes: int = Field(default=262_144, gt=0, le=10_485_760)
    question_chars: int = Field(default=32_000, gt=0)
    context_chars: int = Field(default=100_000, gt=0)
    completion_tokens: int = Field(default=2_048, gt=0)
    concurrency: int = Field(default=1, gt=0, le=16)
    queue_depth: int = Field(default=4, ge=0, le=128)
    request_timeout_seconds: float = Field(default=300, gt=0, le=3600)
    connect_timeout_seconds: float = Field(default=5, gt=0, le=120)
    requests_per_minute: int = Field(default=60, gt=0, le=10_000)
    inventory_cache_seconds: int = Field(default=10, ge=0, le=300)


class AppConfig(StrictModel):
    ollama_base_url: str = "http://127.0.0.1:11434"
    database_path: Path = Path("~/.local/share/second-brain/conversations.sqlite3")
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    default_profile: str = "32k"
    profiles: dict[str, ModelProfile]
    allowed_models: dict[str, AllowedModel] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)
    token_env: dict[str, str] = Field(default_factory=dict)
    log_level: str = "INFO"
    retention_days: int | None = Field(default=None, gt=0)
    trusted_hosts: list[str] = Field(default_factory=list)

    @field_validator("host")
    @classmethod
    def local_host_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("host must be loopback; remote ingress belongs in a proxy")
        return value

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, value: list[str]) -> list[str]:
        normalized = []
        for host in value:
            if (
                not isinstance(host, str)
                or len(host) > 253
                or not re.fullmatch(
                    r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*",
                    host,
                )
            ):
                raise ValueError(
                    "trusted_hosts entries must be bare DNS names without "
                    "scheme, port, or path"
                )
            normalized.append(host.lower())
        if len(set(normalized)) != len(normalized):
            raise ValueError("trusted_hosts entries must be unique")
        return normalized

    @field_validator("profiles")
    @classmethod
    def require_profiles(
        cls, value: dict[str, ModelProfile]
    ) -> dict[str, ModelProfile]:
        expected = {
            "4k": 4096,
            "32k": 32768,
            "128k": 131072,
            "256k": 262144,
        }
        if set(value) != set(expected):
            raise ValueError(
                f"profiles must define exactly: {', '.join(sorted(expected))}"
            )
        if any(
            value[name].context_tokens != budget for name, budget in expected.items()
        ):
            raise ValueError("profile context token budgets must match their names")
        return value

    @field_validator("allowed_models", mode="before")
    @classmethod
    def validate_allowed_models_input(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("allowed_models must be a mapping")
        normalized = {}
        for name, budget in value.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("allowed model tags and context budgets must be valid")
            normalized[name] = (
                {"context_tokens": budget} if type(budget) is int else budget
            )
        return normalized

    @field_validator("default_profile")
    @classmethod
    def known_default_profile(cls, value: str) -> str:
        if value not in {"4k", "32k", "128k", "256k"}:
            raise ValueError("default_profile must be one of 4k, 32k, 128k, 256k")
        return value

    @field_validator("log_level")
    @classmethod
    def valid_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL"
            )
        return normalized

    @model_validator(mode="after")
    def validate_effective_budgets(self) -> AppConfig:
        tags = [profile.model for profile in self.profiles.values()]
        if any(_is_placeholder(tag) for tag in [*tags, *self.allowed_models]):
            raise ValueError(
                "model tag placeholders must be replaced with exact names from "
                "`ollama list`"
            )
        profiles_by_tag: dict[str, list[str]] = {}
        for name, profile in self.profiles.items():
            completion = profile.completion_tokens or self.limits.completion_tokens
            _validate_budget(
                profile.context_tokens,
                completion,
                f"profile {name}",
            )
            profiles_by_tag.setdefault(profile.model, []).append(name)
        for tag, names in profiles_by_tag.items():
            if len(names) > 1:
                raise ValueError(
                    f"model tag {tag!r} is mapped by profiles {', '.join(names)}; "
                    "some models ignore the request's num_ctx, so each profile "
                    "needs its own model variant with that context window"
                )
        profile_tags = {
            profile.model: profile.context_tokens for profile in self.profiles.values()
        }
        for tag, selection in self.allowed_models.items():
            completion = selection.completion_tokens or self.limits.completion_tokens
            _validate_budget(selection.context_tokens, completion, f"model {tag}")
            profile_budget = profile_tags.get(tag)
            if (
                profile_budget is not None
                and profile_budget != selection.context_tokens
            ):
                raise ValueError(
                    f"model tag {tag!r} has a different allowed-model budget; "
                    "select it through its profile instead"
                )
        selectable = set(profile_tags) | set(self.allowed_models)
        if len(selectable) > 200:
            raise ValueError(
                "no more than 200 distinct selectable model tags are allowed"
            )
        for principal, env_name in self.token_env.items():
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", principal):
                raise ValueError(
                    "token_env principal names must be lowercase identifiers"
                )
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", env_name):
                raise ValueError("token_env values must be environment variable names")
        return self

    @field_validator("ollama_base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(
                "ollama_base_url must use http or https and include a host"
            )
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise ValueError("ollama_base_url must point to a loopback address")
        return value.rstrip("/")

    def credentials(self) -> dict[str, str]:
        """Resolve principal-to-secret environment mappings without logging secrets."""
        required_principals = {"codex", "claude-code"}
        if not required_principals.issubset(self.token_env):
            raise ValueError(
                "token_env must map distinct credentials for codex and claude-code"
            )
        credentials = {
            principal: os.environ.get(env_name, "")
            for principal, env_name in self.token_env.items()
        }
        missing = [
            env_name
            for env_name in self.token_env.values()
            if not os.environ.get(env_name)
        ]
        if missing:
            raise ValueError(
                "missing environment variables for configured principals: "
                + ", ".join(missing)
            )
        weak = [
            principal for principal, token in credentials.items() if len(token) < 32
        ]
        if weak:
            raise ValueError(
                "bearer tokens must contain at least 32 characters for principals: "
                + ", ".join(weak)
            )
        malformed = [
            principal
            for principal, token in credentials.items()
            if not token.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ]
        if malformed:
            raise ValueError(
                "bearer tokens must contain printable ASCII for principals: "
                + ", ".join(malformed)
            )
        if len(set(credentials.values())) != len(credentials):
            raise ValueError("each configured principal must use a distinct token")
        return credentials


def _is_placeholder(tag: str) -> bool:
    return tag == "SET_FROM_OLLAMA_LIST" or tag.startswith("REPLACE_WITH_")


def _validate_budget(context_tokens: int, completion_tokens: int, name: str) -> None:
    if completion_tokens >= context_tokens:
        raise ValueError(f"{name} completion_tokens must be less than context_tokens")
    longest_prompt = max(
        (system_prompt(mode) for mode in MODE_PROMPTS),
        key=lambda prompt: len(prompt.encode("utf-8")),
    )
    if available_input(context_tokens, completion_tokens, longest_prompt) < (
        MIN_INPUT_TOKENS
    ):
        raise ValueError(
            f"{name} leaves too little prompt budget after completion reserve; "
            "leave room for the system prompt and at least "
            f"{MIN_INPUT_TOKENS} input tokens"
        )


def load_config(path: Path) -> AppConfig:
    """Load strict YAML configuration from ``path``."""
    try:
        with path.expanduser().open(encoding="utf-8") as config_file:
            raw: Any = yaml.safe_load(config_file)
        if not isinstance(raw, dict):
            raise ValueError("configuration root must be a mapping")
        return AppConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"invalid configuration in {path}: {exc}") from exc
