"""Create a private credentials environment file without overwriting an existing one."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path


def main() -> None:
    path = Path.home() / ".config/second-brain/credentials.env"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    body = (
        f"CODEX_MCP_TOKEN={secrets.token_hex(32)}\n"
        f"CLAUDE_CODE_MCP_TOKEN={secrets.token_hex(32)}\n"
    )
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as credentials_file:
            credentials_file.write(body)
    finally:
        path.chmod(0o600)
    path.chmod(0o600)
    print(f"Created private credentials file: {path}")
    print(f"File mode: {stat.S_IMODE(path.stat().st_mode):04o}")


if __name__ == "__main__":
    main()
