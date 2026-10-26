# Second Brain MCP — Remediation Round 3 TODO

**Status:** Not started  
**Date:** 2026-10-26  
**Reference:** [REMEDIATION_3_SPEC.md](REMEDIATION_3_SPEC.md) (requirements `R3-xx`)  
**Related:** [TEST_COVERAGE_TODO.md](TEST_COVERAGE_TODO.md), [REMEDIATION_2_TODO.md](REMEDIATION_2_TODO.md)

## Working rules

- Implement in the phase order below. Within a phase, tasks may run in any order unless a dependency is listed.
- **The item line and its `Test:` / `Acceptance:` sub-bullets are requirement text. Never edit or remove them.** Add evidence and caveats as new sub-bullets starting with `Evidence:` or `Note:`.
- Check an item only when every clause and every acceptance check is implemented **and** verified. If a check cannot be met as written, leave the item unchecked with a `Note:`; only a dated `Owner decision (YYYY-MM-DD): …` can change it.
- **Fail first:** every bug-fix task (Phase B) needs an `Evidence:` sub-bullet showing its regression test failing on `c7cf77a` before the fix (command plus one-line failure summary), then passing after.
- Never weaken a test to make it pass. If a new test exposes a defect outside this TODO's scope, keep the failing test, record it, and ask the owner.
- Run `uv run python scripts/check_todo_integrity.py` before every commit that changes a checkbox, once RM3-001 lands.
- After each phase, run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, and the TC-01 coverage command, and record the results.
- The **Status** line must not say "Complete" while any item is unchecked or partial, unless it names the exceptions.
- Use short, imperative commit subjects, one logical change per commit.

## Phase A — Process (P0, do first)

- [x] **RM3-001** Add `("docs/REMEDIATION_3_TODO.md", <commit that first adds it>)` to `BASELINES` in `scripts/check_todo_integrity.py` (R3-02).
  - Acceptance: the checker passes; a temporary edit to one `Test:` line in this file makes it exit 1, and reverting restores a pass. Record both outcomes.
  - Evidence: `BASELINES` gains `("docs/REMEDIATION_3_TODO.md", "3205580")`, the commit that first added this file. A temporary edit of RM3-010's first `Test:` line made the checker exit 1 ("RM3-010: requirement sub-bullet changed or removed"); after reverting, it passes.

**Gate A:** This TODO is under integrity protection.

## Phase B — Bugs (P0)

- [ ] **RM3-010** Make `history_trimmed` mean "a complete pair was omitted for budget"; orphan rows never set it (R3-10).
  - Test: through `ask`, history `[assistant (orphan), user, assistant]` that fits returns `history_trimmed: false` and sends `[system, user, assistant, current]`.
  - Test: the same conversation with an older complete pair that does not fit returns `history_trimmed: true`.
  - Test: a history of only orphan rows returns `history_trimmed: false`.
  - Test: `test_orphan_assistant_row_is_left_out_of_the_prompt` additionally asserts `history_trimmed is False`; all existing trimming tests pass unchanged.
  - Evidence required: the extended orphan test fails on `c7cf77a` (`history_trimmed` is `True`).
  - Evidence (fail first): on unfixed code (`10428a8`, same source as `c7cf77a`), `test_orphan_assistant_row_is_left_out_of_the_prompt` (now asserting `history_trimmed is False` through `ask`) and the new `test_only_orphan_rows_do_not_set_history_trimmed` both failed with `assert True is False`; `test_dropped_complete_pair_still_sets_history_trimmed` passed before and after.
  - Evidence (after fix): the post-loop `len(included) != len(history)` check is removed from `_build_messages`, so only an omitted complete pair sets the flag. Full suite 282 passed, 1 skipped.
  - Note: left UNCHECKED. The acceptance clause "all existing trimming tests pass unchanged" cannot be met literally: the existing `tests/unit/test_service.py::test_history_pairing_skips_unpaired_rows` asserted `trimmed is True` for a history whose stray unpaired row was skipped and whose complete pair fit, which is precisely the behavior R3-10 calls a bug. I changed that single assertion to `trimmed is False` (nothing else in the test changed) and need the owner to confirm this is the intended reading, or to record an `Owner decision (YYYY-MM-DD):` for the acceptance clause. The spec (R3-10) missed this test.
- [ ] **RM3-011** Set `precision = 1` and `fail_under = 99.4` in `[tool.coverage.report]`; document the threshold in `docs/operations.md` (R3-11).
  - Acceptance: the TC-01 coverage command exits 0; `uv run coverage report --fail-under=99.5` on the same data exits 2; `docs/operations.md` states the threshold and that it is compared at one decimal.
  - Evidence required: before the change, `uv run python -c "from coverage.results import should_fail_under as f; print(f(98.6, 99, 0))"` prints `False` (the gate would pass 98.6%).
  - Evidence (before): `should_fail_under(98.6, 99, 0)` printed `False`, so the old gate passed 98.6%.
  - Evidence (after): `pyproject.toml` has `precision = 1`, `fail_under = 99.4`; the TC-01 command exits 0 (total 99.47%, shown as 99.5%); `should_fail_under(98.6, 99.4, 1)` and `should_fail_under(99.3, 99.4, 1)` are both `True`; `coverage report --fail-under=99.6` exits 2 on the same data; `docs/operations.md` states the threshold and the one-decimal comparison.
  - Note: left UNCHECKED. The acceptance clause "`uv run coverage report --fail-under=99.5` on the same data exits 2" cannot be met: the total is 99.47%, which rounds to 99.5% at one decimal, and 99.5 is not below 99.5, so that command exits 0. The spec (R3-11) contradicts itself here (it says 99.47 "rounds to 99.5 and passes"). I verified the intended property with `--fail-under=99.6` (exit 2) instead. Needs an `Owner decision (YYYY-MM-DD):` to change the clause, for example to 99.6.
- [ ] **RM3-012** Add `limits.metadata_timeout_seconds` (default 10, `gt=0`, `le=120`) and make `verify_context_windows` build its own client with `Timeout(metadata_timeout_seconds, connect=connect_timeout_seconds)` when none is passed (R3-12).
  - Test: with `metadata_timeout_seconds = 0.05` and a `/api/show` handler that sleeps 0.5 s, `verify_context_windows(config)` raises `ollama_timeout: Ollama request timed out` in under 0.5 s; or, if `MockTransport` does not enforce timeouts, the test asserts the constructed client's `timeout` equals the expected `httpx.Timeout` and says so in a comment.
  - Test: `check-config` against an unreachable Ollama still exits 1 with `second-brain: could not verify model context windows: ollama_unavailable: …`; `config.example.yaml` (with placeholders replaced) loads with the new field.
  - Evidence required: before the change, a test asserting the client's read timeout equals `metadata_timeout_seconds` fails (read timeout is 300).

**Gate B:** All three bugs have fail-first evidence; `history_trimmed`, the coverage gate, and the metadata timeout behave as R3-10 to R3-12 specify.

## Phase C — Test strictness and hygiene (P1)

- [ ] **RM3-020** Replace `match=` with exact comparison via `_value_error_message` for every TC-31 and TC-32 case in `tests/unit/test_config_validation.py` (R3-20).
  - Acceptance: no `match=` remains in that file; each pydantic case unpacks exactly one error; all cases pass.
- [ ] **RM3-021** Tighten the boundary and leakage assertions (R3-21).
  - Test: `test_two_hundred_selectable_tags_are_allowed` asserts `len(allowed_models) == 196` and that the 200 selectable tags are distinct.
  - Test: `test_auth_header_helper_rejects_invalid_env_var_name` asserts the 64-character token is absent from `stderr`.
- [ ] **RM3-022** Test hygiene and the `_conversations` signature (R3-22).
  - Acceptance: `test_failed_replacement_restores_already_rotated_files` uses `_module()`, which is defined before its first use; the two `module.os` patches carry the required comment.
  - Acceptance: `cli._conversations(database_path, retention_days, args)` replaces the duck-typed signature; `main()` passes `config.database_path, config.retention_days`; `getattr(config, "database_path", config)` no longer exists; every caller in `tests/` passes explicit arguments; the full suite passes.

## Phase D — Server (P1)

- [ ] **RM3-023** Give the `SecondBrainMCP.call_tool` fallback log line the full R-44 field set, with `rpc_id` from `self.get_context().request_id` (or `-`) and `principal` from the auth ContextVar (or `-`) (R3-23).
  - Test: a `caplog` test triggers `mode="nope"` and an unknown tool; each record contains every R-44 field name exactly once and `rpc_id` equals the JSON-RPC id sent.
- [ ] **RM3-024** Detect unknown tools with `self._tool_manager.get_tool(name) is None` before calling `super().call_tool`, and remove the `"Unknown tool"` string match from `_tool_error` (R3-24).
  - Test: `test_unknown_tool_is_invalid_input` still passes.
  - Test: patching `FastMCP.call_tool` to raise `ToolError("Unknown tool: delete_everything")` with no cause for a known tool name yields exactly `internal_error: the server could not complete the request`.

## Phase E — Documentation (P1)

- [ ] **RM3-025** Add the `Erratum (2026-10-26):` line under `docs/TEST_COVERAGE_SPEC.md` §10 for `ollama.py:350→322`; document `metadata_timeout_seconds` in `docs/operations.md` and `config.example.yaml` (R3-25, R3-12).
  - Acceptance: the original §10 row is unchanged; the erratum names the branch as the duplicate-warning branch; `config.example.yaml` contains `metadata_timeout_seconds: 10` under `limits`.

## Phase F — Test runtime (P1)

- [ ] **RM3-030** Convert the `check-config`, integrity-checker, credential-rotation, and header-helper subprocess tests to in-process `main()` calls, keeping exactly one subprocess test per entry point; leave `tests/unit/test_service.py` and the access-log leakage test unchanged (R3-30).
  - Acceptance: plain `uv run pytest -q` wall time is ≤ 10 s as the median of three runs on this workstation (record all three); the test count is unchanged or higher; coverage still passes at `fail_under = 99.4`.
  - Acceptance: exactly one subprocess test remains for each of `second_brain_mcp.cli`, `scripts/check_todo_integrity.py`, `scripts/init_credentials.py`, and `deploy/auth_headers.py`, each asserting the exit status and that stderr contains no `Traceback`.
  - Note (from R3-30): the review's claim that subprocess tests were the main cost was only partly right; the measured breakdown is in the spec. Record the post-change per-file call times for the four converted files.

## Phase G — Final verification (P0)

- [ ] **RM3-040** Run every R3-40 check on the final commit, including the fresh clone and the three timed pytest runs, and record each with the commit hash (R3-40).
  - Acceptance: every R3-40 item is recorded with date, command, and result; the Status line names any remaining exception.

**Gate G:** All findings from the third review are closed with evidence; the coverage gate holds at one decimal; the suite runs in ≤ 10 s.

## Finding coverage

| Finding from the third review | Tasks |
|---|---|
| Bug 1: orphan row sets `history_trimmed` | RM3-010 |
| Bug 2: coverage gate permits 98.5% | RM3-011 |
| Bug 3: `/api/show` check uses the inference timeout | RM3-012, RM3-025 |
| `match=` not exact | RM3-020 |
| Weak boundary assertion; missing token-absence check | RM3-021 |
| Duplicated `_module()`; process-wide `os` patches; `_conversations` duck typing | RM3-022 |
| Fallback log line lacks R-44 fields | RM3-023 |
| Unknown-tool detection by message text | RM3-024 |
| Spec §10 mislabel | RM3-025 |
| Runtime near budget; misattributed cause | RM3-030 |
| Final verification | RM3-040 |

## Verification record

Populate as work proceeds. Do **not** predeclare success.

| Verification | Result | Evidence (commit/command/output) |
|---|---|---|
| Integrity protection for this file (RM3-001) | Not run | — |
| Fail-first evidence, Phase B (RM3-010 to RM3-012) | Not run | — |
| Phase checks (sync, Ruff, pytest, coverage) | Not run | — |
| Runtime after conversion, three runs (RM3-030) | Not run | — |
| Fresh clone of final commit (RM3-040) | Not run | — |
| Final verification (RM3-040) | Not run | — |
