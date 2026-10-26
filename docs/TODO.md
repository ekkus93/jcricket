# Second Brain MCP — Implementation TODO

**Status:** In progress — local v0.1 implemented. Open: SB-002 (spec files not at repository root), SB-040 (dropped by owner decision 2026-10-26), SB-041–SB-046 and SB-054 (blocked: no remote endpoint or ChatGPT workspace), SB-052 and SB-053 (need live client re-runs on current code, including restart), SB-062 (no systemd host), SB-063 (ChatGPT guide blocked); SB-100–SB-107 deferred. Round-2 remediation is in progress in `docs/REMEDIATION_2_TODO.md`.
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
- The item line and its `Test:` / `Acceptance:` sub-bullets are requirement text; never edit or remove them when checking an item. Add evidence, caveats, and limitations as new `Evidence:` or `Note:` sub-bullets. If an acceptance check cannot be met as written, leave the item unchecked with a `Note:` until it is met or the owner records `Owner decision (YYYY-MM-DD): …` under the item.
- Stop the first release at an independently useful, secure tool-free chatbot; memory sharing and advanced agent features remain deferred.

## Phase 0 — Repository and baseline (P0)

- [x] **SB-001** Owner creates a new repository and supplies its URL to the implementer. **[OWNER BLOCKER]**
  - Evidence: the owner supplied `git@github.com:ekkus93/jcricket.git`, configured as `origin`.
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
- [x] **SB-018** Test all five modes, every profile mapping, approved direct model selection, disallowed/missing names, both selectors supplied, input validation, malformed Ollama output, and timeouts via mocks.
  - Verified with the completed R-51 mocked matrix: modes, all profiles, selectors, invalid input, malformed Ollama responses, and timeouts pass under plain pytest.
- [x] **SB-019** Run MCP Inspector against loopback server and confirm exactly two discoverable tools with usable schemas, valid responses, read-only model inventory, and safe errors.
  - Verified 2026-10-26 with MCP Inspector CLI: exactly two tools, enum schemas, `truncated`, a valid live ask, read-only inventory, and sanitized `invalid_input` response (RM-053).

**Gate P1:** An MCP client can list installed/loaded Ollama models and ask one question, while Ollama remains tool-free.

## Phase 2 — Isolated persistent conversations (P0)

- [x] **SB-020** Add SQLite database initialization, schema migration, WAL, foreign keys, busy timeout, and migrations tests.
- [x] **SB-021** Implement server-generated unpredictable conversation IDs and create/resume flow. No caller-provided owner/client IDs as authority.
- [x] **SB-022** Persist successful question/context/answer turns with timestamps, mode, selected exact model tag, optional profile, and effective context budget; avoid orphan or half-written pairs on failure/cancellation.
  - Atomic `record_turn` tests cover new and continued conversations, ownership, and injected mid-write rollback (RM-012/RM-013).
- [x] **SB-023** Scope all conversation operations by **verified authenticated principal**, not merely by conversation ID.
- [x] **SB-024** On continuation, reconstruct prior model messages in order; support explicit approved model/profile changes with validation, persistence, and appropriate budget handling while preserving stored turns.
  - Regression tests cover current profile remapping, profile/direct selection changes, mode change, revoked models, and unchanged selections after failure (RM-011/RM-013/R-51).
- [x] **SB-025** Budget prompt tokens conservatively; keep full history in SQLite, include recent history that fits, set `history_trimmed` accurately, and reject oversized *current* input without silent truncation.
  - Estimator framing, newest-pair trimming, fit status, larger-profile suggestions, and no-write rejection are covered by unit tests (RM-031/RM-033/R-51).
  - Evidence (RM2-032, 2026-10-26): re-evaluated after RM2-012. Included history is now the newest contiguous run (`test_trimming_stops_at_first_pair_that_does_not_fit`, `test_fully_fitting_history_keeps_exact_order`); oversized current input is rejected with the selection's budget named (`test_context_too_large_names_*`); estimates come from `budget.py` (RM2-020). Every clause is met.
- [x] **SB-026** Serialize concurrent modifications of the same conversation, or otherwise guarantee sane chronological ordering and no history corruption.
  - Concurrent profile-switch continuation test verifies user/assistant pair ordering and authoritative selection reads after lock acquisition (RM-014/R-24).
- [x] **SB-027** Add local administrative CLI to list/show/delete conversations and purge old conversations with bulk-operation confirmation.
- [x] **SB-028** Test multi-turn continuity, server restart, cross-principal denial, unknown IDs, concurrency, retention operations, and long-history trimming.
  - Evidence: multi-turn continuity `test_persistence_continuity_and_principal_isolation`; server restart `test_conversation_survives_fresh_service_and_store` and live `test_live_ollama_mcp_and_restart_persistence` (process restart); cross-principal denial `test_cross_principal_unknown_id_is_indistinguishable`; unknown IDs `test_rejects_invalid_input_and_unknown_model`, `test_record_turn_rejects_unknown_and_foreign_ids`; concurrency `test_later_continuation_reads_selection_after_lock`, `test_distinct_conversations_infer_in_parallel`, `test_concurrent_tool_calls_keep_principal_ownership`; retention `test_purge_requires_confirmation_and_confirmation_flag`, `test_purge_uses_configured_retention`; long-history trimming `test_trimming_keeps_newest_complete_pairs_and_reports_fit_status`.
  - Note: the trimming test does not catch non-contiguous history (REMEDIATION_2 bug 3); RM2-012 adds the uneven-size case.
  - Updated evidence: mocked tests now cover concurrency, owner isolation, retention purge, export refusal, and newest-pair trimming; the live suite also exercises continuation after restart (RM-051/RM-052).

**Gate P2:** A conversation resumes after restart; one client cannot read or continue another client's conversation.

## Phase 3 — Local access and auth boundary (P0)

- [x] **SB-030** Bind the application to `127.0.0.1` by default; ensure Ollama also stays on a trusted local/private listener.
- [x] **SB-031** Implement verified local principals using separately provisioned `codex` and `claude-code` credentials (or equivalent secure local mechanism) before any conversation access.
- [x] **SB-032** Apply request size, queue length, rate and concurrency limits; validate Host and Origin policy using SDK/proxy-safe settings.
  - Regression coverage includes 413, bounded queue behavior, injectable rate-window expiry, Host/Origin variants, trusted hosts, and concurrency (RM-022/RM-035/RM-048/R-51).
- [x] **SB-033** Provide `.env`/secret provisioning instructions and test token rotation without committing real credentials.
  - Provisioning and separate user/service credential-file instructions are documented. Rotation and old-token rejection passed with private `.bak` files and mode checks (RM-047).
  - Evidence (RM2-032, 2026-10-26): provisioning and the separate user/service files are documented in `docs/integrations/local-clients.md` and `docs/operations.md`; rotation is tested by `tests/integration/test_credential_rotation.py` (repeat rotations, preserved lines, unwritable target, rollback) and `test_rotation_atomically_replaces_tokens_and_preserves_private_backup` (old token gets 401, new token works). No real credentials are tracked: the only tracked `.env` file is `deploy/credentials.env.example`, which holds placeholders.
- [x] **SB-034** Implement sanitized logs, request IDs, model/profile/time/usage metrics, and basic `/healthz` without secret/prompt disclosure.
  - Tests verify unique server IDs, headers on success and auth errors, exact model logging, hashed conversation IDs, and absence of prompt/answer/token markers (RM-035/RM-036).
- [x] **SB-035** Add security tests for unauthenticated calls to both tools, forged client identity, cross-client IDs, malicious input text, unapproved model selection, oversized payloads, and accidental secret logging.
  - Evidence: unauthenticated calls to both tools `test_unauthenticated_calls_to_each_tool_never_reach_backend` (no header, wrong token, wrong scheme × both tools); forged client identity `test_forged_identity_in_arguments_and_headers_is_ignored`; cross-client IDs `test_cross_principal_unknown_id_is_indistinguishable`; malicious input text `test_prompt_injection_is_sent_as_untrusted_user_data`; unapproved model selection `test_rejects_conflicting_and_unapproved_models`, `test_continuation_rejects_revoked_direct_model`; oversized payloads `test_oversized_mcp_body_returns_413_without_tool_call`, `test_character_limits_and_oversized_rejection_write_nothing`; accidental secret logging `test_tool_logs_are_correlatable_and_do_not_contain_content`.
  - Note: uvicorn access-log coverage is added by RM2-023.
  - The completed R-51 matrix adds malformed/non-ASCII credentials, untrusted host/origin, oversized/malformed requests, cross-principal indistinguishability, prompt injection, and cancellation coverage.

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

- [x] **SB-050** Verify the four exact Qwen3.5 9B model tags via live `list_models` backed by `/api/tags`, and check loaded status from `/api/ps`; update private runtime config with real names.
  - Evidence: recorded live `list_models` returned the four exact configured tags (verification record). Re-checked 2026-10-26 with `ollama list`: `qwen3.5:9b`, `qwen35-32k:latest`, `qwen35-128k:latest`, `qwen35-256k:latest` are installed and match the private `config.yaml`; loaded status from `/api/ps` is shown in the SB-057 evidence.
- [x] **SB-051** Run actual Ollama conversation with `32k` profile. Record latency, Ollama-reported token counts, and effective model name.
  - Evidence: verification record row "Existing Ollama 32K profile": `qwen35-32k:latest`, 129 prompt / 50 completion tokens, 607 ms.
- [ ] **SB-052** Configure Codex to use local HTTP MCP; confirm both-tool discovery, `list_models` results, first question, follow-up using returned ID, and persistence across restart.
  - Evidence: recorded live Codex run listed profiles and made two `ask_second_brain` calls; the follow-up used the returned ID.
  - Note: unchecked after restoring the original text. The record shows restart persistence as a separate server-level check, not through Codex, and both-tool discovery is not recorded explicitly. The local server (started 2026-10-25 22:42) also predates the round-1 fixes. Needs a live Codex re-run against current code, including a server restart.
- [ ] **SB-053** Configure Claude Code to use local HTTP MCP; confirm the same discovery, model-listing, and conversation checks.
  - Evidence: recorded live Claude Code run listed profiles and made two `ask_second_brain` calls; the follow-up used the returned ID.
  - Note: unchecked for the same reasons as SB-052. The running local server predates the round-1 fixes (its published `mode` schema has no `enum`), so a Claude Code re-run needs the server restarted on current code.
- [ ] **SB-054** Register/connect the authorized remote endpoint in the owner's actual ChatGPT environment and verify live `list_models` and `ask_second_brain` calls, then a conversation continuation. **[EXTERNAL ACCESS MAY BLOCK]**
  - Note: Blocked — no remote endpoint or ChatGPT workspace access.
- [x] **SB-055** If ChatGPT cannot connect because of account/workspace permission, connector transport, or auth policy, document the exact issue and evidence; do not mark ChatGPT validated or invent a workaround.
  - Evidence: the exact blocker (no authenticated remote endpoint, no eligible ChatGPT workspace) is documented in `docs/integrations/local-clients.md`, `README.md`, and the verification record; ChatGPT is not marked validated and no workaround is offered.
- [x] **SB-056** Run a cross-client isolation test with distinct principals and intentionally presented foreign conversation IDs.
  - Evidence: live run presented a Codex-owned conversation ID with the Claude Code token and received `conversation is unavailable`; the opt-in live test repeats this cross-principal denial.
- [x] **SB-057** Perform targeted smoke tests for `4k`, `128k`, and `256k` profiles; measure speed and `ollama ps` context/GPU-offload behavior without assuming all work remains entirely on GPU.
  - Evidence (run 2026-10-26 during RM2-003, direct `/api/chat` with each profile's `num_ctx`, then `ollama ps`): `4k` `qwen3.5:9b` 2,274 ms, 100% GPU, context 4096; `128k` `qwen35-128k:latest` 3,521 ms, 100% GPU, context 131072; `256k` `qwen35-256k:latest` 4,177 ms, 7%/93% CPU/GPU, context 262144. Times are Ollama `total_duration` including model load.
- [x] **SB-058** Verify independent critique workflow: ask for an original solution *without* the host's answer; then follow up in the same conversation to challenge its reasoning.
  - Evidence: recorded live run asked an independent problem without the host's answer, then challenged the reasoning in the same conversation; the follow-up rederived and checked the arithmetic.

**Gate P5:** Codex and Claude Code pass live tests; ChatGPT either passes or has an accurately documented external blocker. Full three-client integration cannot be claimed without SB-054 passing.

## Phase 6 — Hardening and release (P1)

- [x] **SB-060** Finish regression suite: restarts, timeouts, cancellations, SQLite contention, malformed requests, oversized questions, long histories, and model outages.
  - Added explicit SQLite lock-contention rollback and malformed MCP JSON tests; the full mocked suite covers the remaining clauses (RM-051/RM-060).
- [x] **SB-061** Review data privacy: secure file permissions, backup/restore, no prompt/secret logging, explicit persistence documentation, and deletion behavior.
  - Evidence: `docs/operations.md` documents persistence, permissions, backup/restore, logging, and deletion; `test_new_database_uses_wal_foreign_keys_version_and_restrictive_mode` checks `0600`/`0700`; `test_tool_logs_are_correlatable_and_do_not_contain_content` checks no prompt or secret logging.
- [ ] **SB-062** Provide systemd unit and direct Ubuntu setup; demonstrate startup/restart/shutdown without Docker/Podman.
  - Note: example unit and setup instructions exist, but startup/restart/shutdown cannot be demonstrated because this environment is not booted with systemd.
- [ ] **SB-063** Provide separate Codex, Claude Code, and ChatGPT connection guides, `list_models` examples, sample prompts, profile/direct-model selection, troubleshooting, and secure token instructions.
  - Local client guidance exists. ChatGPT remote setup remains blocked by missing ingress and workspace access.
- [x] **SB-064** Document runtime configuration, admin CLI, profile switching, usage reporting, backup, migration, and removal.
- [x] **SB-065** Run `uv sync --locked`, `ruff check`, formatting checks, full mocked pytest suite, and explicit opt-in live integration tests; fix all actionable failures.
  - Final run on tested code commit `b1ffb35`: locked sync, Ruff lint/format, `uv run pytest -q` (137 passed, 1 live skipped), and `SECOND_BRAIN_LIVE=1 uv run pytest -m live -q` (1 passed). One Starlette/httpx deprecation warning.
- [x] **SB-066** Reconcile TODO checkboxes against code and verified evidence. Document deferred items and exact blockers. Produce v0.1 release notes.
  - Evidence reconciliation is complete and `docs/RELEASE_NOTES.md` is available. Final verification results are recorded under RM-064.
  - Evidence (RM2-032, 2026-10-26): checkboxes were reconciled against original requirement text (RM2-003) and `scripts/check_todo_integrity.py` passes; deferred items (SB-100–SB-107) and blockers (SB-040 owner-dropped, SB-041–SB-046 and SB-054 ChatGPT, SB-052/SB-053 live re-runs, SB-062 systemd) are named in the Status line; `docs/RELEASE_NOTES.md` was brought in line with delivered behavior by RM2-033.

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
| Unit/integration test suite | Passed | Tested code commit `b1ffb35`: `uv sync --locked`, Ruff lint/format checks, `uv run pytest -q`: 137 passed, one opt-in live test skipped (one Starlette/httpx deprecation warning). |
| SB-018 mocked tool coverage | Passed | R-51 matrix covers modes, profiles, selectors, validation, malformed Ollama responses, and timeouts. |
| SB-019 MCP Inspector | Passed | 2026-10-26 Inspector CLI verified two tools, schemas, inventory, live ask, and safe invalid-input response. |
| SB-022/024–026 persistence and continuation | Passed | Transaction rollback, live selector remapping/switching, failure preservation, history ordering, trimming, and rejection tests pass. |
| SB-028 conversation matrix | Passed | Mocked concurrency, ownership, retention/export, and trimming tests pass; opt-in live restart continuation passes. |
| SB-032–035 local security matrix | Passed | Request limits, principal propagation, auth rotation, Host/Origin, rate-window expiry, request IDs, and log leakage tests pass. |
| SB-060 hardening regressions | Passed | SQLite lock contention rolls back; malformed MCP JSON, oversized requests/questions, cancellations, timeouts, and model outages are covered. |

| MCP Inspector discovery of both tools | Passed | 2026-10-26 Inspector CLI strict `tools/list`, inventory with `truncated`, live `32k` ask with usage, and safe invalid-input error; see RM-053. |
| Installed/loaded model inventory and allowlist | Passed | Live MCP `list_models` returned four exact configured tags; private config remains untracked. |
| No-tools guarantee | Passed | Mock regression asserts `/api/chat` request omits `tools`; direct Ollama conversation succeeded. |
| SQLite restart persistence | Passed | Live MCP conversation resumed with the same ID and prior `LANTERN-4831` turn after stopping and restarting the server against the same database. |
| Cross-principal isolation | Passed | The Claude Code principal received `conversation is unavailable` when presenting the Codex principal's conversation ID. |
| Existing Ollama 32K profile | Passed | `qwen35-32k:latest`; live request returned 323, 129 prompt tokens/50 completion tokens, 607 ms in the recorded run. |
| Codex end-to-end | Passed | Live profile listing and two `ask_second_brain` calls returned `23 × 17 = 391`; follow-up used the same ID. Restart persistence independently passed. |
| Claude Code end-to-end | Passed | Live profile listing and two `ask_second_brain` calls returned `23 × 17 = 391`; follow-up used the same ID. Restart persistence independently passed. |
| Opt-in live MCP/Ollama suite | Passed | `SECOND_BRAIN_LIVE=1 uv run pytest -m live -q`: 1 passed, including inventory, ask, continuation, restart persistence, cross-principal denial, enums, and safe errors. |
| ChatGPT end-to-end | Blocked | No authenticated remote endpoint or ChatGPT workspace access is available; do not expose local loopback service. |
| Remote auth/security tests | Not run | Requires a selected OAuth/tunnel design and reachable remote test endpoint. |
| 4K/128K/256K profile checks | Passed | Live short calls: 4k `qwen3.5:9b` 2.742 s; 128k `qwen35-128k:latest` 3.978 s; 256k `qwen35-256k:latest` 4.716 s. `ollama ps` showed 256k loaded at 262144 context, 7% CPU / 93% GPU. |

### Remaining release blockers

- An authorized ChatGPT workspace and remote test endpoint are needed before SB-041–046 and SB-054 can be completed. This requirement is independent of Ralph Bridge.
- A booted Ubuntu systemd host is required to demonstrate the service lifecycle (SB-062).

## Reference documentation

- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Ollama list installed models API](https://docs.ollama.com/api/tags)
- [Ollama list running models API](https://docs.ollama.com/api/ps)
- [MCP Python SDK deployment](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [MCP server guide](https://modelcontextprotocol.io/docs/develop/build-server)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [ChatGPT custom MCP connections](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
