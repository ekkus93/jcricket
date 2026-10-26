# Second Brain MCP

A private, local-first MCP server that lets Codex and Claude Code consult a separate Ollama chatbot. It stores conversations by authenticated client in SQLite; the Ollama model receives no tools and cannot access files, shell commands, repositories, or the network through this application. A ChatGPT connection through an OpenAI Secure MCP Tunnel is documented but has not been verified live.

The implementation follows [`docs/SPEC.md`](docs/SPEC.md), with dependency-ordered work tracked in [`docs/TODO.md`](docs/TODO.md). It targets Python 3.12+, `uv`, and an existing Ollama installation. No container runtime is required.

## Development setup

Install `uv`, Python 3.12, and Ollama before starting. Then run:

```sh
uv python install 3.12
uv venv
uv sync --locked
cp config.example.yaml config.yaml
ollama list
```

Edit `config.yaml` with exact installed model tags. Each profile needs its own model tag whose real context window is at least the profile's budget. Some models, including Qwen3.5, ignore the request's `num_ctx`, so build one variant per context size (for example, a Modelfile with `PARAMETER num_ctx 32768`) and map each profile to its own variant. `uv run second-brain --config config.yaml check-config` checks each budget against the model's real window. Set credential values through the environment variables named in `token_env`. Keep local secrets and runtime data out of version control. Run lint, formatting, and unit tests with:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Create separate local client tokens in a private file with `uv run python scripts/init_credentials.py`, then start the loopback server with `scripts/run_local.sh`. Use `uv run second-brain --config config.yaml conversations list` to inspect local history; `show`, `get-any`, and `delete` take a conversation ID. `export [ID]` writes JSON to stdout; `--output FILE` creates a private, non-overwriting export. `purge` uses configured `retention_days` or `--older-than DAYS` and prompts for confirmation unless `--yes` is supplied. Admin commands do not require bearer-token environment variables.

The MCP service exposes exactly two tools: `ask_second_brain` and read-only `list_models`. A first request can use arguments such as `{"question":"Review this approach independently.","context":"Selected design notes...","mode":"critic","model_profile":"32k"}`. You can also pass an exact installed Ollama tag with `"model":"qwen35-128k:latest"`; all models currently installed in Ollama are available, with the default profile budget used unless the tag maps to a profile or has an `allowed_models` budget override. Save the returned `conversation_id` and pass it with the next question to continue that principal's conversation. Local access binds to loopback. Remote access requires a separately secured HTTPS proxy or supported private tunnel and verified authentication. Do not expose Ollama's HTTP API publicly.

A failed tool call returns `isError: true` with text that is exactly `<code>: <message>`, for example `invalid_input: question must not be empty`. Codes are `invalid_input`, `conversation_unavailable`, `model_not_approved`, `model_not_installed`, `context_too_large`, `busy`, `ollama_unavailable`, `ollama_timeout`, `ollama_bad_response`, `unauthorized`, and `internal_error`; see [operations](docs/operations.md) for details and input-size guidance.

## Connect an MCP client

Follow the [client setup guide](docs/integrations/local-clients.md) for user-scoped Codex and Claude Code setup. Both have been smoke-tested against the local server. Hosted ChatGPT cannot reach this loopback endpoint directly. The guide documents a connection through an OpenAI Secure MCP Tunnel using a dedicated `chatgpt` principal, with no public port. That procedure has not been run against a real ChatGPT workspace, so ChatGPT is not yet a verified integration. Do not expose the local server publicly with a static bearer token.

See [operations](docs/operations.md) for database administration, backup, restore, Ubuntu service setup, and troubleshooting.

## Status

The local Codex and Claude Code flows and the configured Ollama profiles have passed smoke checks. Remote ChatGPT access, systemd lifecycle validation, and remaining hardening work are still open; see the [implementation TODO](docs/TODO.md) for evidence and blockers.
