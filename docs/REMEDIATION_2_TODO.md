# Second Brain MCP — Remediation Round 2 TODO

**Status:** Not started  
**Date:** 2026-10-26  
**Reference:** [REMEDIATION_2_SPEC.md](REMEDIATION_2_SPEC.md) (requirements `R2-xx`)  
**Related:** [TODO.md](TODO.md) (`SB-xxx`), [REMEDIATION_TODO.md](REMEDIATION_TODO.md) (`RM-xxx`)

## Working rules

- Implement in the phase order below. Within a phase, tasks may run in any order unless a dependency is listed.
- **The item line and its `Test:` / `Acceptance:` sub-bullets are requirement text. Never edit or remove them.** Add evidence, caveats, and limitations as new sub-bullets starting with `Evidence:` or `Note:`, or in the verification record.
- If an acceptance check cannot be met as written, leave the item **unchecked** with a `Note:`. Only a dated owner decision, written under the item as `Owner decision (YYYY-MM-DD): …`, can change it.
- Check an item only when every clause and every acceptance check is implemented **and** verified.
- **Fail first:** every bug-fix task needs an `Evidence:` sub-bullet showing its regression test failing on `ad85cdb` (command plus one-line failure summary) before the fix, then passing after (R2-06).
- Once RM2-002 lands, run `uv run python scripts/check_todo_integrity.py` before every commit that changes a checkbox. It must report zero violations.
- After each phase, run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -q`, and record the results in the verification record.
- The **Status** line must not say "Complete" or "passed" while any item is unchecked, partial, or relies on unrepeated manual evidence, unless it names those exceptions.
- Use short, imperative commit subjects, one logical change per commit.

## Phase A — Process integrity (P0, do first)

- [x] **RM2-001** Add the R2-01 working rule (acceptance sub-bullets are requirement text; unmet checks stay unchecked) to `docs/TODO.md` and `docs/REMEDIATION_TODO.md` (R2-01).
  - Acceptance: both files' working rules contain the rule; no existing item text changes in this commit.
  - Evidence: one working-rule bullet inserted in each file; `git diff --stat` shows exactly one added line per file and no other changes.
- [x] **RM2-002** Add `scripts/check_todo_integrity.py` with the five checks, baseline pairs, and exit codes from R2-02 (R2-02).
  - Test: temporary-git-repo tests cover a removed item, changed item text, removed `Test:` sub-bullet, changed `Acceptance:` sub-bullet, changed gate line, an allowed `Owner decision (YYYY-MM-DD):` change, and a clean file (exit 0).
  - Acceptance: run against the current repository *before* RM2-003 and RM2-004, it reports violations for SB-001, SB-028, SB-035, SB-050–SB-058, SB-061, SB-062, RM-019, RM-051, and RM-052. Record the output as evidence.
  - Evidence: `tests/unit/test_todo_integrity.py` (8 tests: clean file, removed item, changed item text, removed `Test:`, changed `Acceptance:`, changed gate, dated owner decision allowed, undated owner decision rejected) passes. Baseline for this file is `54e4554`, the commit that first added it.
  - Evidence: `uv run python scripts/check_todo_integrity.py` before RM2-003/RM2-004 exited 1 with exactly 17 violations: "requirement text changed" for SB-001, SB-028, SB-035, SB-050, SB-051, SB-052, SB-053, SB-054, SB-055, SB-056, SB-057, SB-058, SB-061, SB-062, and "requirement sub-bullet changed or removed" for RM-019 (`Test:`), RM-051 (`Acceptance:`), RM-052 (`Acceptance:`).
  - Note: only `Test:` / `Acceptance:` sub-bullets are checked, as R2-02 specifies; `Evidence required:` lines in this file are not covered by the checker.
- [x] **RM2-003** Restore the original text of the 14 SB items in R2-03's table. Move current status and evidence into `Evidence:` / `Note:` sub-bullets, and re-evaluate each checkbox against the restored text (R2-03). Depends on RM2-002.
  - Acceptance: the checker reports zero violations for `docs/TODO.md`; SB-062 is unchecked; SB-028 and SB-035 are checked only if their evidence notes name a test for every listed clause.
  - Evidence: all 14 items restored to their `5f245be` text; prior status moved into `Evidence:` / `Note:` sub-bullets. Checker reports zero violations.
  - Evidence: unchecked after re-evaluation: SB-052 and SB-053 (restart persistence not shown through the client; local server predates round-1 fixes), SB-054 (blocked), SB-062 (no systemd). SB-028 and SB-035 name a test per clause.
  - Evidence: added `tests/security/test_principal_boundary.py` (7 tests) to cover SB-035's "unauthenticated calls to both tools" and "forged client identity" clauses, which had no test. SB-057 was re-measured live on 2026-10-26 (all three profiles plus `ollama ps`).
- [x] **RM2-004** Restore the RM-019, RM-051, and RM-052 acceptance lines from `ca3a444`. Uncheck RM-010, RM-019, and RM-060 until RM2-010 passes (R2-04). Depends on RM2-002.
  - Acceptance: the checker reports zero violations for `docs/REMEDIATION_TODO.md`; RM-010, RM-019, and RM-060 are unchecked with a `Note:` pointing to RM2-010.
  - Evidence: the three `ca3a444` lines restored verbatim; the replacement notes kept as `Evidence:` sub-bullets; RM-010, RM-019, RM-060 unchecked with the RM2-010 note. `uv run python scripts/check_todo_integrity.py`: "TODO integrity check passed".
- [x] **RM2-005** Produce round-1 fail-first evidence. In a temporary git worktree at `ca3a444`, run each round-1 bug's regression test, then add the per-bug Gate R1 `Note:` from R2-05 to `docs/REMEDIATION_TODO.md` (R2-05, R2-06).
  - Acceptance: the note covers all twelve round-1 bugs, each marked "failed at `ca3a444`" with the test name, or "not runnable at `ca3a444`" with a reason; the worktree is removed afterwards.
  - Evidence: ran 17 regression tests at `ca3a444` in a detached worktree with current `tests/` copied in. Bugs 3, 7, 12 failed for the expected reason; the other 9 could not be collected (`second_brain_mcp.errors` / `store.ModelSelection` did not exist). Per-bug note added under Gate R1 in `docs/REMEDIATION_TODO.md`; `git worktree list` shows only the main worktree.
- [x] **RM2-006** Correct the Status lines of `docs/TODO.md` and `docs/REMEDIATION_TODO.md` so they name all open or unrepeated items (R2-05).
  - Acceptance: neither line claims completion without listing the exceptions (at least: RM-010/019/060 pending RM2-010, SB-062, SB-063, SB-040 dropped, SB-041–046 and SB-054 blocked).
  - Evidence: both Status lines now start "In progress" and name every unchecked item (from `grep '^- \[ \]'`), including SB-002, SB-052, SB-053, the Gate R1 limitation, and the unrepeated RM-052/RM-053 live evidence.

**Gate A:** The integrity checker exists and passes on `docs/TODO.md` and `docs/REMEDIATION_TODO.md`; no TODO claims more than its evidence supports.

## Phase B — Bugs (P0)

### Error contract

- [x] **RM2-010** Subclass `FastMCP` and override `call_tool` to return `CallToolResult(isError=True)` with exactly `<code>: <message>`. Map `SecondBrainError` causes directly, argument `ValidationError` to `invalid_input: invalid value for <fields>`, unknown tools to `invalid_input: unknown tool`, and anything else to `internal_error`. Move both `model_validate` calls inside the handlers' `try` (R2-10).
  - Test: every R2-10 acceptance case through a real MCP `tools/call` on the ASGI app, using exact string equality, `isError: true`, and no `structuredContent`.
  - Test: `nope` and `secret-marker` do not appear anywhere in the corresponding responses.
  - Evidence required: the empty-question and `mode="nope"` tests fail on `ad85cdb` (SDK prefix and raw pydantic text).
  - Evidence (fail first): `uv run pytest -q tests/integration/test_error_contract.py` on unfixed code (`66802de`, same source as `ad85cdb`): 7 failed. Texts were `Error executing tool ask_second_brain: invalid_input: question must not be empty`, a raw pydantic `1 validation error for ask_second_brainArguments…` for `mode="nope"`, `Error executing tool …: internal_error: …`, and `Unknown tool: delete_everything`.
  - Evidence (after fix): `SecondBrainMCP.call_tool` in `src/second_brain_mcp/server.py` maps `ToolError` causes to exact `CallToolResult(isError=True)` text; `model_validate` now runs inside each handler's `try`. All 7 tests in `tests/integration/test_error_contract.py` pass with exact equality, `isError: true`, no `structuredContent`, and no `nope` or `secret-marker` in responses. Full suite: 159 passed, 1 skipped.
- [x] **RM2-011** After RM2-010, re-check RM-010, RM-019, and RM-060 in `docs/REMEDIATION_TODO.md` with `Evidence:` sub-bullets naming the RM2-010 tests (R2-04). Depends on RM2-010.
  - Evidence: RM-010, RM-019, RM-060 re-checked with an `Evidence:` sub-bullet citing `tests/integration/test_error_contract.py` and commit `0b5f9e1`; RM-019's restored `Test:` line is met by `test_unexpected_exceptions_return_exact_internal_error`. The `REMEDIATION_TODO.md` Status line no longer lists them as reopened.

### Conversation behavior

- [x] **RM2-012** Stop history trimming at the first pair that doesn't fit, so included history is always the newest contiguous run (R2-12).
  - Test: uneven pair sizes (small oldest, large middle, small newest) include only the newest pair and set `history_trimmed: true`.
  - Test: a fully fitting history keeps the exact message order.
  - Evidence required: the uneven-size test fails on `ad85cdb` (the oldest pair is included).
  - Evidence (fail first): `test_trimming_stops_at_first_pair_that_does_not_fit` on unfixed code: `AssertionError … At index 0 diff: 'oldest-user' != 'newest-user'`.
  - Evidence (after fix): `service.py` trimming loop now `break`s at the first pair that does not fit. `test_trimming_stops_at_first_pair_that_does_not_fit` and `test_fully_fitting_history_keeps_exact_order` pass; full suite 161 passed, 1 skipped.
- [x] **RM2-013** Name the budget correctly in `context_too_large` (`the <profile> prompt budget` / `the <N>-token prompt budget`) (R2-13).
  - Test: a 6000-token direct model produces `the 6000-token prompt budget`; `4k` produces `the 4k prompt budget`.
  - Evidence required: the direct-model test fails on `ad85cdb` (`5k`).
  - Evidence (fail first): `test_context_too_large_names_direct_model_token_budget` on unfixed code: input was `context_too_large: input exceeds the 5k prompt budget …`.
  - Evidence (after fix): `_build_messages` takes the selection's profile name; the message says `the <profile> prompt budget` or `the <N>-token prompt budget`. Both `test_context_too_large_names_*` tests pass; full suite 163 passed, 1 skipped.

### Configuration

- [ ] **RM2-014** Remove the profile-vs-profile same-tag rule; change the allowed-model rule to "equals one of the profile budgets for that tag"; add placeholder detection (R2-15).
  - Test: `config.example.yaml` fails with exactly the placeholder message and no "conflicting" message.
  - Test: one shared tag for all four profiles loads; four distinct tags load.
  - Test: an allowed model sharing a profile tag loads with a matching budget and fails with a non-matching one.
  - Evidence required: the shared-tag test and the example-config message test fail on `ad85cdb`.
- [ ] **RM2-015** Make every `second-brain` command print configuration and credential errors to stderr and exit 1 without a traceback (R2-17).
  - Test: a parametrized CLI test runs `check-config` with one invalid config per R-35 rule plus the placeholder rule, and with a missing token env var; each exits 1, stderr has the message, and stderr has no `Traceback`.
  - Evidence required: the test fails on `ad85cdb` (traceback).

### Credentials and deployment

- [ ] **RM2-016** Rewrite `--rotate`: atomic `.bak` replacement, other lines preserved, all targets staged before any replacement, rollback on partial failure, and clean exit-1 errors (R2-18).
  - Test: three consecutive rotations succeed, each `.bak` holds the previous tokens, and modes are preserved (`0600`, `0640`, `0600` backups).
  - Test: an extra `CHATGPT_MCP_TOKEN=…` line and a comment survive unchanged.
  - Test: an unwritable service-file directory leaves the user file unchanged, exit status 1, no traceback.
  - Evidence required: the three-rotations test fails on `ad85cdb` (`FileExistsError`).
- [ ] **RM2-017** Let `auth_headers.py` accept any valid principal name, requiring `--env-var` for names other than `codex` and `claude-code` (R2-19).
  - Test: `chatgpt --env-var CHATGPT_MCP_TOKEN` prints the header; `chatgpt` alone exits 2 with the required message; an invalid name exits 2.
  - Evidence required: the `chatgpt --env-var` test fails on `ad85cdb` (invalid choice).
- [ ] **RM2-018** Add `proxy_set_header Authorization "";` plus an explanatory comment to `deploy/reverse-proxy.example` (R2-20).
  - Test: the R2-20 assertions on the `location = /mcp` block.
  - Evidence required: the test fails on `ad85cdb` (no Authorization clearing).

**Gate B:** Every Phase B task has fail-first evidence recorded; the client-visible error text is exactly `<code>: <message>` in every tested case.

## Phase C — Hygiene, logging, and tests (P1)

- [ ] **RM2-020** Create the single estimator module with `MESSAGE_OVERHEAD_TOKENS`, `PROMPT_OVERHEAD_TOKENS`, `MIN_INPUT_TOKENS`, and the estimate function; use it from `service.py`, `ollama.py`, and `config.py`; apply the corrected budget-validation formula (R2-16).
  - Test: a grep-style test asserts no module except the estimator module defines these constants or repeats the estimate formula.
  - Test: the usable-input values in `docs/operations.md` match values recomputed from the estimator and the default config.
- [ ] **RM2-021** Add the error-code-to-log-level map to `errors.py` and use it in both handlers and the `call_tool` override (R2-21).
  - Test: one code from each level row is logged at the mapped level.
- [ ] **RM2-022** Delete `ConversationStore.create`, `add_turn`, and `update_selection`; migrate tests to `record_turn` or a `conftest.py` helper (R2-22).
  - Acceptance: `grep -rnE "\.create\(|add_turn|update_selection" src tests` finds no `ConversationStore` uses; the full suite passes.
- [ ] **RM2-023** Add the subprocess uvicorn access-log leakage test (R2-23).
  - Test: no question, context, or token marker appears in captured server output; the test runs under plain pytest without Ollama in under 30 seconds.
- [ ] **RM2-024** Add the cancelled-ask lock-cleanup cases (R2-14).
  - Test: after 50 asks plus one cancelled mid-inference ask, the lock registry is empty; with two asks contending for one conversation and the waiter cancelled, the registry is empty after the holder completes.
- [ ] **RM2-025** Replace suffix and `endswith` error checks in server and live tests with exact-equality checks (R2-30). Depends on RM2-010.
  - Acceptance: `grep -rn "endswith(\"invalid_input\|endswith('invalid_input" tests` finds nothing; the live test compares the full error text.

## Phase D — Documentation and reconciliation (P1)

- [ ] **RM2-030** Update `SPEC.md` §4.1, `docs/operations.md`, `README.md`, and `docs/RELEASE_NOTES.md` to describe the exact error format and list all eleven codes with one line each (R2-11).
  - Acceptance: `docs/operations.md` lists `conversation_unavailable` and `unauthorized`; no document mentions an `Error executing tool` prefix or describes errors differently from the delivered text.
- [ ] **RM2-031** Amend `REMEDIATION_SPEC.md` R-35 for tag sharing (R2-15), recorded as an `Owner decision (YYYY-MM-DD)` note, and document helper usage for other principals and the new rotation behavior in `docs/operations.md` and `docs/integrations/local-clients.md` (R2-18, R2-19).
- [ ] **RM2-032** Re-evaluate SB-025, SB-033, SB-066 in `docs/TODO.md` and RM-025, RM-026, RM-047, RM-048, RM-061, RM-063 in `docs/REMEDIATION_TODO.md` against their unchanged text and the new evidence, adding `Evidence:` sub-bullets.
  - Acceptance: the integrity checker reports zero violations; every checked item has evidence that covers each clause.
- [ ] **RM2-033** Update `docs/RELEASE_NOTES.md` so every listed guarantee is delivered and every known limitation matches the open items (R2-05).

## Phase E — Final verification (P0)

- [ ] **RM2-040** Run the full R2-50 check on the final commit, including a fresh clone, the integrity checker, the opt-in live suite, and the manual Inspector error-text check; record each result with its commit hash (R2-50).
  - Acceptance: every R2-50 item is recorded with its date, command, and result in the verification record below; the opt-in live and Inspector rows say "Passed" only if they were run on the final commit.

**Gate E:** All tasks above are checked with evidence, the integrity checker passes, and the Status lines of all three TODO files are accurate.

## Finding coverage

| Finding from the second review | Tasks |
|---|---|
| RM-019 acceptance check deleted; RM-051/RM-052 acceptance lines replaced | RM2-001, RM2-002, RM2-004, RM2-011 |
| Gate R1 not verified; status claims all phases passed | RM2-005, RM2-006, RM2-033 |
| SB-028/SB-035 contradict checkboxes; 14 SB items reworded | RM2-002, RM2-003, RM2-032 |
| Bug 1: nginx example forwards `Authorization` | RM2-018 |
| Bug 2: rotation crash, partial rotation, dropped lines | RM2-016 |
| Bug 3: non-contiguous trimming; weak test | RM2-012 |
| Bug 4: same-tag rule breaks example config | RM2-014 |
| Bug 5: SDK error prefix; codeless validation errors; SPEC §4.1 untrue | RM2-010, RM2-030 |
| Bug 6: helper rejects new principals | RM2-017 |
| Bug 7: response validation outside catch-all | RM2-010 |
| Bug 8: "k" label in `context_too_large` | RM2-013 |
| Duplicated estimator; budget check ignores framing; literal 256 | RM2-020 |
| Dead store methods | RM2-022 |
| Caller mistakes logged at ERROR | RM2-021 |
| `docs/operations.md` omits two codes | RM2-030 |
| `check-config` reporting untested; traceback on bad config | RM2-015 |
| Access logs not covered by leakage test | RM2-023 |
| RM-021 cancelled-ask clause untested | RM2-024 |
| Suffix-only error assertions | RM2-025 |
| Live/Inspector checks not repeated on final code | RM2-040 |

## Verification record

Populate as work proceeds. Do **not** predeclare success.

| Verification | Result | Evidence (commit/command/output) |
|---|---|---|
| Integrity checker before restoration (RM2-002) | Not run | — |
| Integrity checker after restoration (Gate A) | Not run | — |
| Round-1 fail-first evidence at `ca3a444` (RM2-005) | Not run | — |
| Round-2 fail-first evidence at `ad85cdb` (Phase B) | Not run | — |
| Exact error text through MCP (RM2-010) | Not run | — |
| Access-log leakage test (RM2-023) | Not run | — |
| Phase checks (sync, Ruff, pytest) | Not run | — |
| Fresh clone of final commit (RM2-040) | Not run | — |
| Opt-in live suite on final commit (RM2-040) | Not run | — |
| Inspector error-text check on final commit (RM2-040) | Not run | — |
