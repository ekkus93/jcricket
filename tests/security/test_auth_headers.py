import json
import os
import subprocess
import sys
from pathlib import Path


def test_auth_header_helper_reads_private_file_without_logging_token(
    tmp_path: Path,
) -> None:
    credentials = tmp_path / "credentials.env"
    token = "c" * 64
    credentials.write_text(f"CODEX_MCP_TOKEN={token}\n", encoding="utf-8")
    credentials.chmod(0o600)
    env = os.environ | {"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)}
    result = subprocess.run(
        [sys.executable, "deploy/auth_headers.py", "codex"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert json.loads(result.stdout) == {"Authorization": f"Bearer {token}"}
    assert token not in result.stderr


def test_auth_header_helper_rejects_loose_file_permissions(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.env"
    credentials.write_text(f"CODEX_MCP_TOKEN={'d' * 64}\n", encoding="utf-8")
    credentials.chmod(0o644)
    result = subprocess.run(
        [sys.executable, "deploy/auth_headers.py", "codex"],
        capture_output=True,
        text=True,
        env=os.environ | {"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)},
    )
    assert result.returncode == 1
    assert "permissions must be 600" in result.stderr
