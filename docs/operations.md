# Operations

## Local development

Use Python 3.12 managed by `uv`; from the repository root run `uv sync --locked`, copy `config.example.yaml` to the ignored `config.yaml`, and replace each placeholder with the exact output of `ollama list`. Create local credentials with `uv run python scripts/init_credentials.py`, then start with `scripts/run_local.sh`. Check setup with `uv run second-brain --config config.yaml check-config`. The default listener is `127.0.0.1:18765`; the default database is `~/.local/share/second-brain/conversations.sqlite3`.

### Model variants and context windows

Each profile needs its own model tag whose real context window is at least the profile's budget. Some models, including Qwen3.5, ignore the request's `num_ctx`, so build one variant per context size (for example, a Modelfile with `PARAMETER num_ctx 32768`) and map each profile to its own variant. No tag may be mapped by two profiles, and an allowed model that shares a profile's tag must use that profile's budget.

`check-config` and `serve` ask Ollama (read-only `POST /api/show`) for each configured tag's pinned `num_ctx` and native context length:

- a budget larger than the pinned `num_ctx`, or (when nothing is pinned) larger than the native length, is an error, as is a tag that is not installed;
- a tag that does not pin `num_ctx` gets a warning, because its real window then depends on whether the model honors the request and on Ollama's default context length (`OLLAMA_CONTEXT_LENGTH`);
- if Ollama cannot be reached, `check-config` fails, while `serve` prints a warning and starts anyway.

This check uses its own timeout, `limits.metadata_timeout_seconds` (default 10 s, maximum 120 s), together with `limits.connect_timeout_seconds`, so a slow `/api/show` never waits for the 300 s inference timeout (`limits.request_timeout_seconds`). The check makes one request per configured tag.

## Ubuntu service

The example unit is `deploy/second-brain.service.example`. Install the project and locked environment under `/opt/second-brain`, put runtime configuration in `/etc/second-brain/config.yaml`, and create `/etc/second-brain/credentials.env` with only the service's principal tokens. Set the credential file to `root:second-brain`, mode `0640`, and keep the configuration readable by the service account. Create `/var/lib/second-brain` owned by `second-brain` with mode `0700`; set `database_path` in the service config to `/var/lib/second-brain/conversations.sqlite3`. Review the unit paths and permissions, then install it as `/etc/systemd/system/second-brain.service` and run `systemctl daemon-reload`, `systemctl enable --now second-brain`, and `systemctl status second-brain`. Logs are available with `journalctl -u second-brain`.

The unit example is a starting point, not a verified installation: this development environment does not run systemd. It runs one worker because in-memory admission control and conversation locks require a single process. Keep Ollama bound to loopback and do not expose its API. The working directory must not contain a `.env` file; FastMCP environment overrides are unsupported, and the application passes its security-sensitive SDK settings explicitly.

## Conversation administration and retention

Use the same config as the server: `uv run second-brain --config config.yaml conversations list [--principal codex]`, `show ID`, `get-any ID`, `delete ID`, or `export [ID] [--principal codex] [--output FILE]`. Export files are created with mode `0600` and are never overwritten; without `--output`, JSON is written to stdout. `delete` and `purge` require confirmation unless `--yes` is supplied. `purge --older-than DAYS` uses the explicit age; without it, the configured `retention_days` is used. Retention is never applied automatically by the server. The example timer and service in `deploy/second-brain-purge.*.example` run the purge command daily. Conversations persist on disk and contain user questions and assistant answers. Backups may retain deleted content.

The default selectable profiles use these approximate usable input sizes (before prior conversation history):

| Profile | Context | Completion reserve | Approximate input |
|---|---:|---:|---:|
| `4k` | 4,096 | 1,024 | 2,516 bytes |
| `32k` | 32,768 | 2,048 | 30,164 bytes |
| `128k` | 131,072 | 2,048 | 128,468 bytes |
| `256k` | 262,144 | 2,048 | 259,540 bytes |

Estimates reserve space for the longest system prompt and chat framing; model tokenization can use more. `list_models` returns at most 200 entries and reports `truncated`; configured models remain included. Each HTTP response carries a server-generated `X-Request-ID` for support correlation.

### Tool errors

A failed tool call returns `isError: true` with one text item that is exactly `<code>: <message>`, for example `invalid_input: question must not be empty`. Messages are fixed and never contain prompts, tokens, stack traces, or database rows.

| Code | When it occurs |
|---|---|
| `invalid_input` | Empty or over-long question or context, empty selector, both `model` and `model_profile`, an argument outside its schema (`invalid value for <field>`), or an unknown tool. |
| `conversation_unavailable` | Unknown conversation ID, an ID owned by another principal (indistinguishable from unknown), or a conversation deleted while its turn was running. |
| `model_not_approved` | Unknown profile or a conversation whose stored profile is no longer configured. |
| `model_not_installed` | The selected tag is not in Ollama's `/api/tags`; the message names the profile and tag. |
| `context_too_large` | The current question and context exceed the selection's prompt budget; the message gives the available bytes and suggests a larger profile when one fits. |
| `busy` | `concurrency + queue_depth` requests are already admitted. |
| `ollama_unavailable` | Ollama refused the connection or returned a non-success status. |
| `ollama_timeout` | An Ollama request exceeded its configured timeout. |
| `ollama_bad_response` | Ollama returned malformed, empty, or oversized data. |
| `unauthorized` | A tool ran without an authenticated principal; the HTTP middleware normally rejects such requests first. |
| `internal_error` | Any other failure; only the exception type is logged. |

Caller mistakes (`invalid_input`, `conversation_unavailable`, `model_not_approved`, `context_too_large`) are logged at INFO, backend and capacity problems at WARNING, and `unauthorized` / `internal_error` at ERROR.

## Backup, restore, and removal

Stop the service before copying the SQLite database, including its `-wal` and `-shm` companions if present. For a consistent standalone backup, use SQLite's backup command, for example `sqlite3 conversations.sqlite3 '.backup /secure/backup/second-brain.sqlite3'`; protect the backup as private conversation data. To restore, stop the service, preserve the current database, copy the backup to the configured database path, set ownership to the service account and mode `0600`, and restart. Keep versioned backups before upgrades; schema migrations run when the application opens the database. Test a restored copy before relying on it.

To remove the installation, stop and disable the service, remove its unit and package/configuration/credentials as appropriate, then separately delete `/var/lib/second-brain` or the local database if permanent conversation deletion is intended. Removing software does not automatically erase backups.

## Test coverage

Coverage is measured with `coverage` (a dev dependency), including code the tests run in subprocesses (the CLI, the scripts, and the uvicorn leakage test). Run:

```sh
uv run coverage erase && uv run coverage run -m pytest -q && uv run coverage combine && uv run coverage report
```

Configuration lives in `[tool.coverage.*]` in `pyproject.toml`. The gate is `fail_under = 99.4` with `precision = 1`: coverage rounds the total to one decimal place before comparing, so the report fails as soon as the total rounds to 99.3% or less. (With the default precision of 0, a total of 98.6% would still pass a threshold of 99.) Plain `uv run pytest` does not measure coverage, so it stays fast.

## Troubleshooting

- `401`: check that the client uses its matching principal helper and the server has the same token; rotate credentials with `scripts/init_credentials.py --rotate` (add `--service-file` when systemd uses the service file, so both are rotated together, all-or-nothing, with a private `.bak` of the previous contents), restart the service, and reconnect clients. For principals other than `codex` and `claude-code`, run the helper with `--env-var NAME`.
- `403`: confirm loopback Host/Origin policy and that requests use the configured local URL.
- Missing model/profile: check the exact tag with `ollama list`; direct model selection accepts any installed tag. Check loaded models with `ollama ps`.
- Timeout or queue-full response: verify Ollama is responsive and lower inference concurrency; large context profiles can take longer and consume more memory.
- MCP Inspector prompts for OAuth: Inspector defaults to OAuth; for this local bearer-token server, pass an Authorization header using a private local test setup.

See [local client setup](integrations/local-clients.md) for Codex and Claude Code configuration. The ChatGPT section describes a connection through an OpenAI Secure MCP Tunnel (`deploy/second-brain-tunnel.service.example`, `deploy/tunnel.env.example`); it needs an OpenAI Platform tunnel, a runtime key, and a ChatGPT workspace with Developer mode, and has not been verified live.
