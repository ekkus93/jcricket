import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "init_credentials.py"


def _values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )


def _setup(tmp_path: Path, extra: str = "") -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    credential_dir = home / ".config/second-brain"
    credential_dir.mkdir(parents=True)
    user_file = credential_dir / "credentials.env"
    user_file.write_text(
        f"CODEX_MCP_TOKEN={'a' * 64}\nCLAUDE_CODE_MCP_TOKEN={'b' * 64}\n{extra}",
        encoding="utf-8",
    )
    user_file.chmod(0o600)
    service_dir = tmp_path / "etc"
    service_dir.mkdir()
    service_file = service_dir / "credentials.env"
    service_file.write_text(user_file.read_text(encoding="utf-8"), encoding="utf-8")
    service_file.chmod(0o640)
    return home, user_file, service_file


def _rotate(home: Path, service_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rotate",
            "--service-file",
            str(service_file),
        ],
        capture_output=True,
        text=True,
        env=os.environ | {"HOME": str(home)},
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_three_consecutive_rotations_keep_previous_tokens_in_backup(
    tmp_path: Path,
) -> None:
    home, user_file, service_file = _setup(tmp_path)
    for _ in range(3):
        previous_user = _values(user_file)
        previous_service = _values(service_file)
        result = _rotate(home, service_file)
        assert result.returncode == 0, result.stderr
        user_backup = user_file.with_name("credentials.env.bak")
        service_backup = service_file.with_name("credentials.env.bak")
        assert _values(user_backup) == previous_user
        assert _values(service_backup) == previous_service
        assert _values(user_file) == _values(service_file)
        assert _values(user_file)["CODEX_MCP_TOKEN"] != previous_user["CODEX_MCP_TOKEN"]
        assert _mode(user_file) == 0o600
        assert _mode(service_file) == 0o640
        assert _mode(user_backup) == 0o600
        assert _mode(service_backup) == 0o600


def test_rotation_preserves_other_lines_and_comments(tmp_path: Path) -> None:
    extra = "# keep this comment\nCHATGPT_MCP_TOKEN=" + "c" * 64 + "\n"
    home, user_file, service_file = _setup(tmp_path, extra)
    result = _rotate(home, service_file)
    assert result.returncode == 0, result.stderr
    for path in (user_file, service_file):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[2:] == ["# keep this comment", "CHATGPT_MCP_TOKEN=" + "c" * 64]
        assert lines[0].startswith("CODEX_MCP_TOKEN=")
        assert lines[1].startswith("CLAUDE_CODE_MCP_TOKEN=")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_service_directory_leaves_user_file_unchanged(
    tmp_path: Path,
) -> None:
    home, user_file, service_file = _setup(tmp_path)
    original = user_file.read_text(encoding="utf-8")
    service_file.parent.chmod(0o500)
    try:
        result = _rotate(home, service_file)
    finally:
        service_file.parent.chmod(0o700)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert str(service_file.parent) in result.stderr
    assert user_file.read_text(encoding="utf-8") == original


def test_failed_replacement_restores_already_rotated_files(
    tmp_path: Path, monkeypatch
) -> None:
    spec = importlib.util.spec_from_file_location("init_credentials", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _home, user_file, service_file = _setup(tmp_path)
    original_user = user_file.read_text(encoding="utf-8")
    original_service = service_file.read_text(encoding="utf-8")
    real_replace = os.replace

    def failing_replace(source, destination):
        if Path(destination) == service_file:
            raise PermissionError("simulated replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", failing_replace)
    with pytest.raises(module.RotationError, match=str(service_file)):
        module.rotate([user_file, service_file], {"CODEX_MCP_TOKEN": "n" * 64})
    assert user_file.read_text(encoding="utf-8") == original_user
    assert service_file.read_text(encoding="utf-8") == original_service
    assert sorted(path.name for path in user_file.parent.iterdir()) == [
        "credentials.env",
        "credentials.env.bak",
    ]
