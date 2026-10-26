# Second Brain MCP — Unit Test Coverage TODO

**Status:** All TCT tasks checked with evidence (2026-10-26). Two defects were found and fixed (TCT-032, TCT-063). Exceptions: partial branches `cli.py:117->exit` and `init_credentials.py:122->124` are unreachable and documented; plain pytest runtime (12–13 s) is close to its 15 s limit.  
**Date:** 2026-10-26  
**Reference:** [TEST_COVERAGE_SPEC.md](TEST_COVERAGE_SPEC.md) (requirements `TC-xx`)

## Working rules

- Implement in the phase order below. Within a phase, tasks may run in any order unless a dependency is listed.
- **The item line and its `Test:` / `Acceptance:` sub-bullets are requirement text. Never edit or remove them.** Add evidence and caveats as new sub-bullets starting with `Evidence:` or `Note:`.
- Check an item only when every clause and every acceptance check is implemented **and** verified. If a check cannot be met as written, leave the item unchecked with a `Note:`; only a dated `Owner decision (YYYY-MM-DD): …` can change it.
- New tests assert observable behavior with exact messages (TC-02). A test that only executes a line does not count.
- **If a new test exposes a defect** (TC-03): keep the failing test, record the failure as `Evidence:`, and fix the code in the same task. If the correct behavior is unclear, leave the task unchecked and ask the owner. Never weaken a test to make it pass.
- No `# pragma: no cover` without a `Note:` and owner agreement (TC-70).
- Run `uv run python scripts/check_todo_integrity.py` before every commit that changes a checkbox, once TCT-002 lands.
- After each phase, run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, and (from Phase A on) the TC-01 coverage command, and record the results.
- The **Status** line must not say "Complete" while any item is unchecked or partial, unless it names the exceptions.
- Use short, imperative commit subjects, one logical change per commit.

## Phase A — Tooling and baseline (P0, do first)

- [x] **TCT-001** Add `coverage[toml]>=7.10` to the `dev` group, update `uv.lock`, and add `[tool.coverage.run]` (`branch`, `source`, `parallel`, `patch = ["subprocess"]`) and `[tool.coverage.report]` (`show_missing`, `skip_covered = false`) to `pyproject.toml`. Document the coverage command under a "Test coverage" heading in `docs/operations.md` (TC-01).
  - Acceptance: `uv sync --locked` succeeds offline; the documented command runs; `deploy/auth_headers.py` and `scripts/check_todo_integrity.py` report above 0%; `.coverage` and `.coverage.*` remain ignored by git.
  - Acceptance: record the new per-module baseline table (with subprocesses measured) in the verification record.
  - Evidence: `uv add --dev 'coverage[toml]>=7.10'` locked `coverage==7.17.0` (an offline resolve failed because the universal lockfile needs metadata for other Python versions, so the lock step used the network); afterwards `uv sync --locked --offline` succeeds. `[tool.coverage.run]` sets `branch`, `source`, `parallel`, `patch = ["subprocess"]`, and silences the no-data/not-imported warnings so subprocess stderr assertions are unaffected; `[tool.coverage.report]` sets `show_missing` and `skip_covered = false`. `docs/operations.md` has a "Test coverage" section with the command. `git check-ignore` confirms `.coverage` and `.coverage.*` are ignored.
  - Evidence: measured baseline — `deploy/auth_headers.py` 85%, `scripts/check_todo_integrity.py` 92% (both 0% before), `scripts/init_credentials.py` 84%, `cli.py` 81%, total 91%; table in the verification record. The measured run takes about 10 s; plain `uv run pytest` is unchanged at about 6 s.
- [x] **TCT-002** Add `("docs/TEST_COVERAGE_TODO.md", <commit that first adds it>)` to `BASELINES` in `scripts/check_todo_integrity.py`.
  - Acceptance: the integrity checker passes and reports violations if a `TCT` item's text or acceptance line is changed (verify once by a temporary edit, then revert).
  - Evidence: `BASELINES` gains `("docs/TEST_COVERAGE_TODO.md", "c4eb4f1")`, the commit that first added this file. A temporary edit of two `Test:` lines (TCT-010, TCT-011) made the checker exit 1 with two "requirement sub-bullet changed or removed" violations; after reverting, it passes.

**Gate A:** Coverage is measured for in-process and subprocess code, with one documented command.

## Phase B — Ollama adapter error paths (P0)

- [x] **TCT-010** Chat response limits and failures (TC-10).
  - Test: an answer over `limits.response_bytes` raises exactly `ollama_bad_response: Ollama returned malformed data`; an answer exactly at the limit is accepted.
  - Test: HTTP 500 raises exactly `ollama_unavailable: Ollama is unavailable or rejected the request`; a non-JSON 200 body raises `ollama_bad_response: …`.
  - Evidence: `tests/unit/test_ollama_errors.py` — `test_chat_rejects_answer_over_response_byte_limit` (11 bytes over a 10-byte limit → exact `ollama_bad_response` text), `test_chat_accepts_answer_exactly_at_response_byte_limit` (5 × `é` = 10 bytes accepted), `test_chat_http_error_and_malformed_body` (500 → exact `ollama_unavailable`; non-JSON → exact `ollama_bad_response`). No defects found.
- [x] **TCT-011** Ollama unavailable on the ask path (TC-11).
  - Test: through `SecondBrainService.ask`, a refused `/api/tags` gives exactly the `ollama_unavailable` text and writes no conversation row; a timeout gives `ollama_timeout: Ollama request timed out`; `{"models": "nope"}` and a non-JSON body give `ollama_bad_response: …`.
  - Test: with `inventory_cache_seconds: 0`, two asks make two `/api/tags` requests.
  - Evidence: `test_ask_reports_installed_tag_lookup_failures` (refused, timeout, `{"models": "nope"}`, non-JSON; each exact text and `store.list() == []`; the handler fails the test if anything other than `/api/tags` is called) and `test_disabled_inventory_cache_fetches_tags_for_every_ask` (2 asks → 2 tag requests). No defects found.
- [x] **TCT-012** `/api/show` failures (TC-12).
  - Test: HTTP 500 → `ollama_unavailable`; timeout → `ollama_timeout`; list body and non-JSON body → `ollama_bad_response`; a non-string `parameters` and a non-integer `context_length` are treated as absent.
  - Test: `verify_context_windows` keeps checking later tags after a not-installed tag (both errors reported, in order).
  - Evidence: `test_show_failures_are_sanitized` (500, timeout, list body, non-JSON), `test_show_treats_malformed_fields_as_absent` (dict `parameters`, string `context_length` → `(None, None)`), `test_context_window_check_continues_after_missing_tag` (4k and 128k missing → both errors in order, later tags still checked).
  - Note: spec §10 described branch `ollama.py:350→322` as "continuing after a not-installed tag"; it is actually the duplicate-warning branch. `test_context_window_warning_is_reported_once_per_tag` (an allowed model sharing the unpinned `4k` tag) covers it. `ollama.py` is now 100% line and branch.
- [x] **TCT-013** Inventory parsing edge cases (TC-13).
  - Test: `/api/ps` entries that are not objects or have a blank name are ignored (`loaded: false`); a tag listed twice in `/api/tags` appears once; a list-shaped `/api/tags` or `/api/ps` body gives `ollama_bad_response`.
  - Evidence: `test_inventory_ignores_bad_ps_entries_and_duplicate_tags` and `test_inventory_rejects_list_shaped_bodies` (both endpoints). Full suite 221 passed, 1 skipped.

## Phase C — Service continuation and validation (P0)

- [x] **TCT-020** Direct-model continuation (TC-20).
  - Test: a conversation created with `model="other:tag"` continues without a selector after the configured budget for `other:tag` changes; the response has `model: "other:tag"`, `model_profile: null`, and the new budget, and the stored row has the new budget.
  - Evidence: `tests/unit/test_service_continuation.py::test_direct_model_continuation_uses_current_budget` (8192 → 16384; response and stored row both show `other:tag`, `None`, 16384). No defect found.
- [x] **TCT-021** Stored profile no longer configured (TC-21).
  - Test: a row stored with profile `legacy` fails on continuation with exactly `model_not_approved: this conversation's profile is no longer approved; choose a profile`, and no turn is written.
  - Evidence: `test_continuation_rejects_profile_missing_from_config` (exact text; history still 2 rows).
- [x] **TCT-022** Remaining service validation branches (TC-22).
  - Test: approved direct model missing from `/api/tags` → exactly `model_not_installed: model tag "other:tag" is not installed in Ollama`.
  - Test: `conversation_id="   "` → `invalid_input: conversation_id must not be empty`; direct `service.ask(..., mode="nope")` → `invalid_input: mode is not supported`.
  - Test: a history whose first row is an orphan `assistant` turn builds messages without that row.
  - Evidence: `test_missing_direct_model_names_the_tag`, `test_service_rejects_blank_conversation_id_and_unknown_mode` (both exact texts), and `test_orphan_assistant_row_is_left_out_of_the_prompt`. That last test goes through `ask`, with the orphan row inserted by SQL, and checks the messages actually sent to `/api/chat` are `first question`, `first answer`, `current`.
- [x] **TCT-023** Remove the unreachable default-profile check in `SecondBrainService._selection`, with a comment naming the validator that guarantees the profile exists (TC-80).
  - Acceptance: `test_default_selection_is_32k` passes; the `no model profile is configured` branch is gone; the full suite passes.
  - Evidence: `_selection` now indexes `self.config.profiles[profile_name]` with a comment naming `known_default_profile` and `require_profiles`; the message no longer appears under `src/` or `tests/`. `test_default_selection_is_32k` passes; full suite 227 passed, 1 skipped; `service.py` is 100% line and branch.

## Phase D — Credential and config validation (P0)

- [x] **TCT-030** Credentials (TC-30).
  - Test: missing `claude-code` mapping, a 31-character token, and two identical tokens each fail with the exact TC-30 message; valid distinct tokens return the principal-to-token map.
  - Evidence: `tests/unit/test_config_validation.py` — `test_credentials_require_both_local_principals`, `test_credentials_reject_weak_or_shared_tokens` (exact messages), `test_credentials_return_principal_token_map`. No defect found.
- [x] **TCT-031** Ollama URL forms (TC-31).
  - Test: `ftp://127.0.0.1` and `http://` fail with the scheme/host message; `http://localhost:11434`, `http://127.0.0.1:11434/` (trailing slash stripped), and `http://[::1]:11434` load; `http://example.com` and `http://10.0.0.5:11434` fail with the loopback message.
  - Evidence: `test_rejects_invalid_ollama_urls` (4 cases) and `test_accepts_loopback_ollama_urls` (3 cases, including the trailing-slash strip). No defect found.
- [x] **TCT-032** Remaining field validation (TC-32).
  - Test: each row of the TC-32 table fails with its exact message, including the 201-selectable-tags case and the list-shaped YAML root through `load_config`.
  - Evidence: `test_field_validation_messages` (6 table rows; 4 profiles + 197 allowed = 201 tags), `test_two_hundred_selectable_tags_are_allowed` (boundary), `test_list_shaped_yaml_root_is_rejected_with_path`.
  - Evidence (defect found, TC-03): `test_list_shaped_yaml_root_is_rejected_with_path` failed first. A list-shaped root raised a bare `configuration root must be a mapping` without the `invalid configuration in <path>:` prefix every other config error has, because that `ValueError` was raised inside a `try` that only re-wrapped `OSError`/`YAMLError`/`ValidationError`. `load_config` now wraps all three cases with the path.
  - Evidence: `test_missing_or_malformed_yaml_names_the_file` covers the missing-file and invalid-YAML branch that coverage then showed as untested. `config.py` is 100% line and branch; full suite 248 passed, 1 skipped.

## Phase E — Store, HTTP, CLI, and helper scripts (P1)

- [x] **TCT-040** Store data safety (TC-40).
  - Test: a database at `user_version = 3` raises the "newer than this application" `RuntimeError` and is left byte-for-byte unchanged; `purge(0)` and `purge(-1)` raise `older_than_days must be positive` and delete nothing; a v1 database that already has all three columns migrates to v2 without schema changes.
  - Evidence: `tests/unit/test_store_safety.py` — `test_newer_schema_is_refused_and_left_unchanged` (exact message, file bytes identical), `test_purge_rejects_non_positive_age` (0 and -1; the 30-day-old conversation is still listed), `test_v1_database_with_all_new_columns_only_bumps_version` (`user_version` 2, `sqlite_master` identical). No defect found.
- [x] **TCT-050** HTTP and error-contract edges (TC-50).
  - Test: `GET /unknown` and `POST /mcp/extra` return 404 `{"error":"not found"}` with `X-Request-ID`.
  - Test: `current_principal()` without a principal raises exactly `unauthorized: authenticated principal required`.
  - Test: a `ToolError` caused by `RuntimeError("secret-marker")` from the parent `FastMCP.call_tool` yields exactly the `internal_error` text, no `secret-marker` or `boom` in the response, and an ERROR record with `unexpected_error_type=RuntimeError`.
  - Evidence: `tests/integration/test_http_edges.py` — `test_unknown_paths_return_404_with_request_id` (GET `/unknown`, POST `/mcp/extra`), `test_current_principal_without_authentication_is_unauthorized`, and `test_unexpected_tool_error_falls_back_to_internal_error` (patches `FastMCP.call_tool`, the parent of our subclass). No defect found.
- [x] **TCT-060** Admin CLI and prompts (TC-60).
  - Test: `get-any` found and unknown; `export` of all conversations to stdout with and without `--principal`; `export <unknown> --output FILE` exits `conversation not found` and creates no file; `purge` without age or retention exits with the TC-60 message; TTY confirmation `y` deletes.
  - Test: `main()` with patched `sys.argv` dispatches `check-config` (prints `Configuration is valid.` with a patched context-window check), `conversations list`, and `serve` (patched `server.run` receives the loaded config).
  - Test: `system_prompt("nope")` raises `ValueError("unsupported mode: nope")`.
  - Evidence: `tests/integration/test_cli_admin.py` (10 tests): `get-any` found and unknown; `export` to stdout for all conversations and for `--principal codex` (turn contents checked); `export missing --output FILE` exits `conversation not found` with no file; `purge` with no age or retention exits with the exact message and deletes nothing; TTY + `y` deletes only the target; `main()` dispatches `check-config` (`Configuration is valid.`), `conversations list`, and `serve` (patched `server.run` gets the loaded config); `system_prompt("nope")`. No defect found. `cli.py` 99% (0 missed lines), `prompts.py` 100%.
  - Note: the one remaining partial branch, `cli.py:117->exit`, is an `action` outside the `elif` chain; argparse's subcommands make it unreachable. It is left as is rather than tested as a silent no-op or rewritten (a behavior change outside this TODO).
- [x] **TCT-061** `deploy/auth_headers.py` failure cases (TC-61).
  - Test: invalid `--env-var` exits 2; malformed line, short token, and missing file exit 1 with the exact TC-61 messages; a quoted value is printed unquoted; failures print nothing to stdout and never echo the token.
  - Evidence: `tests/security/test_auth_headers.py` — `test_auth_header_helper_rejects_invalid_env_var_name`, `test_auth_header_helper_rejects_bad_credential_files` (malformed line, 20-char token; exact stderr, empty stdout, token absent from stderr), `test_auth_header_helper_reports_missing_file`, `test_auth_header_helper_strips_quotes`. No defect found.
- [x] **TCT-062** `scripts/check_todo_integrity.py` failure cases (TC-62).
  - Test: unknown baseline commit and missing TODO file each exit 1 with the TC-62 message; `--baseline TODO.md` exits 2 with `--baseline must use PATH@COMMIT`.
  - Evidence: `tests/unit/test_todo_integrity.py` — `test_unknown_baseline_commit_is_reported`, `test_missing_todo_file_is_reported`, `test_baseline_without_commit_is_a_usage_error`. No defect found.
- [x] **TCT-063** `scripts/init_credentials.py` failure cases, fixing the create-over-existing-file crash (TC-63, TC-81).
  - Test: `--rotate` with no user file exits 1 with `cannot rotate credentials: credentials file does not exist: <path>` and no traceback.
  - Test: creating when the file exists exits 1 with `credentials file already exists: <path>; use --rotate to replace its tokens`, no traceback, and the file unchanged.
  - Evidence required: the create-over-existing test fails before the fix (currently a `FileExistsError` traceback, reproduced 2026-10-26).
  - Evidence (fail first): `test_create_refuses_existing_file_without_traceback` failed on the unfixed script with `Traceback … FileExistsError` in stderr.
  - Evidence (after fix): the create path catches `FileExistsError`, prints `credentials file already exists: <path>; use --rotate to replace its tokens`, and exits 1; the file is unchanged. `test_rotate_without_existing_file_fails_cleanly` passed without a fix. Full suite 276 passed, 1 skipped (plain run 7.2 s).
- [x] **TCT-064** Re-run coverage after TCT-063 and add tests for any `scripts/init_credentials.py` staging or restore lines still uncovered (`:106`, `:113-116`, `:128` at `588dbfb`), or record a `Note:` explaining why a line cannot be reached (TC-01, §10).
  - Evidence: after TCT-063, coverage showed four `init_credentials.py` gaps, now tested in `tests/integration/test_credential_rotation.py`: `test_create_writes_private_file_with_distinct_tokens` (the normal create path had no test: 0600 file, 0700 directory, two distinct 64-hex tokens, exact output), `test_rotate_user_file_only` (rotation without `--service-file`; the service file is untouched), `test_rotation_as_root_preserves_file_owner` (patched `geteuid`/`fchown`), and `test_staging_failure_removes_temporary_files` (an `fsync` failure leaves only the original file). `init_credentials.py` is now 99%.
  - Note: the remaining partial branch `init_credentials.py:122->124` is the cleanup path when the temporary file no longer exists; `mkstemp` always creates it, so it cannot be reached without patching `os.path.exists` itself.

## Phase F — Gate and final verification (P0)

- [x] **TCT-070** Meet the TC-70 targets and set `fail_under` (TC-70).
  - Acceptance: `src/second_brain_mcp` ≥ 97% and `scripts/` + `deploy/` ≥ 90% combined line+branch coverage; every §10 location covered or marked removed; `fail_under` set to the achieved total rounded down; no new `# pragma: no cover`.
  - Evidence: `src/second_brain_mcp` 99.93% (1052 statements, 0 missed, 296 branches, 1 partial); `scripts/` + `deploy/` 97.67% (253 statements, 2 missed); total 99.47%. Every §10 location is covered, except `service.py:175`, which was removed (TCT-023). `fail_under = 99` is in `[tool.coverage.report]`; the full report passes, and `--fail-under=99.9` exits 2, so the gate works. `grep -rn "pragma: no cover"` over `src`, `scripts`, `deploy`, `tests` finds nothing.
  - Note: the remaining partial branches are `cli.py:117->exit` (unreachable `action`, see TCT-060) and `init_credentials.py:122->124` (see TCT-064). The uncovered script lines (`auth_headers.py:55`, `63->exit`; `check_todo_integrity.py:58`, `122->127`, `137->exit`) are outside §10 and above the 90% target.
- [x] **TCT-071** Final verification on the last commit (TC-71).
  - Acceptance: every TC-71 command passes and is recorded with the commit hash; `uv run pytest -q` stays under 15 seconds; the final per-module coverage table is in the verification record.
  - Evidence: on `de88a70`, `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q` (280 passed, 1 skipped, 1 Starlette/httpx deprecation warning; 12.2 s wall), the TC-01 coverage command (report exit 0 at `fail_under = 99`, total 99%), and `scripts/check_todo_integrity.py` all pass.
  - Note: plain pytest now takes 12–13 s (it was 6 s at the start), mainly from about a dozen new subprocess-based script tests; no single test exceeds 0.7 s. It is under the 15 s limit, but with little headroom.

**Gate F:** Coverage targets are met and enforced by `fail_under`, every new test asserts behavior, and any defect found was fixed with fail-first evidence.

## Coverage map

| Spec group | Tasks |
|---|---|
| Tooling and measurement (TC-01) | TCT-001, TCT-002, TCT-064 |
| Ollama adapter (TC-10 to TC-13) | TCT-010 to TCT-013 |
| Service (TC-20 to TC-22, TC-80) | TCT-020 to TCT-023 |
| Config and credentials (TC-30 to TC-32) | TCT-030 to TCT-032 |
| Store, HTTP, CLI, scripts (TC-40 to TC-63, TC-81) | TCT-040 to TCT-064 |
| Gate (TC-70, TC-71) | TCT-070, TCT-071 |

## Verification record

Populate as work proceeds. Do **not** predeclare success.

| Verification | Result | Evidence (commit/command/output) |
|---|---|---|
| Baseline with subprocess coverage (TCT-001) | Recorded | 2026-10-26, on `c4eb4f1` + TCT-001 config: auth.py 96%, budget 100%, cli 81%, config 90%, errors 100%, ollama 90%, prompts 75%, schemas 100%, server 97%, service 95%, store 96%, `deploy/auth_headers.py` 85%, `scripts/check_todo_integrity.py` 92%, `scripts/init_credentials.py` 84%; total 91% (1300 statements, 88 missed, 388 branches, 56 partial). 202 passed, 1 skipped. |
| Phase checks (sync, Ruff, pytest, coverage) | Passed | 2026-10-26, after each phase: Ruff check and format clean; pytest 202 → 220/221 (B) → 227 (C) → 248 (D) → 276/280 (E), always 1 skipped (opt-in live); coverage rising from 91% to 99%. |
| Fail-first evidence for exposed defects (TC-03, TCT-063) | Recorded | TCT-032: `load_config` list-root message lacked the file path (test failed first, then fixed, `a0ae4d8`). TCT-063: create over an existing credentials file crashed with a `FileExistsError` traceback (test failed first, then fixed). |
| Final coverage table and `fail_under` (TCT-070) | Passed | `de88a70`: auth 100%, budget 100%, cli 99% (1 partial), config 100%, errors 100%, ollama 100%, prompts 100%, schemas 100%, server 100%, service 100%, store 100%; `deploy/auth_headers.py` 96%, `scripts/check_todo_integrity.py` 97%, `scripts/init_credentials.py` 99%. Package 99.93%, scripts + deploy 97.67%, total 99.47%; `fail_under = 99`. |
| Final verification (TCT-071) | Passed | 2026-10-26, `de88a70`: locked sync, Ruff check and format, `pytest -q` 280 passed / 1 skipped in 12.2 s, coverage report exit 0, integrity checker passed. |
