# Local client setup

The local server exposes Streamable HTTP at `http://127.0.0.1:8000/mcp` and uses independent tokens for `codex` and `claude-code`. Create the user credential file once with `uv run python scripts/init_credentials.py`; it writes `~/.config/second-brain/credentials.env` with mode `0600`. It refuses to overwrite an existing file. Start the server with `scripts/run_local.sh`. The helper reads the user credential file and emits only the requested bearer header as JSON; it never prints tokens to stderr or a log. For systemd, `/etc/second-brain/credentials.env` is a separate service credential file, read by systemd and normally owned by `root:second-brain` with mode `0640`. The helper does not read the service file.

## Codex

Add the server to user configuration with `codex mcp add second-brain --url http://127.0.0.1:8000/mcp`. In `~/.codex/config.toml`, add `http_headers_helper = "python3 /absolute/path/to/jcricket/deploy/auth_headers.py codex"` under `[mcp_servers.second-brain]`. Check `codex mcp list`; then start a fresh Codex session and verify `list_models`, a question, a continuation, and persistence across restart.

## Claude Code

Add the user-scoped server with `claude mcp add-json second-brain '{"type":"http","url":"http://127.0.0.1:8000/mcp","headersHelper":"python3 /absolute/path/to/jcricket/deploy/auth_headers.py claude-code"}' --scope user`. Verify `claude mcp get second-brain` and `/mcp`, then run the same tool and persistence checks in a fresh session.

Rotate local tokens with `uv run python scripts/init_credentials.py --rotate`. It replaces only the `CODEX_MCP_TOKEN` and `CLAUDE_CODE_MCP_TOKEN` lines, keeps every other line and comment, and saves the previous file as a private `.bak` (replaced on each rotation, so it always holds the immediately previous tokens). If systemd uses the service credential file, include `--service-file /etc/second-brain/credentials.env` (with suitable privileges) so both files get the same new tokens. Rotation is all-or-nothing: every file is staged before any is replaced, and if a later replacement fails, earlier files are restored and the command exits 1. Then restart the service and reconnect each client.

For a principal other than `codex` or `claude-code`, pass the environment variable name explicitly, for example `python3 deploy/auth_headers.py chatgpt --env-var CHATGPT_MCP_TOKEN`; the helper requires `--env-var` for any name outside its default map and accepts lowercase names matching `[a-z][a-z0-9-]{0,31}`. Project directories and committed configs must never contain real tokens. If a client reports an authorization failure, verify the helper path, principal name (`codex` or `claude-code`), credential file permissions, and that the service was restarted after rotation. Confirm available models with `list_models` before selecting a profile.

## ChatGPT (not yet available)

There is no working ChatGPT connection guide yet. Hosted ChatGPT cannot reach `127.0.0.1`, and this project currently implements only local bearer-token authentication for Codex and Claude Code; remote HTTPS ingress, ChatGPT authentication, and a distinct `chatgpt` principal are not implemented or tested. Do not expose the local endpoint or treat a static bearer token as a remote ChatGPT solution. ChatGPT setup requires a separately designed and tested remote transport/authentication path plus access to an eligible ChatGPT workspace.

For setup, database backup, administration, and troubleshooting, see [`../operations.md`](../operations.md). Ollama model tags are machine-specific; never copy another workstation's private `config.yaml` blindly.
