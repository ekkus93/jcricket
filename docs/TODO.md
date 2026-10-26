# Second Brain MCP — Implementation TODO

**Status:** In progress — local MCP server implemented; remote access and release hardening remain
**Date:** 2026-10-25  
**Reference:** [SPEC.md](SPEC.md)  
**Repository:** `ekkus93/jcricket` (working tree implementation in progress)

## Working rules

- Implement v0.1 from `SPEC.md` in the dependency order below; keep the MVP small.
- Work directly on the repository's default branch if the owner establishes that workflow; do not create per-task branches/PRs without instruction.
- Before changing a live repository, inspect its actual current head and existing work; do not overwrite concurrent changes.
- Use `uv`, Python, the existing Ollama installation, and direct Ubuntu deployment; no Docker or Podman.
- Discover installed model names using Ollama `/api/tags` and loaded status using `/api/ps`; never invent tags or allow arbitrary model execution.
- Mark an item complete only after implementation **and** verification. Keep external/manual blockers visible instead of silently treating them as done.
- TODO entries state requirements, not outcomes. Never reword requirement text when updating a checkbox; put evidence and caveats in notes or the verification record.
- Narrowing or dropping a requirement requires an explicit owner decision recorded here with a date and, when it changes `SPEC.md`, a corresponding specification update.
- Check an item only when every clause of its original requirement is implemented and verified; partial completion stays unchecked.
- Stop the first release at an independently useful, secure tool-free chatbot; memory sharing and advanced agent features remain deferred.

## Phase 0 — Repository and baseline (P0)

- [x] **SB-001** Repository exists at the remote supplied by the owner.
- [ ] **SB-002** Commit `SPEC.md` and `TODO.md` at repository root and establish project naming/package metadata.
  - The specs and package metadata are committed, but the specification files remain under `docs/`; leaving this requirement unchecked avoids claiming the root-path clause is complete.
- [x] **SB-003** Create `pyproject.toml`, Python >=3.12 environment, `uv.lock`, runnable module/CLI entry points, `ruff`, `pytest`, and `pytest-asyncio`.
- [x] **SB-004** Add `.gitignore` for local SQLite databases, secrets, `.env`, virtual environments, logs, and generated files.
- [x] **SB-005** Create `README.md` with project summary, architecture, prerequisite installation, and example of intended chat flow.
- [x] **SB-006** Add config loader, `config.example.yaml`, env-backed secret fields, validation, and tests for invalid config.
- [x] **SB-007** Define a mock Ollama test fixture; make the base automated test suite run without GPU, network, or external accounts.

**Gate P0:** Fresh checkout installs reproducibly and test/lint entry points work.

## Phase 1 — Tool-free Ollama chatbot (P0)

- [x] **SB-010** Implement async Ollama HTTP adapter around `/api/chat`, with non-streaming response, connect/read timeouts, cancellation handling, and typed errors.
- [x] **SB-011** Ensure request construction **never includes `tools`** and never executes shell, filesystem, network tools, or model-returned actions. Add explicit regression assertions.
- [x] **SB-012** Add four configurable model profiles (`4k`, `32k`, `128k`, `256k`), default `32k`, and an allowlist of approved direct model tags with explicit safe context budgets.
- [x] **SB-013** Implement read-only Ollama model discovery using `/api/tags` (installed) and `/api/ps` (currently loaded); missing tags and backend failures must produce precise, recoverable errors.
- [x] **SB-014** Add five behavior-mode prompts (`discuss`, `brainstorm`, `critic`, `review`, `solve`), with unit tests that distinguish the expected instructions.
- [x] **SB-015** Implement `ask_second_brain` validation (including optional approved `model` versus `model_profile` conflict rejection) and normalized response (`answer`, `conversation_id`, `mode`, `model_profile`, `model`, `context_limit_tokens`, `history_trimmed`, `usage`).
- [x] **SB-016** Implement MCP server on Streamable HTTP `/mcp` using a maintained Python SDK; publish exactly `ask_second_brain` and `list_models`, with truthful stateful/read-only metadata respectively.
- [x] **SB-017** Add consistent error classification, bounded tool responses, configurable completion-token reserve, max request bytes, and concurrency limit (initially one Ollama generation).
- [ ] **SB-018** Test all five modes, every profile mapping, approved direct model selection, disallowed/missing names, both selectors supplied, input validation, malformed Ollama output, and timeouts via mocks.
  - Existing tests cover common profile, selector, mode, malformed-response, and timeout cases. Full R-51 coverage is tracked under RM-051.
- [ ] **SB-019** Run MCP Inspector against loopback server and confirm exactly two discoverable tools with usable schemas, valid responses, read-only model inventory, and safe errors.
  - Tool discovery and valid responses were verified; standardized safe error responses remain pending RM-053.

**Gate P1:** An MCP client can list installed/loaded Ollama models and ask one question, while Ollama remains tool-free.

## Phase 2 — Isolated persistent conversations (P0)

- [x] **SB-020** Add SQLite database initialization, schema migration, WAL, foreign keys, busy timeout, and migrations tests.
- [x] **SB-021** Implement server-generated unpredictable conversation IDs and create/resume flow. No caller-provided owner/client IDs as authority.
- [x] **SB-022** Persist successful question/context/answer turns with timestamps, mode, selected exact model tag, optional profile, and effective context budget; avoid orphan or half-written pairs on failure/cancellation.
- [x] **SB-023** Scope all conversation operations by **verified authenticated principal**, not merely by conversation ID.
- [x] **SB-024** On continuation, reconstruct prior model messages in order; support explicit approved model/profile changes with validation, persistence, and appropriate budget handling while preserving stored turns.
- [x] **SB-025** Budget prompt tokens conservatively; keep full history in SQLite, include recent history that fits, set `history_trimmed` accurately, and reject oversized *current* input without silent truncation.
- [x] **SB-026** Serialize concurrent modifications of the same conversation, or otherwise guarantee sane chronological ordering and no history corruption.
- [x] **SB-027** Add local administrative CLI to list/show/delete conversations and purge old conversations with bulk-operation confirmation.
- [ ] **SB-028** Test multi-turn continuity, restart persistence, cross-principal denial, unknown IDs, concurrency, retention operations, and long-history trimming. Continuity/restart and cross-principal denial passed live; complete concurrency and retention integration coverage remains.

**Gate P2:** A conversation resumes after restart; one client cannot read or continue another client's conversation.

## Phase 3 — Local access and auth boundary (P0)

- [x] **SB-030** Bind the application to `127.0.0.1` by default; ensure Ollama also stays on a trusted local/private listener.
- [x] **SB-031** Implement verified local principals using separately provisioned `codex` and `claude-code` credentials (or equivalent secure local mechanism) before any conversation access.
- [x] **SB-032** Apply request size, queue length, rate and concurrency limits; validate Host and Origin policy using SDK/proxy-safe settings.
- [ ] **SB-033** Provide `.env`/secret provisioning instructions and test token rotation without committing real credentials.
  - Provisioning instructions and private credentials exist; rotation testing remains under RM-047.
- [x] **SB-034** Implement sanitized logs, request IDs, model/profile/time/usage metrics, and basic `/healthz` without secret/prompt disclosure.
- [ ] **SB-035** Add the full security regression matrix; authentication, principal mapping, Host/Origin, rate limit, and model validation are tested, but every listed adversarial case is not yet covered.

**Gate P3:** Local MCP access is authenticated, isolated, and safe on a shared workstation.

## Phase 4 — Remote ChatGPT transport (P0 integration path)

- [ ] **SB-040** Inspect the owner's working Ralph Bridge connectivity/auth deployment **as a design reference** (without copying credentials); verify current ChatGPT workspace/account feature support.
  - Owner decision (2026-10-26): Drop the Ralph Bridge design-reference requirement; it is not a dependency of the Ollama MCP server. Removed the references from `docs/SPEC.md` §§2.1.10 and 7.2. This task remains unchecked as dropped scope; ChatGPT workspace access remains tracked in SB-054.
- [ ] **SB-041** Choose secure remote ingress: TLS reverse proxy or supported private MCP tunnel. Keep MCP/Ollama/SQLite internal and enforce a strict trusted-host configuration.
- [ ] **SB-042** Determine actual ChatGPT authentication requirements. Where applicable use conformant OAuth 2.1, protected-resource metadata, PKCE, secure authorization-server integration, and issuer/audience/scope verification; avoid writing a custom provider when one already exists.
- [ ] **SB-043** Allocate a distinct authenticated `chatgpt` principal so its conversations are isolated from Codex and Claude Code.
- [ ] **SB-044** Provide deployable reverse-proxy or tunnel example with TLS, forwarded-header safety, request limits, access restrictions, and appropriate long-running inference timeouts.
- [ ] **SB-045** Test unauthorized/expired/incorrect-audience tokens, Auth metadata if used, Host/Origin policy, replay/failure cases, and publicly exposed surface.
- [ ] **SB-046** Confirm remote `/mcp` discovery and a valid authorized tool invocation using an MCP test client before attempting ChatGPT setup.

**Gate P4:** A remote authenticated MCP test client works over the protected endpoint without exposing the Ollama API. This does **not** by itself prove ChatGPT integration.

## Phase 5 — Real client smoke tests (P0 release gates)

- [x] **SB-050** Verify the four exact model tags using live `list_models` backed by `/api/tags` and loaded status from `/api/ps`; private runtime config uses the discovered tags.
- [x] **SB-051** Run actual Ollama conversation with `32k`; see verification record for latency, token counts, and effective model.
- [x] **SB-052** Configure Codex local HTTP MCP; live listing and two-turn continuation passed. A separate MCP restart check confirmed persisted history survives restart.
- [x] **SB-053** Configure Claude Code local HTTP MCP; live listing and two-turn continuation passed. A separate MCP restart check confirmed persisted history survives restart.
- [ ] **SB-054** Register/connect the authorized remote endpoint in the owner's actual ChatGPT environment and verify live `list_models` and `ask_second_brain` calls, then a conversation continuation. **[BLOCKED: no remote endpoint or ChatGPT workspace access.]**
- [x] **SB-055** Documented the exact ChatGPT validation blocker; no workaround or validation claim is made.
- [x] **SB-056** Presented a Codex-owned conversation ID using the distinct Claude Code token; the server denied access as unavailable.
- [x] **SB-057** Perform targeted smoke tests for `4k`, `128k`, and `256k`; measured short requests and checked `ollama ps` context/GPU-offload behavior.
- [x] **SB-058** Asked an independent problem with no host answer, then challenged its reasoning in the same conversation; the follow-up rederived and checked the arithmetic.

**Gate P5:** Codex and Claude Code pass live tests; ChatGPT either passes or has an accurately documented external blocker. Full three-client integration cannot be claimed without SB-054 passing.

## Phase 6 — Hardening and release (P1)

- [ ] **SB-060** Finish regression suite: restarts, timeouts, cancellations, SQLite contention, malformed requests, oversized questions, long histories, and model outages.
- [x] **SB-061** Documented private persistent data, file permissions, backup/restore, logging, and deletion behavior in `docs/operations.md`.
- [ ] **SB-062** Provide systemd unit and Ubuntu setup; an example and setup instructions exist, but startup/restart/shutdown cannot be demonstrated because this environment is not booted with systemd.
- [ ] **SB-063** Provide separate Codex, Claude Code, and ChatGPT connection guides, `list_models` examples, sample prompts, profile/direct-model selection, troubleshooting, and secure token instructions.
  - Local client guidance exists. ChatGPT remote setup remains blocked by missing ingress and workspace access.
- [x] **SB-064** Document runtime configuration, admin CLI, profile switching, usage reporting, backup, migration, and removal.
- [ ] **SB-065** Run `uv sync --locked`, `ruff check`, formatting checks, full mocked pytest suite, and explicit opt-in live integration tests; fix all actionable failures.
  - Mocked checks passed at baseline; repeatable opt-in live tests remain under RM-052.
- [ ] **SB-066** Reconcile TODO checkboxes against code and verified evidence. Document deferred items and exact blockers. Produce v0.1 release notes.
  - Release notes and final evidence reconciliation remain pending RM-061–RM-064.

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
| Unit/integration test suite | Passed | `uv sync --locked`; Ruff check/format check; `uv run pytest -q`: 35 passed (one Starlette/httpx deprecation warning). |
| MCP Inspector discovery of both tools | Passed | Inspector `tools/list` returned `ask_second_brain` and `list_models`, schemas, structured outputs, and read-only metadata. |
| Installed/loaded model inventory and allowlist | Passed | Live MCP `list_models` returned four exact configured tags; private config remains untracked. |
| No-tools guarantee | Passed | Mock regression asserts `/api/chat` request omits `tools`; direct Ollama conversation succeeded. |
| SQLite restart persistence | Passed | Live MCP conversation resumed with the same ID and prior `LANTERN-4831` turn after stopping and restarting the server against the same database. |
| Cross-principal isolation | Passed | The Claude Code principal received `conversation is unavailable` when presenting the Codex principal's conversation ID. |
| Existing Ollama 32K profile | Passed | `qwen35-32k:latest`; live request returned 323, 129 prompt tokens/50 completion tokens, 607 ms in the recorded run. |
| Codex end-to-end | Passed | Live profile listing and two `ask_second_brain` calls returned `23 × 17 = 391`; follow-up used the same ID. Restart persistence independently passed. |
| Claude Code end-to-end | Passed | Live profile listing and two `ask_second_brain` calls returned `23 × 17 = 391`; follow-up used the same ID. Restart persistence independently passed. |
| ChatGPT end-to-end | Blocked | No authenticated remote endpoint or ChatGPT workspace access is available; do not expose local loopback service. |
| Remote auth/security tests | Not run | Requires a selected OAuth/tunnel design and reachable remote test endpoint. |
| 4K/128K/256K profile checks | Passed | Live short calls: 4k `qwen3.5:9b` 2.742 s; 128k `qwen35-128k:latest` 3.978 s; 256k `qwen35-256k:latest` 4.716 s. `ollama ps` showed 256k loaded at 262144 context, 7% CPU / 93% GPU. |

### Remaining release blockers

- An authorized ChatGPT workspace and remote test endpoint are needed before SB-041–046 and SB-054 can be completed. This requirement is independent of Ralph Bridge.
- Remaining concurrency and retention integration coverage is still needed (SB-028).
- A booted Ubuntu systemd host is required to demonstrate the service lifecycle (SB-062).
- The remaining adversarial security regression cases remain to be exercised (SB-035, SB-060).

## Reference documentation

- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Ollama list installed models API](https://docs.ollama.com/api/tags)
- [Ollama list running models API](https://docs.ollama.com/api/ps)
- [MCP Python SDK deployment](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [MCP server guide](https://modelcontextprotocol.io/docs/develop/build-server)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [ChatGPT custom MCP connections](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
