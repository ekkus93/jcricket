import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

CODEX_TOKEN = "TOKENMARKERcodex" + "c" * 32
CLAUDE_TOKEN = "TOKENMARKERclaude" + "d" * 32
BAD_TOKEN = "TOKENMARKERinvalid" + "x" * 32
QUESTION = "QUESTIONMARKER what is the plan?"
CONTEXT = "CONTEXTMARKER private design notes"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_server_output_never_contains_prompt_or_token_markers(tmp_path: Path) -> None:
    port = _free_port()
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""ollama_base_url: http://127.0.0.1:9
database_path: {tmp_path / "db.sqlite3"}
port: {port}
log_level: DEBUG
profiles:
  4k: {{model: a, context_tokens: 4096}}
  32k: {{model: b, context_tokens: 32768}}
  128k: {{model: c, context_tokens: 131072}}
  256k: {{model: d, context_tokens: 262144}}
token_env: {{codex: LEAK_CODEX_TOKEN, claude-code: LEAK_CLAUDE_TOKEN}}
""",
        encoding="utf-8",
    )
    log_path = tmp_path / "server.log"
    environment = os.environ | {
        "LEAK_CODEX_TOKEN": CODEX_TOKEN,
        "LEAK_CLAUDE_TOKEN": CLAUDE_TOKEN,
    }
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "second_brain_mcp.cli",
                "--config",
                str(config),
                "serve",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 20
            while True:
                try:
                    if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert process.poll() is None, log_path.read_text(encoding="utf-8")
                assert time.monotonic() < deadline, "server did not start"
                time.sleep(0.1)

            headers = {
                "Host": "127.0.0.1",
                "Accept": "application/json, text/event-stream",
            }
            ask = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ask_second_brain",
                    "arguments": {"question": QUESTION, "context": CONTEXT},
                },
            }
            with httpx.Client(base_url=base, timeout=10) as client:
                unauthenticated = client.post("/mcp", json=ask, headers=headers)
                invalid = client.post(
                    "/mcp",
                    json=ask,
                    headers=headers | {"Authorization": "Bearer " + BAD_TOKEN},
                )
                valid = client.post(
                    "/mcp",
                    json=ask,
                    headers=headers | {"Authorization": "Bearer " + CODEX_TOKEN},
                )
                query = client.post(
                    "/mcp?note=QUERYMARKER",
                    json=ask,
                    headers=headers | {"Authorization": "Bearer " + CODEX_TOKEN},
                )
        finally:
            process.terminate()
            process.wait(timeout=10)

    assert unauthenticated.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["result"]["content"][0]["text"] == (
        "ollama_unavailable: Ollama is unavailable or rejected the request"
    )
    assert query.status_code == 200
    output = log_path.read_text(encoding="utf-8")
    assert "POST /mcp" in output, "uvicorn access log was not captured"
    for marker in ("QUESTIONMARKER", "CONTEXTMARKER", "TOKENMARKER"):
        assert marker not in output
