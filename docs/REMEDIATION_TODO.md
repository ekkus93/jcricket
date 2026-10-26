# Second Brain MCP — Remediation TODO

**Status:** Not started  
**Date:** 2026-10-26  
**Reference:** [REMEDIATION_SPEC.md](REMEDIATION_SPEC.md) (requirements `R-xx`), [SPEC.md](SPEC.md)  
**Related:** [TODO.md](TODO.md) (original v0.1 items `SB-xxx`)

## Working rules

- Implement in the phase order below. Within a phase, tasks may run in any order unless a dependency is listed.
- **Never reword a task when checking it off.** Put evidence, caveats, and partial progress in an indented note under the task or in the verification record. Changing a task's scope requires an explicit owner decision recorded here with a date.
- Check a task only when **every** clause and acceptance check is implemented **and** verified. Partial work stays unchecked with a note.
- Each task lists its acceptance checks. "Test:" means an automated mocked test that runs under plain `uv run pytest`, with no Ollama, GPU, network, or accounts.
- After each phase, run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest`, and record the results.
- Keep the security invariants in REMEDIATION_SPEC §1.2 intact in every change.
- Use short, imperative commit subjects, one logical change per commit (for example, `Re-validate stored model selection on continuation`).

## Phase R0 — Repository and TODO hygiene (P0, do first)

- [ ] **RM-001** Commit the current implementation as-is, before any remediation, so later diffs are reviewable (R-01). Include `pyproject.toml`, `uv.lock`, `src/`, `tests/`, `deploy/`, `scripts/`, `config.example.yaml`, `docs/operations.md`, `docs/integrations/`, `AGENTS.md`, and the modified `.gitignore`, `README.md`, `docs/TODO.md`.
  - Acceptance: `git status` is clean apart from ignored files; no `config.yaml`, database, credentials, `.venv`, or `__pycache__` is tracked.
- [x] **RM-002** Fix `.gitignore` gaps: `.serena/`, `*.db`, `*.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, `credentials.env` (keep `*.env.example` allowed) (R-06).
  - Acceptance: `git check-ignore` confirms each pattern; `deploy/credentials.env.example` is still tracked.
  - Verified with `git check-ignore -v --no-index`; the example credentials file remains tracked and unignored.
- [ ] **RM-003** Verify Gate P0 from a fresh clone (R-01). Depends on RM-001 and RM-002.
  - Acceptance: in an empty temporary directory, `git clone`, `uv sync --locked`, Ruff check, Ruff format check, and `uv run pytest` all pass. Record the commit hash and results in the verification record.
- [ ] **RM-004** Add the TODO integrity rules from R-02 to the "Working rules" section of `docs/TODO.md`.
- [ ] **RM-005** Restore the original `HEAD` wording of SB-018, SB-019, SB-031, SB-033, SB-063, SB-064, SB-065, and SB-066 in `docs/TODO.md`, and re-evaluate each checkbox against the restored text as R-03's table specifies (R-03).
  - Acceptance: `git diff 5f245be -- docs/TODO.md` shows no changed requirement text for these items apart from added indented notes; SB-018, SB-019, SB-033, SB-065, and SB-066 are unchecked.
- [x] **RM-006** **[OWNER DECISION]** Decide SB-040: (a) restore the original Ralph Bridge design-reference requirement, unchecked, or (b) drop it, recording the owner's decision and date in `TODO.md` and amending `SPEC.md` §2.1.10 and §7.2 (R-04). The implementer must not decide.
  - Owner chose option (b) on 2026-10-26. The decision is noted under SB-040 in `docs/TODO.md`; Ralph Bridge references were removed from `docs/SPEC.md` §§2.1.10 and 7.2. The task is complete; the now-dropped SB-040 implementation requirement remains unchecked for traceability.
- [ ] **RM-007** Fix SB-002's state. Leave it checked only once RM-001 is committed and RM-003 has passed.

**Gate R0:** The repository, not just the working tree, contains the implementation; a fresh clone passes all checks; `TODO.md` states requirements truthfully.

## Phase R1 — Correctness and security bugs (P0)

### Model selection

- [ ] **RM-010** Introduce the error hierarchy: `SecondBrainError` with a `code` attribute and fixed messages for every code in R-20; make `ServiceError` and `OllamaError` subclasses or replace them; all raised errors render as `<code>: <message>` (R-20).
  - Test: every code has a fixed message string, and each existing failure path raises the expected code.
- [ ] **RM-011** Re-validate the stored selection on continuation per the R-10 table: profile conversations follow the current profile mapping; direct-model conversations require the tag to still be in `allowed_models` with its current budget; anything else gives `model_not_approved` (R-10, R-11). Depends on RM-010.
  - Test: revoked direct model blocks continuation; remapped profile tag is used and persisted after success; budget change takes effect; explicit profile or model on continuation validated like a new conversation.
- [ ] **RM-012** Add `ConversationStore.record_turn(...)` that, in one `BEGIN IMMEDIATE` transaction, inserts the conversation row (new conversations), or verifies existence and ownership (existing ones), updates the selection and `updated_at`, and inserts the user/assistant pair (R-12, R-23).
  - Test: ownership mismatch and missing row both roll back and raise `conversation_unavailable`; no partial rows remain after an injected failure between statements.
- [ ] **RM-013** Rewrite `SecondBrainService.ask` to generate new IDs before inference, insert nothing until `record_turn`, and remove `create`-then-`delete` and pre-inference `update_selection` (R-12, R-23). Depends on RM-012.
  - Test: for Ollama timeout, Ollama error, busy rejection, cancellation, and oversized input, the conversation row (if any) is unchanged and no new conversation row exists.
  - Test: deleting a conversation through the store while its ask is in flight gives `conversation_unavailable` and no orphan messages.
- [ ] **RM-014** Perform the authoritative conversation read (selection and history) inside the per-conversation lock (R-24). Depends on RM-013.
  - Test: two concurrent asks, one switching profile, the other with no selector; the second, which acquires the lock later, uses the switched selection.

### Ollama adapter and inventory

- [ ] **RM-015** Move all `/api/tags` and `/api/ps` parsing inside error handling; apply R-16's field-level type rules; never let `ModelInventory` validation fail (R-16).
  - Test: parametrized cases from R-16's acceptance list, including `details: null` (the reproduced `AttributeError`).
- [ ] **RM-016** Add an installed-tags lookup that uses only `/api/tags`, has no truncation, uses a TTL cache (`limits.inventory_cache_seconds`, default 10, `0` disables) shared by concurrent callers, and never caches failures. Use it on the ask path instead of `models()` (R-13).
  - Test: a model in position 250 of `/api/tags` is accepted; two concurrent asks cause one `/api/tags` fetch; `/api/ps` is never called on the ask path; a failed fetch is retried on the next call.
- [ ] **RM-017** `model_not_installed` names the profile (if any) and the tag (R-13).
  - Test: missing `32k` tag yields a message containing `32k` and the tag.
- [ ] **RM-018** `list_models`: `MAX_LISTED_MODELS = 200` constant; always include configured and allowlisted tags; add `truncated: bool` to `ModelInventory`; mention the cap in the tool description (R-15).
  - Test: 300 installed tags, with a configured tag at position 280, return 200 entries including that tag and `truncated: true`; 5 tags return `truncated: false`.

### Error sanitization and auth

- [ ] **RM-019** In both tool handlers, re-raise `SecondBrainError`, convert every other `Exception` to `internal_error`, log the type and request ID at `ERROR` and details only at `DEBUG`, and never catch `CancelledError` (R-21). Depends on RM-010.
  - Test: injected `sqlite3.OperationalError` and `AttributeError` produce exactly the `internal_error` text in the MCP response; the original message is absent from the response.
- [ ] **RM-020** Compare credentials as bytes; non-printable-ASCII or malformed tokens get 401; `credentials()` rejects non-ASCII configured tokens (R-22).
  - Test: R-22's cases, including raw byte `0xE9` (the reproduced 500), never return 500.

### Concurrency and persistence

- [ ] **RM-021** Reference-count per-conversation locks and remove them when unused (R-25).
  - Test: after 50 asks on distinct conversations, plus a cancelled ask, the lock registry is empty.
- [ ] **RM-022** Move admission control to the start of `ask`, after cheap validation, so it covers inventory fetch, lock wait, and inference; release in `finally` (R-26).
  - Test: with `concurrency=1, queue_depth=0`, a second ask while the first is blocked in Ollama gets `busy`, makes no Ollama call, and writes nothing; with `queue_depth=1`, it waits and succeeds.
- [ ] **RM-023** Close every SQLite connection deterministically through a store helper (R-27).
  - Test: count `connect` and `close` across every store method; they are equal.
- [ ] **RM-024** Make migrations transactional and idempotent, using `PRAGMA table_info` checks (R-28).
  - Test: clean v1, partially migrated v1, and an injected mid-migration failure (left at v1 with no new columns).
- [ ] **RM-025** Pair history by walking user→assistant turns, skipping unpaired rows (R-32).
  - Test: history with a stray unpaired `user` row still builds coherent messages.

### Configuration validation

- [ ] **RM-026** Validate `log_level`, budget versus reserve plus minimum input, `completion_tokens < context_tokens`, conflicting budgets for one tag, `token_env` name formats, and `inventory_cache_seconds` range (R-35).
  - Test: one failing config per rule, each with a specific error message; `check-config` reports each.
  - Test: `allowed_models: {x: 1024}` with the default reserve is rejected at load (the reproduced bug 7).

**Gate R1:** All twelve review bugs have regression tests that failed before the fix and pass after; every tool error matches `<code>: <message>`.

## Phase R2 — Interface, budgeting, and logging (P0)

- [ ] **RM-030** Use `Literal` types for `mode` and `model_profile` so the published schema has `enum` arrays (R-14).
  - Test: `tools/list` schema for `ask_second_brain` contains the exact enums; an invalid mode is rejected by the MCP layer.
- [ ] **RM-031** Implement the estimator with `MESSAGE_OVERHEAD_TOKENS = 8` and `PROMPT_OVERHEAD_TOKENS = 16` (R-30).
  - Test: estimate for N short messages includes 8·N + 16 overhead.
- [ ] **RM-032** Add per-profile and per-model `completion_tokens` overrides; accept both the integer and mapping forms in `allowed_models`; set the 4k reserve to 1024 in `config.example.yaml` (R-31).
  - Test: overrides change the effective reserve and the `num_predict` sent to Ollama; existing integer-form configs still load.
- [ ] **RM-033** Make `context_too_large` report the approximate available bytes and suggest the smallest profile that fits (R-31).
  - Test: a 3 KB input on `4k` suggests `32k`; an input too large for `256k` suggests none.
- [ ] **RM-034** Log warnings for `estimate_exceeded` and `context_saturated` using Ollama-reported counts (R-17).
  - Test: mocked responses trigger each warning; no content appears in the log.
- [ ] **RM-035** Server-generated `request_id` (uuid4) in middleware, a ContextVar, and an `X-Request-ID` response header on every response, including errors (R-43).
  - Test: two requests with the same JSON-RPC id get different request IDs; 401 and 403 responses carry the header.
- [ ] **RM-036** Tool log lines contain exactly the R-44 fields, including the exact model tag, with a hashed conversation-ID prefix (R-44).
  - Test: the `caplog` leakage test from R-44 with marker strings in question, context, answer, and tokens.

**Gate R2:** Schemas are enum-typed; budget errors are actionable; logs are correlatable and leak-free by test.

## Phase R3 — Cleanup, CLI, and operations (P1)

- [ ] **RM-040** Remove the duplicate distinct-token and empty-credentials checks from `server.py`, and the unreachable `/healthz` route (R-40).
  - Test: the existing `/healthz` test still passes and also passes with a foreign Host header.
- [ ] **RM-041** Add the concurrent two-principal propagation test, and set `scope["user"]` with the principal (R-41).
  - Test: 20 interleaved `tools/call` requests from both principals each see their own principal (verified through stored conversation ownership).
- [ ] **RM-042** Pass all security-relevant FastMCP settings explicitly (R-37).
  - Test: `FASTMCP_DEBUG=true` and `FASTMCP_HOST=0.0.0.0` in the environment do not change the app's settings.
- [ ] **RM-043** Rebuild the CLI with subparsers; add `get_any`; `delete` confirmation; EOF-safe prompts; admin commands do not need token env vars (R-38).
  - Test: R-51 (14) CLI cases.
- [ ] **RM-044** Add `retention_days` config, `purge` fallback to it, and the `export` command with `0600` `O_EXCL` output (R-36).
  - Test: purge uses config retention; export writes a `0600` file and refuses to overwrite.
- [ ] **RM-045** Add `deploy/second-brain-purge.service.example` and `.timer.example` (R-36).
- [ ] **RM-046** Force a single process (`workers=1`) in `run()` and document it (R-29).
- [ ] **RM-047** `auth_headers.py --env-var`; `init_credentials.py --rotate` with atomic replacement and a `0600` `.bak` (R-34).
  - Test: helper with `--env-var`; rotate produces new distinct tokens, a `0600` file, and a `0600` backup.
  - Test: the R-34 rotation test (old token gets 401 after rebuild; new token succeeds).
- [ ] **RM-048** Fix `deploy/reverse-proxy.example`: remove the Host rewrite, stop forwarding `Authorization`, and add the "non-functional until SB-041/SB-042" banner; add validated `trusted_hosts` config used by the middleware and `TransportSecuritySettings` (R-42).
  - Test: a `trusted_hosts` entry is accepted as Host; an unlisted host is still rejected; invalid entries (with a scheme, port, or path) fail config validation.
- [ ] **RM-049** Documentation updates listed in R-39 and R-34: operations, README, local-clients (credential file distinction, error codes, usable input sizes, single process, retention and export, FastMCP environment, `X-Request-ID`, `MAX_LISTED_MODELS`).
  - Acceptance: each listed topic appears in the named document; no doc claims the helper reads the service credential file.

## Phase R4 — Test suite completion (P0)

- [ ] **RM-050** Reorganize tests into `tests/unit/`, `tests/integration/`, `tests/security/`, and `tests/live/`, keeping shared fixtures in `tests/conftest.py` (R-50).
- [ ] **RM-051** Fill the remaining R-51 mocked cases not already added by earlier tasks: mode-prompt distinctness (1), all profile mappings and default (2), selectors (3), continuation with mode change (5), trimming boundaries (6), same-conversation concurrency ordering and parallel different conversations (7), restart persistence through a fresh store (9), cross-principal indistinguishability (10), 413 body limit and character limits (11), rate-limit window expiry with an injectable clock (12), Host/Origin cases (13), the exact `/api/chat` key set on every path (15), and prompt-injection text passing as data (16).
  - Acceptance: a checklist mapping each R-51 item to a test name is added as a note under this task.
- [ ] **RM-052** Add opt-in live tests in `tests/live/` with the `live` marker registered and skipped unless `SECOND_BRAIN_LIVE=1`; cover the R-52 scenarios, including an MCP client session that checks enums and a safe error (R-52).
  - Acceptance: plain `uv run pytest` reports them as skipped; `SECOND_BRAIN_LIVE=1 uv run pytest -m live` passes on this workstation; record the date, command, and summary in the verification record.
- [ ] **RM-053** Re-run MCP Inspector after R1 and R2 and confirm the two tools, enum schemas, the `truncated` field, a valid ask response, and a safe error response (R-53).

**Gate R4:** The mocked suite covers every R-51 case; live checks can be repeated from the repository.

## Phase R5 — Reconcile and release (P1)

- [ ] **RM-060** Apply the `SPEC.md` changes from REMEDIATION_SPEC §12 (the Ralph Bridge row only if RM-006 chose option (b)).
- [ ] **RM-061** Re-evaluate SB-018, SB-019, SB-022, SB-024–SB-026, SB-028, SB-032–SB-035, SB-060, and SB-065 in `docs/TODO.md` against their original wording and the new evidence; check only items that fully pass; add evidence rows to the verification record. Do not change requirement text.
- [ ] **RM-062** Write `docs/RELEASE_NOTES.md` for v0.1 with features, known limitations (4k usable input, single process, local auth only), external blockers (ChatGPT, systemd lifecycle), and the verification summary (R-05).
- [ ] **RM-063** Check SB-066 only after RM-061 and RM-062 are complete.
- [ ] **RM-064** Final full check: `uv sync --locked`, Ruff check, Ruff format check, `uv run pytest` (mocked), and `SECOND_BRAIN_LIVE=1 uv run pytest -m live` (live). Record the commit hash and results.

**Gate R5:** Every review finding is closed or explicitly deferred with an owner-approved note; `TODO.md` checkboxes match the original requirements and recorded evidence.

## Finding coverage

| Review finding | Tasks |
|---|---|
| Uncommitted implementation; Gate P0 false | RM-001, RM-003, RM-007 |
| Reworded TODO items; SB-066 premature | RM-004, RM-005, RM-061–RM-063 |
| SB-040 contradicts SPEC | RM-006, RM-060 |
| Bug 1: revoked or remapped selection ignored | RM-011 |
| Bug 2: selection persisted on failure | RM-012, RM-013 |
| Bug 3: malformed inventory leaks raw errors | RM-015, RM-019 |
| Bug 4: non-ASCII token gives 500 | RM-020 |
| Bug 5: non-unique request ID; tag not logged | RM-035, RM-036 |
| Bug 6: truncation breaks installed check | RM-016, RM-018 |
| Bug 7: budget ≤ reserve accepted | RM-026 |
| Bug 8: read outside lock | RM-014 |
| Bug 9: unbounded locks; incomplete queue bound | RM-021, RM-022 |
| Bug 10: connections not closed | RM-023 |
| Bug 11: non-atomic migration | RM-024 |
| Bug 12: `log_level` unvalidated | RM-026 |
| Raw exception text to clients | RM-010, RM-019 |
| No enum schemas | RM-030 |
| 4k nearly unusable; global reserve; framing | RM-031–RM-033 |
| Strict-alternation pairing | RM-025 |
| Duplicate checks; dead route | RM-040 |
| ContextVar relies on SDK internals | RM-041 |
| FastMCP environment and `.env` | RM-042 |
| CLI structure; export and retention | RM-043–RM-045 |
| Single-process assumption | RM-046 |
| Helper hardcoding; rotation untested; credential doc drift | RM-047, RM-049 |
| Reverse-proxy example | RM-048 |
| Extra HTTP calls per ask | RM-016 |
| `.gitignore` gaps | RM-002 |
| Missing mocked tests; weak mode test | RM-050, RM-051 |
| No repeatable live tests | RM-052 |
| SB-019 safe errors unconfirmed | RM-053 |

## Verification record

Populate as work proceeds. Do **not** predeclare success.

| Verification | Result | Evidence (commit/test/log) |
|---|---|---|
| Fresh-clone install, lint, and tests (RM-003) | Not run | — |
| Bug regression tests, all twelve (Gate R1) | Not run | — |
| Log leakage test (RM-036) | Not run | — |
| Full R-51 mocked coverage (RM-051) | Not run | — |
| Opt-in live suite (RM-052) | Not run | — |
| MCP Inspector re-check (RM-053) | Not run | — |
| Final full check (RM-064) | Not run | — |
