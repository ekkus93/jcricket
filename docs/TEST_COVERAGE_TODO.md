# Second Brain MCP — Unit Test Coverage TODO

**Status:** Not started  
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

- [ ] **TCT-001** Add `coverage[toml]>=7.10` to the `dev` group, update `uv.lock`, and add `[tool.coverage.run]` (`branch`, `source`, `parallel`, `patch = ["subprocess"]`) and `[tool.coverage.report]` (`show_missing`, `skip_covered = false`) to `pyproject.toml`. Document the coverage command under a "Test coverage" heading in `docs/operations.md` (TC-01).
  - Acceptance: `uv sync --locked` succeeds offline; the documented command runs; `deploy/auth_headers.py` and `scripts/check_todo_integrity.py` report above 0%; `.coverage` and `.coverage.*` remain ignored by git.
  - Acceptance: record the new per-module baseline table (with subprocesses measured) in the verification record.
- [ ] **TCT-002** Add `("docs/TEST_COVERAGE_TODO.md", <commit that first adds it>)` to `BASELINES` in `scripts/check_todo_integrity.py`.
  - Acceptance: the integrity checker passes and reports violations if a `TCT` item's text or acceptance line is changed (verify once by a temporary edit, then revert).

**Gate A:** Coverage is measured for in-process and subprocess code, with one documented command.

## Phase B — Ollama adapter error paths (P0)

- [ ] **TCT-010** Chat response limits and failures (TC-10).
  - Test: an answer over `limits.response_bytes` raises exactly `ollama_bad_response: Ollama returned malformed data`; an answer exactly at the limit is accepted.
  - Test: HTTP 500 raises exactly `ollama_unavailable: Ollama is unavailable or rejected the request`; a non-JSON 200 body raises `ollama_bad_response: …`.
- [ ] **TCT-011** Ollama unavailable on the ask path (TC-11).
  - Test: through `SecondBrainService.ask`, a refused `/api/tags` gives exactly the `ollama_unavailable` text and writes no conversation row; a timeout gives `ollama_timeout: Ollama request timed out`; `{"models": "nope"}` and a non-JSON body give `ollama_bad_response: …`.
  - Test: with `inventory_cache_seconds: 0`, two asks make two `/api/tags` requests.
- [ ] **TCT-012** `/api/show` failures (TC-12).
  - Test: HTTP 500 → `ollama_unavailable`; timeout → `ollama_timeout`; list body and non-JSON body → `ollama_bad_response`; a non-string `parameters` and a non-integer `context_length` are treated as absent.
  - Test: `verify_context_windows` keeps checking later tags after a not-installed tag (both errors reported, in order).
- [ ] **TCT-013** Inventory parsing edge cases (TC-13).
  - Test: `/api/ps` entries that are not objects or have a blank name are ignored (`loaded: false`); a tag listed twice in `/api/tags` appears once; a list-shaped `/api/tags` or `/api/ps` body gives `ollama_bad_response`.

## Phase C — Service continuation and validation (P0)

- [ ] **TCT-020** Direct-model continuation (TC-20).
  - Test: a conversation created with `model="other:tag"` continues without a selector after the configured budget for `other:tag` changes; the response has `model: "other:tag"`, `model_profile: null`, and the new budget, and the stored row has the new budget.
- [ ] **TCT-021** Stored profile no longer configured (TC-21).
  - Test: a row stored with profile `legacy` fails on continuation with exactly `model_not_approved: this conversation's profile is no longer approved; choose a profile`, and no turn is written.
- [ ] **TCT-022** Remaining service validation branches (TC-22).
  - Test: approved direct model missing from `/api/tags` → exactly `model_not_installed: model tag "other:tag" is not installed in Ollama`.
  - Test: `conversation_id="   "` → `invalid_input: conversation_id must not be empty`; direct `service.ask(..., mode="nope")` → `invalid_input: mode is not supported`.
  - Test: a history whose first row is an orphan `assistant` turn builds messages without that row.
- [ ] **TCT-023** Remove the unreachable default-profile check in `SecondBrainService._selection`, with a comment naming the validator that guarantees the profile exists (TC-80).
  - Acceptance: `test_default_selection_is_32k` passes; the `no model profile is configured` branch is gone; the full suite passes.

## Phase D — Credential and config validation (P0)

- [ ] **TCT-030** Credentials (TC-30).
  - Test: missing `claude-code` mapping, a 31-character token, and two identical tokens each fail with the exact TC-30 message; valid distinct tokens return the principal-to-token map.
- [ ] **TCT-031** Ollama URL forms (TC-31).
  - Test: `ftp://127.0.0.1` and `http://` fail with the scheme/host message; `http://localhost:11434`, `http://127.0.0.1:11434/` (trailing slash stripped), and `http://[::1]:11434` load; `http://example.com` and `http://10.0.0.5:11434` fail with the loopback message.
- [ ] **TCT-032** Remaining field validation (TC-32).
  - Test: each row of the TC-32 table fails with its exact message, including the 201-selectable-tags case and the list-shaped YAML root through `load_config`.

## Phase E — Store, HTTP, CLI, and helper scripts (P1)

- [ ] **TCT-040** Store data safety (TC-40).
  - Test: a database at `user_version = 3` raises the "newer than this application" `RuntimeError` and is left byte-for-byte unchanged; `purge(0)` and `purge(-1)` raise `older_than_days must be positive` and delete nothing; a v1 database that already has all three columns migrates to v2 without schema changes.
- [ ] **TCT-050** HTTP and error-contract edges (TC-50).
  - Test: `GET /unknown` and `POST /mcp/extra` return 404 `{"error":"not found"}` with `X-Request-ID`.
  - Test: `current_principal()` without a principal raises exactly `unauthorized: authenticated principal required`.
  - Test: a `ToolError` caused by `RuntimeError("secret-marker")` from the parent `FastMCP.call_tool` yields exactly the `internal_error` text, no `secret-marker` or `boom` in the response, and an ERROR record with `unexpected_error_type=RuntimeError`.
- [ ] **TCT-060** Admin CLI and prompts (TC-60).
  - Test: `get-any` found and unknown; `export` of all conversations to stdout with and without `--principal`; `export <unknown> --output FILE` exits `conversation not found` and creates no file; `purge` without age or retention exits with the TC-60 message; TTY confirmation `y` deletes.
  - Test: `main()` with patched `sys.argv` dispatches `check-config` (prints `Configuration is valid.` with a patched context-window check), `conversations list`, and `serve` (patched `server.run` receives the loaded config).
  - Test: `system_prompt("nope")` raises `ValueError("unsupported mode: nope")`.
- [ ] **TCT-061** `deploy/auth_headers.py` failure cases (TC-61).
  - Test: invalid `--env-var` exits 2; malformed line, short token, and missing file exit 1 with the exact TC-61 messages; a quoted value is printed unquoted; failures print nothing to stdout and never echo the token.
- [ ] **TCT-062** `scripts/check_todo_integrity.py` failure cases (TC-62).
  - Test: unknown baseline commit and missing TODO file each exit 1 with the TC-62 message; `--baseline TODO.md` exits 2 with `--baseline must use PATH@COMMIT`.
- [ ] **TCT-063** `scripts/init_credentials.py` failure cases, fixing the create-over-existing-file crash (TC-63, TC-81).
  - Test: `--rotate` with no user file exits 1 with `cannot rotate credentials: credentials file does not exist: <path>` and no traceback.
  - Test: creating when the file exists exits 1 with `credentials file already exists: <path>; use --rotate to replace its tokens`, no traceback, and the file unchanged.
  - Evidence required: the create-over-existing test fails before the fix (currently a `FileExistsError` traceback, reproduced 2026-10-26).
- [ ] **TCT-064** Re-run coverage after TCT-063 and add tests for any `scripts/init_credentials.py` staging or restore lines still uncovered (`:106`, `:113-116`, `:128` at `588dbfb`), or record a `Note:` explaining why a line cannot be reached (TC-01, §10).

## Phase F — Gate and final verification (P0)

- [ ] **TCT-070** Meet the TC-70 targets and set `fail_under` (TC-70).
  - Acceptance: `src/second_brain_mcp` ≥ 97% and `scripts/` + `deploy/` ≥ 90% combined line+branch coverage; every §10 location covered or marked removed; `fail_under` set to the achieved total rounded down; no new `# pragma: no cover`.
- [ ] **TCT-071** Final verification on the last commit (TC-71).
  - Acceptance: every TC-71 command passes and is recorded with the commit hash; `uv run pytest -q` stays under 15 seconds; the final per-module coverage table is in the verification record.

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
| Baseline with subprocess coverage (TCT-001) | Not run | — |
| Phase checks (sync, Ruff, pytest, coverage) | Not run | — |
| Fail-first evidence for exposed defects (TC-03, TCT-063) | Not run | — |
| Final coverage table and `fail_under` (TCT-070) | Not run | — |
| Final verification (TCT-071) | Not run | — |
