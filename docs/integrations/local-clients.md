# Local client setup

The local server exposes Streamable HTTP at `http://127.0.0.1:8000/mcp` and uses independent tokens for `codex` and `claude-code`. Create the private credential file once with `uv run python scripts/init_credentials.py`; it writes `~/.config/second-brain/credentials.env` with mode `0600`. It refuses to overwrite an existing file. Start the server with `scripts/run_local.sh`. The helper reads that private file and emits only the requested bearer header as JSON; it never prints tokens to stderr or a log.

## Codex

Add the server to user configuration with `codex mcp add second-brain --url http://127.0.0.1:8000/mcp`. In `~/.codex/config.toml`, add `http_headers_helper = "python3 /absolute/path/to/jcricket/deploy/auth_headers.py codex"` under `[mcp_servers.second-brain]`. Check `codex mcp list`; then start a fresh Codex session and verify `list_models`, a question, a continuation, and persistence across restart.

## Claude Code

Add the user-scoped server with `claude mcp add-json second-brain '{"type":"http","url":"http://127.0.0.1:8000/mcp","headersHelper":"python3 /absolute/path/to/jcricket/deploy/auth_headers.py claude-code"}' --scope user`. Verify `claude mcp get second-brain` and `/mcp`, then run the same tool and persistence checks in a fresh session.

The CLI helper reads the same credential file used by the system service, so tokens remain outside client configuration and source control. Rotate tokens by updating the private credential file and service environment, restarting the server, and reconnecting each client. Project directories and committed configs must never contain real tokens. If a client reports an authorization failure, verify the helper path, principal name (`codex` or `claude-code`), credential file permissions, and that the service was restarted after rotation. Confirm available models with `list_models` before selecting a profile.

## ChatGPT (not yet available)

There is no working ChatGPT connection guide yet. Hosted ChatGPT cannot reach `127.0.0.1`, and this project currently implements only local bearer-token authentication for Codex and Claude Code; remote HTTPS ingress, ChatGPT authentication, and a distinct `chatgpt` principal are not implemented or tested. Do not expose the local endpoint or treat a static bearer token as a remote ChatGPT solution. ChatGPT setup requires a separately designed and tested remote transport/authentication path plus access to an eligible ChatGPT workspace.

For setup, database backup, administration, and troubleshooting, see [`../operations.md`](../operations.md). Ollama model tags are machine-specific; never copy another workstation's private `config.yaml` blindly.
