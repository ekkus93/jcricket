# Second Brain MCP v0.1

## Features

- Local Streamable HTTP MCP server with two tools: `ask_second_brain` and read-only `list_models`.
- Independent Codex and Claude Code principals, private bearer credentials, and isolated SQLite conversations that survive restarts.
- Ollama-backed modes, four configured context profiles, approved direct model selection, continuation, and bounded history.
- Transactional turn persistence, validated model selection, tool errors returned as exactly `<code>: <message>` with eleven fixed codes, request IDs, rate/concurrency limits, and administrative list/show/delete/purge/export commands.
- `uv`-locked development environment, mocked regression suite, opt-in live Ollama checks, and an Inspector CLI verification path.

## Known limitations

- Authentication is local bearer-token authentication for Codex and Claude Code. The service is not a remote ChatGPT endpoint.
- The 4k profile reserves 1024 completion tokens and has about 2.5 KB of usable current input before history; larger contexts may need substantial memory and inference time.
- Run one server process. Admission control and per-conversation locks are in memory.
- No shared memory exists between principals. Model quality, tokenization, and actual throughput depend on the installed Ollama models and hardware.
- The reverse-proxy example is explicitly non-functional until a remote authentication design is approved and implemented.

## External blockers

- ChatGPT integration requires an authorized remote endpoint, a verified authentication design, and an eligible ChatGPT workspace. Local loopback checks do not establish that integration.
- The example systemd unit and retention timer are provided, but systemd startup, restart, shutdown, and timer execution were not validated in this environment.

## Verification summary

- `uv sync --locked`, Ruff lint and format checks, and the mocked pytest suite pass. The phase R4 run reported 137 passed, one opt-in live test skipped by default, and one Starlette/httpx deprecation warning.
- The opt-in live test passed against the workstation's Ollama installation and private config, including model inventory, a two-turn conversation, restart persistence, cross-principal denial, and an MCP client schema/error check.
- MCP Inspector CLI verification found exactly two tools, enum schemas and the inventory `truncated` field; a live ask returned usage, and an invalid question returned a sanitized MCP tool error.
- ChatGPT remote integration and a live systemd lifecycle remain unverified external blockers.
