import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from starlette.testclient import TestClient

from second_brain_mcp.config import AppConfig, ModelProfile
from second_brain_mcp.server import create_app


def test_auth_headers_supports_custom_environment_variable(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.env"
    credentials.write_text("CUSTOM_TOKEN=" + "z" * 40 + "\n", encoding="utf-8")
    credentials.chmod(0o600)
    environment = os.environ | {"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)}
    result = subprocess.run(
        [
            sys.executable,
            "deploy/auth_headers.py",
            "codex",
            "--env-var",
            "CUSTOM_TOKEN",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    assert json.loads(result.stdout) == {"Authorization": "Bearer " + "z" * 40}


def test_rotation_atomically_replaces_tokens_and_preserves_private_backup(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    credential_dir = home / ".config/second-brain"
    credential_dir.mkdir(parents=True)
    credentials = credential_dir / "credentials.env"
    old_codex = "a" * 64
    old_claude = "b" * 64
    credentials.write_text(
        f"CODEX_MCP_TOKEN={old_codex}\nCLAUDE_CODE_MCP_TOKEN={old_claude}\n",
        encoding="utf-8",
    )
    credentials.chmod(0o600)
    service_credentials = tmp_path / "service-credentials.env"
    service_credentials.write_text(
        credentials.read_text(encoding="utf-8"), encoding="utf-8"
    )
    service_credentials.chmod(0o640)
    environment = os.environ | {"HOME": str(home)}
    subprocess.run(
        [
            sys.executable,
            "scripts/init_credentials.py",
            "--rotate",
            "--service-file",
            str(service_credentials),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    backup = credentials.with_name("credentials.env.bak")
    assert backup.read_text(encoding="utf-8").find(old_codex) >= 0
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(credentials.stat().st_mode) == 0o600
    assert stat.S_IMODE(service_credentials.stat().st_mode) == 0o640
    assert (
        stat.S_IMODE(
            service_credentials.with_name(service_credentials.name + ".bak")
            .stat()
            .st_mode
        )
        == 0o600
    )
    assert service_credentials.read_text(encoding="utf-8") == credentials.read_text(
        encoding="utf-8"
    )
    values = dict(line.split("=", 1) for line in credentials.read_text().splitlines())
    assert values["CODEX_MCP_TOKEN"] != old_codex
    assert values["CLAUDE_CODE_MCP_TOKEN"] != old_claude
    assert values["CODEX_MCP_TOKEN"] != values["CLAUDE_CODE_MCP_TOKEN"]

    monkeypatch.setenv("CODEX_TEST", values["CODEX_MCP_TOKEN"])
    monkeypatch.setenv("CLAUDE_TEST", values["CLAUDE_CODE_MCP_TOKEN"])
    config = AppConfig(
        database_path=tmp_path / "db.sqlite3",
        profiles={
            name: ModelProfile(model=f"tag:{name}", context_tokens=size)
            for name, size in {
                "4k": 4096,
                "32k": 32768,
                "128k": 131072,
                "256k": 262144,
            }.items()
        },
        token_env={"codex": "CODEX_TEST", "claude-code": "CLAUDE_TEST"},
    )
    app = create_app(config)
    with TestClient(app) as client:
        headers = {
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Accept": "application/json, text/event-stream",
        }
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        old = client.post(
            "/mcp",
            json=body,
            headers=headers | {"Authorization": "Bearer " + old_codex},
        )
        current = client.post(
            "/mcp",
            json=body,
            headers=headers | {"Authorization": "Bearer " + values["CODEX_MCP_TOKEN"]},
        )
    assert old.status_code == 401
    assert current.status_code == 200
