# Operations

## Local development

Use Python 3.12 managed by `uv`; from the repository root run `uv sync --locked`, copy `config.example.yaml` to the ignored `config.yaml`, and replace each placeholder with the exact output of `ollama list`. Create local credentials with `uv run python scripts/init_credentials.py`, then start with `scripts/run_local.sh`. Check setup with `uv run second-brain --config config.yaml check-config`. The default listener is `127.0.0.1:8000`; the default database is `~/.local/share/second-brain/conversations.sqlite3`.

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

Estimates reserve space for the longest system prompt and chat framing; model tokenization can use more. `list_models` returns at most 200 entries and reports `truncated`; configured models remain included. Tool errors use stable codes such as `invalid_input`, `model_not_approved`, `model_not_installed`, `context_too_large`, `busy`, `ollama_unavailable`, `ollama_timeout`, `ollama_bad_response`, and `internal_error`. Each HTTP response carries a server-generated `X-Request-ID` for support correlation.

## Backup, restore, and removal

Stop the service before copying the SQLite database, including its `-wal` and `-shm` companions if present. For a consistent standalone backup, use SQLite's backup command, for example `sqlite3 conversations.sqlite3 '.backup /secure/backup/second-brain.sqlite3'`; protect the backup as private conversation data. To restore, stop the service, preserve the current database, copy the backup to the configured database path, set ownership to the service account and mode `0600`, and restart. Keep versioned backups before upgrades; schema migrations run when the application opens the database. Test a restored copy before relying on it.

To remove the installation, stop and disable the service, remove its unit and package/configuration/credentials as appropriate, then separately delete `/var/lib/second-brain` or the local database if permanent conversation deletion is intended. Removing software does not automatically erase backups.

## Troubleshooting

- `401`: check that the client uses its matching principal helper and the server has the same token; rotate credentials, update both user and service credential files if both are used, restart the service, and reconnect clients.
- `403`: confirm loopback Host/Origin policy and that requests use the configured local URL.
- Missing model/profile: compare exact configured tags with `ollama list`; check loaded models with `ollama ps`.
- Timeout or queue-full response: verify Ollama is responsive and lower inference concurrency; large context profiles can take longer and consume more memory.
- MCP Inspector prompts for OAuth: Inspector defaults to OAuth; for this local bearer-token server, pass an Authorization header using a private local test setup.

See [local client setup](integrations/local-clients.md) for Codex and Claude Code configuration. Remote ChatGPT setup remains blocked until a supported authenticated endpoint and workspace access are available.
