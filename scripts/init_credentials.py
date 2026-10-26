"""Create a private credentials environment file without overwriting an existing one."""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--service-file", type=Path)
    args = parser.parse_args()
    path = Path.home() / ".config/second-brain/credentials.env"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    body = (
        f"CODEX_MCP_TOKEN={secrets.token_hex(32)}\n"
        f"CLAUDE_CODE_MCP_TOKEN={secrets.token_hex(32)}\n"
    )
    if args.rotate:
        targets = [path, *([args.service_file] if args.service_file else [])]
        for target in targets:
            _rotate_file(target, body)
        print(f"Rotated private credentials file: {path}")
        if args.service_file:
            print(f"Also rotated service credentials: {args.service_file}")
        print("Restart the service, then reconnect each MCP client.")
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as credentials_file:
                credentials_file.write(body)
        finally:
            path.chmod(0o600)
        print(f"Created private credentials file: {path}")
    path.chmod(0o600)
    print(f"File mode: {stat.S_IMODE(path.stat().st_mode):04o}")


def _rotate_file(path: Path, contents: str) -> None:
    if not path.exists():
        raise SystemExit(f"cannot rotate: credentials file does not exist: {path}")
    previous = path.stat()
    backup = path.with_name(path.name + ".bak")
    descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as backup_file:
        backup_file.write(path.read_bytes())
        backup_file.flush()
        os.fsync(backup_file.fileno())
    descriptor, temporary = tempfile.mkstemp(prefix=".credentials.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            os.fchown(descriptor, previous.st_uid, previous.st_gid)
        os.fchmod(descriptor, stat.S_IMODE(previous.st_mode))
        with os.fdopen(descriptor, "w", encoding="utf-8") as credentials_file:
            credentials_file.write(contents)
            credentials_file.flush()
            os.fsync(credentials_file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
