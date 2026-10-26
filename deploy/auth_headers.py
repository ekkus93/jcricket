"""Read one local principal token and print a bearer header for MCP clients."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

TOKEN_ENV = {"codex": "CODEX_MCP_TOKEN", "claude-code": "CLAUDE_CODE_MCP_TOKEN"}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in TOKEN_ENV:
        print("usage: auth_headers.py codex|claude-code", file=sys.stderr)
        return 2
    credential_path = Path(
        os.environ.get(
            "SECOND_BRAIN_CREDENTIALS_FILE",
            "~/.config/second-brain/credentials.env",
        )
    ).expanduser()
    try:
        mode = stat.S_IMODE(credential_path.stat().st_mode)
        if mode & 0o077:
            raise ValueError("credential file permissions must be 600 or stricter")
        values = _read_environment_file(credential_path)
        token = values.get(TOKEN_ENV[sys.argv[1]], "")
        if len(token) < 32:
            raise ValueError("configured bearer token is missing or too short")
    except (OSError, ValueError) as exc:
        print(f"cannot read local MCP credentials: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"Authorization": f"Bearer {token}"}))
    return 0


def _read_environment_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator:
            raise ValueError("credential file contains a malformed assignment")
        values[name.strip()] = value.strip().strip("\"'")
    return values


if __name__ == "__main__":
    raise SystemExit(main())
