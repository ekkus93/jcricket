from pathlib import Path

import pytest

from second_brain_mcp.config import load_config


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
