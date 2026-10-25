# Second Brain MCP — Implementation TODO

**Status:** Not started  
**Date:** 2026-10-25  
**Reference:** [SPEC.md](SPEC.md)  
**Repository:** Awaiting creation by project owner

## Working rules

- Implement v0.1 from `SPEC.md` in the dependency order below; keep the MVP small.
- Work directly on the repository's default branch if the owner establishes that workflow; do not create per-task branches/PRs without instruction.
- Before changing a live repository, inspect its actual current head and existing work; do not overwrite concurrent changes.
- Use `uv`, Python, the existing Ollama installation, and direct Ubuntu deployment; no Docker or Podman.
- Discover installed model names using Ollama `/api/tags` and loaded status using `/api/ps`; never invent tags or allow arbitrary model execution.
- Mark an item complete only after implementation **and** verification. Keep external/manual blockers visible instead of silently treating them as done.
- Stop the first release at an independently useful, secure tool-free chatbot; memory sharing and advanced agent features remain deferred.

## Phase 0 — Repository and baseline (P0)

- [ ] **SB-001** Owner creates a new repository and supplies its URL to the implementer. **[OWNER BLOCKER]**
- [ ] **SB-002** Commit `SPEC.md` and `TODO.md` at repository root and establish project naming/package metadata.
- [ ] **SB-003** Create `pyproject.toml`, Python >=3.12 environment, `uv.lock`, runnable module/CLI entry points, `ruff`, `pytest`, and `pytest-asyncio`.
- [ ] **SB-004** Add `.gitignore` for local SQLite databases, secrets, `.env`, virtual environments, logs, and generated files.
- [ ] **SB-005** Create `README.md` with project summary, architecture, prerequisite installation, and example of intended chat flow.
- [ ] **SB-006** Add config loader, `config.example.yaml`, env-backed secret fields, validation, and tests for invalid config.
- [ ] **SB-007** Define a mock Ollama test fixture; make the base automated test suite run without GPU, network, or external accounts.

**Gate P0:** Fresh checkout installs reproducibly and test/lint entry points work.

## Phase 1 — Tool-free Ollama chatbot (P0)

- [ ] **SB-010** Implement async Ollama HTTP adapter around `/api/chat`, with non-streaming response, connect/read timeouts, cancellation handling, and typed errors.
- [ ] **SB-011** Ensure request construction **never includes `tools`** and never executes shell, filesystem, network tools, or model-returned actions. Add explicit regression assertions.
- [ ] **SB-012** Add four configurable model profiles (`4k`, `32k`, `128k`, `256k`), default `32k`, and an allowlist of approved direct model tags with explicit safe context budgets.
- [ ] **SB-013** Implement read-only Ollama model discovery using `/api/tags` (installed) and `/api/ps` (currently loaded); missing tags and backend failures must produce precise, recoverable errors.
- [ ] **SB-014** Add five behavior-mode prompts (`discuss`, `brainstorm`, `critic`, `review`, `solve`), with unit tests that distinguish the expected instructions.
- [ ] **SB-015** Implement `ask_second_brain` validation (including optional approved `model` versus `model_profile` conflict rejection) and normalized response (`answer`, `conversation_id`, `mode`, `model_profile`, `model`, `context_limit_tokens`, `history_trimmed`, `usage`).
- [ ] **SB-016** Implement MCP server on Streamable HTTP `/mcp` using a maintained Python SDK; publish exactly `ask_second_brain` and `list_models`, with truthful stateful/read-only metadata respectively.
- [ ] **SB-017** Add consistent error classification, bounded tool responses, configurable completion-token reserve, max request bytes, and concurrency limit (initially one Ollama generation).
- [ ] **SB-018** Test all five modes, every profile mapping, approved direct model selection, disallowed/missing names, both selectors supplied, input validation, malformed Ollama output, and timeouts via mocks.
- [ ] **SB-019** Run MCP Inspector against loopback server and confirm exactly two discoverable tools with usable schemas, valid responses, read-only model inventory, and safe errors.

**Gate P1:** An MCP client can list installed/loaded Ollama models and ask one question, while Ollama remains tool-free.

## Phase 2 — Isolated persistent conversations (P0)

- [ ] **SB-020** Add SQLite database initialization, schema migration, WAL, foreign keys, busy timeout, and migrations tests.
- [ ] **SB-021** Implement server-generated unpredictable conversation IDs and create/resume flow. No caller-provided owner/client IDs as authority.
- [ ] **SB-022** Persist successful question/context/answer turns with timestamps, mode, selected exact model tag, optional profile, and effective context budget; avoid orphan or half-written pairs on failure/cancellation.
- [ ] **SB-023** Scope all conversation operations by **verified authenticated principal**, not merely by conversation ID.
- [ ] **SB-024** On continuation, reconstruct prior model messages in order; support explicit approved model/profile changes with validation, persistence, and appropriate budget handling while preserving stored turns.
- [ ] **SB-025** Budget prompt tokens conservatively; keep full history in SQLite, include recent history that fits, set `history_trimmed` accurately, and reject oversized *current* input without silent truncation.
- [ ] **SB-026** Serialize concurrent modifications of the same conversation, or otherwise guarantee sane chronological ordering and no history corruption.
- [ ] **SB-027** Add local administrative CLI to list/show/delete conversations and purge old conversations with bulk-operation confirmation.
- [ ] **SB-028** Test multi-turn continuity, server restart, cross-principal denial, unknown IDs, concurrency, retention operations, and long-history trimming.

**Gate P2:** A conversation resumes after restart; one client cannot read or continue another client's conversation.

## Phase 3 — Local access and auth boundary (P0)

- [ ] **SB-030** Bind the application to `127.0.0.1` by default; ensure Ollama also stays on a trusted local/private listener.
- [ ] **SB-031** Implement verified local principals using separately provisioned `codex` and `claude-code` credentials (or equivalent secure local mechanism) before any conversation access.
- [ ] **SB-032** Apply request size, queue length, rate and concurrency limits; validate Host and Origin policy using SDK/proxy-safe settings.
- [ ] **SB-033** Provide `.env`/secret provisioning instructions and test token rotation without committing real credentials.
- [ ] **SB-034** Implement sanitized logs, request IDs, model/profile/time/usage metrics, and basic `/healthz` without secret/prompt disclosure.
- [ ] **SB-035** Add security tests for unauthenticated calls to both tools, forged client identity, cross-client IDs, malicious input text, unapproved model selection, oversized payloads, and accidental secret logging.

**Gate P3:** Local MCP access is authenticated, isolated, and safe on a shared workstation.

## Phase 4 — Remote ChatGPT transport (P0 integration path)

- [ ] **SB-040** Inspect the owner's working Ralph Bridge connectivity/auth deployment **as a design reference** (without copying credentials); verify current ChatGPT workspace/account feature support.
- [ ] **SB-041** Choose secure remote ingress: TLS reverse proxy or supported private MCP tunnel. Keep MCP/Ollama/SQLite internal and enforce a strict trusted-host configuration.
- [ ] **SB-042** Determine actual ChatGPT authentication requirements. Where applicable use conformant OAuth 2.1, protected-resource metadata, PKCE, secure authorization-server integration, and issuer/audience/scope verification; avoid writing a custom provider when one already exists.
- [ ] **SB-043** Allocate a distinct authenticated `chatgpt` principal so its conversations are isolated from Codex and Claude Code.
- [ ] **SB-044** Provide deployable reverse-proxy or tunnel example with TLS, forwarded-header safety, request limits, access restrictions, and appropriate long-running inference timeouts.
- [ ] **SB-045** Test unauthorized/expired/incorrect-audience tokens, Auth metadata if used, Host/Origin policy, replay/failure cases, and publicly exposed surface.
- [ ] **SB-046** Confirm remote `/mcp` discovery and a valid authorized tool invocation using an MCP test client before attempting ChatGPT setup.

**Gate P4:** A remote authenticated MCP test client works over the protected endpoint without exposing the Ollama API. This does **not** by itself prove ChatGPT integration.

## Phase 5 — Real client smoke tests (P0 release gates)

- [ ] **SB-050** Verify the four exact Qwen3.5 9B model tags via live `list_models` backed by `/api/tags`, and check loaded status from `/api/ps`; update private runtime config with real names.
- [ ] **SB-051** Run actual Ollama conversation with `32k` profile. Record latency, Ollama-reported token counts, and effective model name.
- [ ] **SB-052** Configure Codex to use local HTTP MCP; confirm both-tool discovery, `list_models` results, first question, follow-up using returned ID, and persistence across restart.
- [ ] **SB-053** Configure Claude Code to use local HTTP MCP; confirm the same discovery, model-listing, and conversation checks.
- [ ] **SB-054** Register/connect the authorized remote endpoint in the owner's actual ChatGPT environment and verify live `list_models` and `ask_second_brain` calls, then a conversation continuation. **[EXTERNAL ACCESS MAY BLOCK]**
- [ ] **SB-055** If ChatGPT cannot connect because of account/workspace permission, connector transport, or auth policy, document the exact issue and evidence; do not mark ChatGPT validated or invent a workaround.
- [ ] **SB-056** Run a cross-client isolation test with distinct principals and intentionally presented foreign conversation IDs.
- [ ] **SB-057** Perform targeted smoke tests for `4k`, `128k`, and `256k` profiles; measure speed and `ollama ps` context/GPU-offload behavior without assuming all work remains entirely on GPU.
- [ ] **SB-058** Verify independent critique workflow: ask for an original solution *without* the host's answer; then follow up in the same conversation to challenge its reasoning.

**Gate P5:** Codex and Claude Code pass live tests; ChatGPT either passes or has an accurately documented external blocker. Full three-client integration cannot be claimed without SB-054 passing.

## Phase 6 — Hardening and release (P1)

- [ ] **SB-060** Finish regression suite: restarts, timeouts, cancellations, SQLite contention, malformed requests, oversized questions, long histories, and model outages.
- [ ] **SB-061** Review data privacy: secure file permissions, backup/restore, no prompt/secret logging, explicit persistence documentation, and deletion behavior.
- [ ] **SB-062** Provide systemd unit and direct Ubuntu setup; demonstrate startup/restart/shutdown without Docker/Podman.
- [ ] **SB-063** Provide separate Codex, Claude Code, and ChatGPT connection guides, `list_models` examples, sample prompts, profile/direct-model selection, troubleshooting, and secure token instructions.
- [ ] **SB-064** Document runtime configuration, admin CLI, profile switching, usage reporting, backup, migration, and removal.
- [ ] **SB-065** Run `uv sync --locked`, `ruff check`, formatting checks, full mocked pytest suite, and explicit opt-in live integration tests; fix all actionable failures.
- [ ] **SB-066** Reconcile TODO checkboxes against code and verified evidence. Document deferred items and exact blockers. Produce v0.1 release notes.

**Gate P6:** Secure, reproducible MVP ready for regular use.

## Deferred backlog — Do not block v0.1

- [ ] **SB-100** Conversation summarization/compaction preserving long-term context beyond the active prompt budget.
- [ ] **SB-101** Opt-in cross-client or project-level shared memories with explicit permissions and provenance.
- [ ] **SB-102** Semantic retrieval and/or SQLite full-text search for archived discussions, if a use case demonstrates need.
- [ ] **SB-103** Multiple-model second opinions and bounded side-by-side comparison.
- [ ] **SB-104** End-to-end streaming and richer progress/cancellation UI if real client testing shows value.
- [ ] **SB-105** Optional local `stdio` transport adapter if an important client cannot support local HTTP.
- [ ] **SB-106** Dashboard/UI and richer observability, only if needed for operational management.
- [ ] **SB-107** Shared memory governance, prompt/version evaluation harness, export interoperability.

## Release verification record

Populate as work proceeds. Do **not** predeclare success.

| Verification | Result | Evidence (commit/test/log) |
|---|---|---|
| Unit/integration test suite | Not run | — |
| MCP Inspector discovery of both tools | Not run | — |
| Installed/loaded model inventory and allowlist | Not run | — |
| No-tools guarantee | Not run | — |
| SQLite restart persistence | Not run | — |
| Cross-principal isolation | Not run | — |
| Existing Ollama 32K profile | Not run | — |
| Codex end-to-end | Not run | — |
| Claude Code end-to-end | Not run | — |
| ChatGPT end-to-end | Not run | — |
| Remote auth/security tests | Not run | — |
| 4K/128K/256K profile checks | Not run | — |

## Reference documentation

- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Ollama list installed models API](https://docs.ollama.com/api/tags)
- [Ollama list running models API](https://docs.ollama.com/api/ps)
- [MCP Python SDK deployment](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [MCP server guide](https://modelcontextprotocol.io/docs/develop/build-server)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [ChatGPT custom MCP connections](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
