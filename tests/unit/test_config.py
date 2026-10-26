from pathlib import Path

import pytest
from pydantic import ValidationError

from second_brain_mcp.config import AppConfig, Limits, ModelProfile, load_config


def test_rejects_non_loopback_host(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """host: 0.0.0.0
profiles:
  4k: {model: a, context_tokens: 4096}
  32k: {model: b, context_tokens: 32768}
  128k: {model: c, context_tokens: 131072}
  256k: {model: d, context_tokens: 262144}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="host must be loopback"):
        load_config(config)


def test_rejects_missing_profile(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("profiles: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="profiles must define exactly"):
        load_config(config)


def test_rejects_non_loopback_ollama_url(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """ollama_base_url: http://0.0.0.0:11434
profiles:
  4k: {model: a, context_tokens: 4096}
  32k: {model: b, context_tokens: 32768}
  128k: {model: c, context_tokens: 131072}
  256k: {model: d, context_tokens: 262144}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="loopback"):
        load_config(config)


@pytest.mark.parametrize(
    "host", ["https://example.com", "example.com:443", "example.com/path"]
)
def test_trusted_hosts_must_be_bare_dns_names(host: str, app_config) -> None:
    values = app_config.model_dump()
    values["trusted_hosts"] = [host]
    with pytest.raises(ValidationError, match="bare DNS names"):
        AppConfig.model_validate(values)


def test_credentials_fail_if_any_configured_secret_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """token_env: {codex: CODEX_TEST, claude-code: CLAUDE_TEST}
profiles:
  4k: {model: a, context_tokens: 4096}
  32k: {model: b, context_tokens: 32768}
  128k: {model: c, context_tokens: 131072}
  256k: {model: d, context_tokens: 262144}
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_TEST", "x" * 32)
    monkeypatch.delenv("CLAUDE_TEST", raising=False)
    config = load_config(config_path)
    with pytest.raises(ValueError, match="CLAUDE_TEST"):
        config.credentials()


def _valid_profiles() -> dict[str, ModelProfile]:
    return {
        "4k": ModelProfile(model="a", context_tokens=4096),
        "32k": ModelProfile(model="b", context_tokens=32768),
        "128k": ModelProfile(model="c", context_tokens=131072),
        "256k": ModelProfile(model="d", context_tokens=262144),
    }


def test_normalizes_log_level_and_validates_inventory_cache() -> None:
    config = AppConfig(profiles=_valid_profiles(), log_level="warning")
    assert config.log_level == "WARNING"
    with pytest.raises(ValueError, match="log_level"):
        AppConfig(profiles=_valid_profiles(), log_level="TRACE")
    with pytest.raises(ValueError, match="inventory_cache_seconds"):
        AppConfig(
            profiles=_valid_profiles(),
            limits=Limits(inventory_cache_seconds=301),
        )


@pytest.mark.parametrize(
    "context,reserve",
    [(4096, 4096), (4096, 3800)],
)
def test_rejects_insufficient_context_budget(context: int, reserve: int) -> None:
    profiles = _valid_profiles()
    profiles["4k"] = ModelProfile(
        model="a", context_tokens=context, completion_tokens=reserve
    )
    with pytest.raises(ValueError, match="completion_tokens|prompt budget"):
        AppConfig(profiles=profiles)


def test_rejects_conflicting_allowed_model_budget() -> None:
    with pytest.raises(ValueError, match="different allowed-model budget"):
        AppConfig(
            profiles=_valid_profiles(),
            allowed_models={"b": 8192},
        )


def test_rejects_allowed_model_smaller_than_default_completion_reserve() -> None:
    with pytest.raises(ValueError, match="completion_tokens"):
        AppConfig(profiles=_valid_profiles(), allowed_models={"x": 1024})


@pytest.mark.parametrize(
    "token_env",
    [
        {"BadName": "GOOD_NAME"},
        {"codex": "bad-name"},
    ],
)
def test_rejects_invalid_token_environment_names(token_env) -> None:
    with pytest.raises(ValueError, match="token_env"):
        AppConfig(profiles=_valid_profiles(), token_env=token_env)


def test_allowed_models_accept_integer_and_mapping_forms() -> None:
    config = AppConfig(
        profiles=_valid_profiles(),
        allowed_models={
            "model-a": 8192,
            "model-b": {"context_tokens": 16384, "completion_tokens": 1024},
        },
    )
    assert config.allowed_models["model-a"].context_tokens == 8192
    assert config.allowed_models["model-b"].completion_tokens == 1024


def test_credentials_reject_non_ascii_tokens(monkeypatch) -> None:
    config = AppConfig(
        profiles=_valid_profiles(),
        token_env={"codex": "CODEX", "claude-code": "CLAUDE"},
    )
    monkeypatch.setenv("CODEX", "café" * 8)
    monkeypatch.setenv("CLAUDE", "d" * 32)
    with pytest.raises(ValueError, match="printable ASCII"):
        config.credentials()


PLACEHOLDER_MESSAGE = (
    "model tag placeholders must be replaced with exact names from `ollama list`"
)
EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config.example.yaml"


def test_example_config_fails_only_on_placeholders() -> None:
    with pytest.raises(ValueError) as exc_info:
        load_config(EXAMPLE_CONFIG)
    assert PLACEHOLDER_MESSAGE in str(exc_info.value)
    assert "conflicting" not in str(exc_info.value)


@pytest.mark.parametrize(
    "tags",
    [
        ["shared:tag"] * 4,
        ["tag:4k", "tag:32k", "tag:128k", "tag:256k"],
    ],
)
def test_example_config_with_real_tags_loads(tmp_path: Path, tags: list[str]) -> None:
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8")
    for tag in tags:
        text = text.replace("SET_FROM_OLLAMA_LIST", tag, 1)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(text, encoding="utf-8")
    config = load_config(config_path)
    assert [profile.model for profile in config.profiles.values()] == tags


@pytest.mark.parametrize("tag", ["SET_FROM_OLLAMA_LIST", "REPLACE_WITH_TAG_4K"])
def test_rejects_placeholder_tags(tag: str) -> None:
    profiles = _valid_profiles()
    profiles["4k"] = ModelProfile(model=tag, context_tokens=4096)
    with pytest.raises(ValueError, match="placeholders must be replaced"):
        AppConfig(profiles=profiles)
    with pytest.raises(ValueError, match="placeholders must be replaced"):
        AppConfig(profiles=_valid_profiles(), allowed_models={tag: 8192})


def test_allowed_model_sharing_profile_tag_must_match_one_profile_budget() -> None:
    shared = {
        name: ModelProfile(model="shared:tag", context_tokens=budget)
        for name, budget in {
            "4k": 4096,
            "32k": 32768,
            "128k": 131072,
            "256k": 262144,
        }.items()
    }
    config = AppConfig(profiles=shared, allowed_models={"shared:tag": 32768})
    assert config.allowed_models["shared:tag"].context_tokens == 32768
    with pytest.raises(ValueError, match="different allowed-model budget"):
        AppConfig(profiles=shared, allowed_models={"shared:tag": 8192})
