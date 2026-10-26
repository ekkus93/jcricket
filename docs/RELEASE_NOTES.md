# Second Brain MCP v0.1

## Features

- Local Streamable HTTP MCP server with two tools: `ask_second_brain` and read-only `list_models`.
- Independent Codex and Claude Code principals, private bearer credentials, and isolated SQLite conversations that survive restarts.
- Ollama-backed modes, four configured context profiles (one model variant per profile), approved direct model selection, continuation, and bounded history that always keeps the newest contiguous turns.
- Transactional turn persistence, validated model selection, tool errors returned as exactly `<code>: <message>` with eleven fixed codes, request IDs, category-based error log levels, rate/concurrency limits, and administrative list/show/delete/purge/export commands.
- `check-config` and `serve` report configuration and credential errors on one line without a traceback; placeholder model tags in the example configuration are rejected with a clear message.
- `check-config` and `serve` compare each profile's budget with the model's real context window via read-only `/api/show`, failing when a budget exceeds the window pinned by the variant and warning when a tag does not pin `num_ctx`.
- Credential rotation that rewrites only the token lines, keeps a private backup of the previous file, and rotates user and service files together or not at all.
- `uv`-locked development environment, mocked regression suite (including a subprocess check that server output never contains prompts or tokens), a TODO requirement-integrity checker, opt-in live Ollama checks, and an Inspector CLI verification path.

## Known limitations

- Authentication is local bearer-token authentication for Codex and Claude Code. The service is not a remote ChatGPT endpoint.
- The 4k profile reserves 1024 completion tokens and has about 2.5 KB of usable current input before history; larger contexts may need substantial memory and inference time.
- Run one server process. Admission control and per-conversation locks are in memory.
- Some models (including Qwen3.5) ignore the request's `num_ctx`, so each profile must map to its own model variant whose window is at least the profile's budget. A tag that does not pin `num_ctx` (such as the base `qwen3.5:9b` used for `4k`) cannot be fully verified and produces a warning.
- No shared memory exists between principals. Model quality, tokenization, and actual throughput depend on the installed Ollama models and hardware.
- The reverse-proxy example is explicitly non-functional until a remote authentication design is approved and implemented; it clears client `Authorization` headers.
- uvicorn's access log records request paths including query strings. The server never reads prompts or credentials from the query string.
- The live Codex client check (SB-052) was recorded against earlier code and still needs a re-run on current code, including a server restart. The Claude Code check (SB-053) passed on current code on 2026-10-26, including persistence across a restart.
- Gate R1's "regression tests failed before the fix" evidence covers 3 of the 12 round-1 bugs; the other 9 tests could not run against the pre-fix code (see `docs/REMEDIATION_TODO.md`). Every round-2 fix has recorded fail-first evidence.

## External blockers

- ChatGPT integration requires an authorized remote endpoint, a verified authentication design, and an eligible ChatGPT workspace. Local loopback checks do not establish that integration.
- The example systemd unit and retention timer are provided, but systemd startup, restart, shutdown, and timer execution were not validated in this environment.

## Verification summary

- `uv sync --locked`, Ruff lint and format checks, the mocked pytest suite, and `scripts/check_todo_integrity.py` pass. Final results for the release commit are recorded in `docs/REMEDIATION_2_TODO.md` (RM2-040).
- On 2026-10-26, after the context-window check (`d41ebd0`): mocked suite 202 passed and 1 skipped (the opt-in live test), the opt-in live test passed again, and a live `check-config` passed with one warning for the unpinned `4k` tag. Earlier, against code commit `04bf04a`: mocked suite 193 passed and 1 skipped; the opt-in live test passed (real Ollama, conversation, process restart, cross-principal denial, exact error text); and MCP Inspector CLI confirmed both tools, the `mode` enum, and the exact `invalid_input: question must not be empty` error.
- `4k`, `128k`, and `256k` were re-measured live on 2026-10-26: 2,274 ms (100% GPU), 3,521 ms (100% GPU), and 4,177 ms (7%/93% CPU/GPU) respectively.
- ChatGPT remote integration and a live systemd lifecycle remain unverified external blockers.
