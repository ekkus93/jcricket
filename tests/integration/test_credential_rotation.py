import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "init_credentials.py"


def _module():
    spec = importlib.util.spec_from_file_location("init_credentials", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    module = _module()
    _home, user_file, service_file = _setup(tmp_path)
    original_user = user_file.read_text(encoding="utf-8")
    original_service = service_file.read_text(encoding="utf-8")
    real_replace = os.replace

    def failing_replace(source, destination):
        if Path(destination) == service_file:
            raise PermissionError("simulated replace failure")
        return real_replace(source, destination)

    # `module.os` is the process-wide `os` module; monkeypatch restores the patch.
    monkeypatch.setattr(module.os, "replace", failing_replace)
    with pytest.raises(module.RotationError, match=str(service_file)):
        module.rotate([user_file, service_file], {"CODEX_MCP_TOKEN": "n" * 64})
    assert user_file.read_text(encoding="utf-8") == original_user
    assert service_file.read_text(encoding="utf-8") == original_service
    assert sorted(path.name for path in user_file.parent.iterdir()) == [
        "credentials.env",
        "credentials.env.bak",
    ]


def _init(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=os.environ | {"HOME": str(home)},
    )


def test_rotate_without_existing_file_fails_cleanly(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _init(home, "--rotate")
    path = home / ".config/second-brain/credentials.env"
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.strip() == (
        f"cannot rotate credentials: credentials file does not exist: {path}"
    )


def test_create_refuses_existing_file_without_traceback(tmp_path: Path) -> None:
    home, user_file, _service_file = _setup(tmp_path)
    original = user_file.read_text(encoding="utf-8")
    result = _init(home)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.strip() == (
        f"credentials file already exists: {user_file}; "
        "use --rotate to replace its tokens"
    )
    assert user_file.read_text(encoding="utf-8") == original


def test_create_writes_private_file_with_distinct_tokens(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    result = _init(home)
    path = home / ".config/second-brain/credentials.env"
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"Created private credentials file: {path}",
        "File mode: 0600",
    ]
    values = _values(path)
    assert set(values) == {"CODEX_MCP_TOKEN", "CLAUDE_CODE_MCP_TOKEN"}
    assert all(len(token) == 64 for token in values.values())
    assert values["CODEX_MCP_TOKEN"] != values["CLAUDE_CODE_MCP_TOKEN"]
    assert _mode(path) == 0o600
    assert _mode(path.parent) == 0o700


def test_rotate_user_file_only(tmp_path: Path) -> None:
    home, user_file, service_file = _setup(tmp_path)
    service_before = service_file.read_text(encoding="utf-8")
    result = _init(home, "--rotate")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"Rotated private credentials file: {user_file}",
        "Restart the service, then reconnect each MCP client.",
        "File mode: 0600",
    ]
    assert _values(user_file)["CODEX_MCP_TOKEN"] != "a" * 64
    assert service_file.read_text(encoding="utf-8") == service_before


def test_rotation_as_root_preserves_file_owner(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    # `module.os` is the process-wide `os` module; monkeypatch restores the patch.
    _home, user_file, _service_file = _setup(tmp_path)
    owner = user_file.stat()
    chowned: list[tuple[int, int]] = []
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        module.os, "fchown", lambda _fd, uid, gid: chowned.append((uid, gid))
    )
    module.rotate([user_file], {"CODEX_MCP_TOKEN": "n" * 64})
    assert chowned == [(owner.st_uid, owner.st_gid)]
    assert _values(user_file)["CODEX_MCP_TOKEN"] == "n" * 64


def test_staging_failure_removes_temporary_files(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    # `module.os` is the process-wide `os` module; monkeypatch restores the patch.
    _home, user_file, _service_file = _setup(tmp_path)
    original = user_file.read_text(encoding="utf-8")

    def failing_fsync(_fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(module.os, "fsync", failing_fsync)
    with pytest.raises(module.RotationError, match="cannot stage"):
        module.rotate([user_file], {"CODEX_MCP_TOKEN": "n" * 64})
    assert user_file.read_text(encoding="utf-8") == original
    assert sorted(path.name for path in user_file.parent.iterdir()) == [
        "credentials.env"
    ]
