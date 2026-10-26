"""Validated application configuration loaded from YAML and environment."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelProfile(StrictModel):
    model: str = Field(min_length=1)
    context_tokens: int = Field(gt=0, le=262_144)


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


class AppConfig(StrictModel):
    ollama_base_url: str = "http://127.0.0.1:11434"
    database_path: Path = Path("~/.local/share/second-brain/conversations.sqlite3")
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    default_profile: str = "32k"
    profiles: dict[str, ModelProfile]
    allowed_models: dict[str, int] = Field(default_factory=dict)
    limits: Limits = Field(default_factory=Limits)
    token_env: dict[str, str] = Field(default_factory=dict)
    log_level: str = "INFO"

    @field_validator("host")
    @classmethod
    def local_host_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("host must be loopback; remote ingress belongs in a proxy")
        return value

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

    @field_validator("allowed_models")
    @classmethod
    def validate_allowed_models(cls, value: dict[str, int]) -> dict[str, int]:
        if any(
            not name.strip() or budget <= 0 or budget > 262_144
            for name, budget in value.items()
        ):
            raise ValueError("allowed model tags and context budgets must be valid")
        return value

    @field_validator("default_profile")
    @classmethod
    def known_default_profile(cls, value: str) -> str:
        if value not in {"4k", "32k", "128k", "256k"}:
            raise ValueError("default_profile must be one of 4k, 32k, 128k, 256k")
        return value

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
        if len(set(credentials.values())) != len(credentials):
            raise ValueError("each configured principal must use a distinct token")
        return credentials


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
