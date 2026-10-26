"""Credential, Ollama URL, and field validation messages."""

from pathlib import Path

import pytest

from second_brain_mcp.config import AppConfig, ModelProfile, load_config

BUDGETS = {"4k": 4096, "32k": 32768, "128k": 131072, "256k": 262144}


def _profiles() -> dict[str, ModelProfile]:
    return {
        name: ModelProfile(model=f"tag:{name}", context_tokens=budget)
        for name, budget in BUDGETS.items()
    }


def _message(exc_info: pytest.ExceptionInfo) -> str:
    return str(exc_info.value)


# TC-30: credentials


def test_credentials_require_both_local_principals(monkeypatch) -> None:
    monkeypatch.setenv("ONLY_CODEX", "c" * 32)
    config = AppConfig(profiles=_profiles(), token_env={"codex": "ONLY_CODEX"})
    with pytest.raises(ValueError) as exc_info:
        config.credentials()
    assert _message(exc_info) == (
        "token_env must map distinct credentials for codex and claude-code"
    )


@pytest.mark.parametrize(
    ("codex", "claude", "message"),
    [
        (
            "c" * 31,
            "d" * 32,
            "bearer tokens must contain at least 32 characters for principals: codex",
        ),
        ("s" * 32, "s" * 32, "each configured principal must use a distinct token"),
    ],
)
def test_credentials_reject_weak_or_shared_tokens(
    monkeypatch, codex: str, claude: str, message: str
) -> None:
    monkeypatch.setenv("CODEX_T", codex)
    monkeypatch.setenv("CLAUDE_T", claude)
    config = AppConfig(
        profiles=_profiles(), token_env={"codex": "CODEX_T", "claude-code": "CLAUDE_T"}
    )
    with pytest.raises(ValueError) as exc_info:
        config.credentials()
    assert _message(exc_info) == message


def test_credentials_return_principal_token_map(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_T", "c" * 32)
    monkeypatch.setenv("CLAUDE_T", "d" * 40)
    config = AppConfig(
        profiles=_profiles(), token_env={"codex": "CODEX_T", "claude-code": "CLAUDE_T"}
    )
    assert config.credentials() == {"codex": "c" * 32, "claude-code": "d" * 40}


# TC-31: Ollama URL forms


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (
            "ftp://127.0.0.1",
            "ollama_base_url must use http or https and include a host",
        ),
        ("http://", "ollama_base_url must use http or https and include a host"),
        ("http://example.com", "ollama_base_url must point to a loopback address"),
        ("http://10.0.0.5:11434", "ollama_base_url must point to a loopback address"),
    ],
)
def test_rejects_invalid_ollama_urls(url: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AppConfig(profiles=_profiles(), ollama_base_url=url)


@pytest.mark.parametrize(
    ("url", "stored"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_accepts_loopback_ollama_urls(url: str, stored: str) -> None:
    assert AppConfig(profiles=_profiles(), ollama_base_url=url).ollama_base_url == (
        stored
    )


# TC-32: remaining field validation


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"default_profile": "64k"},
            "default_profile must be one of 4k, 32k, 128k, 256k",
        ),
        (
            {
                "profiles": _profiles()
                | {"4k": ModelProfile(model="tag:4k", context_tokens=8192)}
            },
            "profile context token budgets must match their names",
        ),
        (
            {"trusted_hosts": ["a.example", "A.example"]},
            "trusted_hosts entries must be unique",
        ),
        ({"allowed_models": ["x"]}, "allowed_models must be a mapping"),
        (
            {"allowed_models": {"   ": 8192}},
            "allowed model tags and context budgets must be valid",
        ),
        (
            {"allowed_models": {f"extra:{index}": 8192 for index in range(197)}},
            "no more than 200 distinct selectable model tags are allowed",
        ),
    ],
)
def test_field_validation_messages(overrides: dict, message: str) -> None:
    arguments = {"profiles": _profiles()} | overrides
    with pytest.raises(ValueError, match=message):
        AppConfig(**arguments)


def test_two_hundred_selectable_tags_are_allowed() -> None:
    allowed = {f"extra:{index}": 8192 for index in range(196)}
    assert len(AppConfig(profiles=_profiles(), allowed_models=allowed).allowed_models)


def test_list_shaped_yaml_root_is_rejected_with_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- not\n- a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_config(config_path)
    assert _message(exc_info) == (
        f"invalid configuration in {config_path}: configuration root must be a mapping"
    )


@pytest.mark.parametrize("content", [None, "profiles: [unclosed\n"])
def test_missing_or_malformed_yaml_names_the_file(
    tmp_path: Path, content: str | None
) -> None:
    config_path = tmp_path / "config.yaml"
    if content is not None:
        config_path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        load_config(config_path)
    assert _message(exc_info).startswith(f"invalid configuration in {config_path}: ")
