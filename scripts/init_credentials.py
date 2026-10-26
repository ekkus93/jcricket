"""Create or rotate private credentials environment files without exposing tokens."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path

TOKEN_NAMES = ("CODEX_MCP_TOKEN", "CLAUDE_CODE_MCP_TOKEN")


class RotationError(RuntimeError):
    """Rotation failed; every already-replaced file has been restored."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--service-file", type=Path)
    args = parser.parse_args()
    path = Path.home() / ".config/second-brain/credentials.env"
    tokens = {name: secrets.token_hex(32) for name in TOKEN_NAMES}
    if args.rotate:
        targets = [path, *([args.service_file] if args.service_file else [])]
        try:
            rotate(targets, tokens)
        except (OSError, RotationError) as exc:
            print(f"cannot rotate credentials: {exc}", file=sys.stderr)
            return 1
        print(f"Rotated private credentials file: {path}")
        if args.service_file:
            print(f"Also rotated service credentials: {args.service_file}")
        print("Restart the service, then reconnect each MCP client.")
    else:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as credentials_file:
            credentials_file.write(
                "".join(f"{name}={token}\n" for name, token in tokens.items())
            )
        print(f"Created private credentials file: {path}")
    print(f"File mode: {stat.S_IMODE(path.stat().st_mode):04o}")
    return 0


def rotate(targets: list[Path], tokens: dict[str, str]) -> None:
    """Replace token lines in every target, or leave every target unchanged."""
    staged: list[tuple[Path, bytes, str, str]] = []
    try:
        for target in targets:
            if not target.exists():
                raise RotationError(f"credentials file does not exist: {target}")
            previous = target.read_bytes()
            status = target.stat()
            updated = _replace_tokens(previous.decode("utf-8"), tokens)
            new_file = _stage(target, updated.encode("utf-8"), status, private=False)
            backup = _stage(target, previous, status, private=True)
            staged.append((target, previous, new_file, backup))
    except OSError as exc:
        _discard(staged)
        raise RotationError(f"cannot stage {exc.filename or target}: {exc}") from exc
    except BaseException:
        _discard(staged)
        raise

    replaced: list[tuple[Path, bytes]] = []
    for index, (target, previous, new_file, backup) in enumerate(staged):
        try:
            os.replace(backup, target.with_name(target.name + ".bak"))
            os.replace(new_file, target)
        except OSError as exc:
            _discard(staged[index:])
            for done, content in replaced:
                restore = _stage(done, content, done.stat(), private=False)
                os.replace(restore, done)
            raise RotationError(
                f"cannot replace {target}: {exc}; earlier files were restored"
            ) from exc
        replaced.append((target, previous))


def _replace_tokens(text: str, tokens: dict[str, str]) -> str:
    lines = text.splitlines()
    remaining = dict(tokens)
    for index, line in enumerate(lines):
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match[1] in remaining:
            lines[index] = f"{match[1]}={remaining.pop(match[1])}"
    lines.extend(f"{name}={token}" for name, token in remaining.items())
    return "\n".join(lines) + "\n"


def _stage(
    target: Path, contents: bytes, status: os.stat_result, *, private: bool
) -> str:
    descriptor, temporary = tempfile.mkstemp(prefix=".credentials.", dir=target.parent)
    try:
        os.fchmod(descriptor, 0o600)
        if not private and hasattr(os, "geteuid") and os.geteuid() == 0:
            os.fchown(descriptor, status.st_uid, status.st_gid)
        if not private:
            os.fchmod(descriptor, stat.S_IMODE(status.st_mode))
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return temporary


def _discard(staged: list[tuple[Path, bytes, str, str]]) -> None:
    for _target, _previous, *temporaries in staged:
        for temporary in temporaries:
            if os.path.exists(temporary):
                os.unlink(temporary)


if __name__ == "__main__":
    raise SystemExit(main())
