import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_auth_header_helper_reads_private_file_without_logging_token(
    tmp_path: Path,
) -> None:
    """The one subprocess test: the helper really runs as a program."""
    credentials = tmp_path / "credentials.env"
    token = "c" * 64
    credentials.write_text(f"CODEX_MCP_TOKEN={token}\n", encoding="utf-8")
    credentials.chmod(0o600)
    env = os.environ | {"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)}
    result = subprocess.run(
        [sys.executable, "deploy/auth_headers.py", "codex"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"Authorization": f"Bearer {token}"}
    assert token not in result.stderr
    assert "Traceback" not in result.stderr


def test_auth_header_helper_rejects_loose_file_permissions(
    tmp_path: Path, load_script, run_main
) -> None:
    credentials = tmp_path / "credentials.env"
    credentials.write_text(f"CODEX_MCP_TOKEN={'d' * 64}\n", encoding="utf-8")
    credentials.chmod(0o644)
    result = run_main(
        load_script("deploy/auth_headers.py"),
        "codex",
        env={"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)},
    )
    assert result.returncode == 1
    assert "permissions must be 600" in result.stderr
    assert "d" * 64 not in result.stderr


@pytest.fixture
def helper(tmp_path: Path, load_script, run_main):
    """Run the header helper's ``main()`` in-process against a private token file."""
    module = load_script("deploy/auth_headers.py")

    def run(*args: str):
        credentials = tmp_path / "credentials.env"
        credentials.write_text(f"CHATGPT_MCP_TOKEN={'e' * 64}\n", encoding="utf-8")
        credentials.chmod(0o600)
        return run_main(
            module, *args, env={"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)}
        )

    return run


def test_auth_header_helper_accepts_other_principal_with_env_var(helper) -> None:
    result = helper("chatgpt", "--env-var", "CHATGPT_MCP_TOKEN")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"Authorization": "Bearer " + "e" * 64}


def test_auth_header_helper_requires_env_var_for_other_principals(helper) -> None:
    result = helper("chatgpt")
    assert result.returncode == 2
    assert "--env-var is required for principal chatgpt" in result.stderr


def test_auth_header_helper_rejects_invalid_principal_name(helper) -> None:
    result = helper("Not_Valid", "--env-var", "CHATGPT_MCP_TOKEN")
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.fixture
def run_helper(tmp_path: Path, load_script, run_main):
    """Run ``main()`` in-process with arbitrary credential-file content."""
    module = load_script("deploy/auth_headers.py")

    def run(content: str | None, *args: str):
        credentials = tmp_path / "credentials.env"
        if content is not None:
            credentials.write_text(content, encoding="utf-8")
            credentials.chmod(0o600)
        return run_main(
            module, *args, env={"SECOND_BRAIN_CREDENTIALS_FILE": str(credentials)}
        )

    return run


def test_auth_header_helper_rejects_invalid_env_var_name(run_helper) -> None:
    result = run_helper(
        f"CODEX_MCP_TOKEN={'f' * 64}\n", "codex", "--env-var", "bad-name"
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "environment variable name is invalid" in result.stderr
    assert "f" * 64 not in result.stderr


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "CODEX_MCP_TOKEN " + "g" * 64 + "\n",
            "cannot read local MCP credentials: credential file contains a "
            "malformed assignment",
        ),
        (
            "CODEX_MCP_TOKEN=" + "h" * 20 + "\n",
            "cannot read local MCP credentials: configured bearer token is missing "
            "or too short",
        ),
    ],
)
def test_auth_header_helper_rejects_bad_credential_files(
    run_helper, content: str, message: str
) -> None:
    result = run_helper(content, "codex")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == message
    assert "g" * 64 not in result.stderr and "h" * 20 not in result.stderr


def test_auth_header_helper_reports_missing_file(run_helper) -> None:
    result = run_helper(None, "codex")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("cannot read local MCP credentials:")


def test_auth_header_helper_strips_quotes(run_helper) -> None:
    token = "q" * 48
    result = run_helper(f'CODEX_MCP_TOKEN="{token}"\n', "codex")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"Authorization": f"Bearer {token}"}
