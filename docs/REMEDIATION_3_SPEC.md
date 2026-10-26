# Second Brain MCP — Remediation Round 3 Specification

**Status:** Proposed, ready for implementation  
**Date:** 2026-10-26  
**Applies to:** `master` at `c7cf77a` ("Record final coverage verification")  
**Companion task list:** [REMEDIATION_3_TODO.md](REMEDIATION_3_TODO.md)  
**Parent documents:** [SPEC.md](SPEC.md), [REMEDIATION_SPEC.md](REMEDIATION_SPEC.md), [REMEDIATION_2_SPEC.md](REMEDIATION_2_SPEC.md), [TEST_COVERAGE_SPEC.md](TEST_COVERAGE_SPEC.md)

## 1. Purpose

This document specifies fixes for every finding from the third review (2026-10-26), which checked the project against `docs/TEST_COVERAGE_TODO.md`. That review found three low-severity bugs, several tests that are weaker than their requirements say, one log line that is thinner than the logging contract, one fragile string match, and a test-runtime concern. It also mislabeled the source of the runtime cost; §7 corrects that with measurements.

Requirement IDs are `R3-xx`. Tasks in the companion TODO are `RM3-xxx`. §9 maps every review finding to a requirement.

### 1.1 Non-goals

- No new features and no change to the MCP tool surface.
- No change to persistence, authentication, or the error-code list.
- No change to the opt-in live test.

### 1.2 Invariants

All invariants in `REMEDIATION_SPEC.md` §1.2 still apply. In addition, the coverage gate (R3-11) and the test-runtime budget (R3-30) must both hold on the final commit.

## 2. Process

### R3-01 Rules carried forward

The working rules from `REMEDIATION_2_TODO.md` and `TEST_COVERAGE_TODO.md` apply unchanged: item lines and their `Test:` / `Acceptance:` sub-bullets are requirement text and are never edited; evidence goes in `Evidence:` / `Note:` sub-bullets; a bug fix needs its regression test shown failing first; the integrity checker runs before every checkbox commit; the Status line names every exception.

### R3-02 Integrity baseline

Add `("docs/REMEDIATION_3_TODO.md", <commit that first adds it>)` to `BASELINES` in `scripts/check_todo_integrity.py`, as TCT-002 did for the coverage TODO.

## 3. Bugs

### R3-10 `history_trimmed` must mean "a complete pair was left out for budget"

`SecondBrainService._build_messages` sets `trimmed = True` whenever `len(included) != len(history)`. A stored row that cannot be paired (an orphan `assistant` or `user` row) is never included, so its presence alone makes the response report `history_trimmed: true` even when every complete pair fits. Reproduced on 2026-10-26 with history `[assistant, user, assistant]`: the prompt was complete, the flag was `true`.

**Required behavior.** `history_trimmed` is `true` if and only if at least one complete user/assistant pair was omitted because it did not fit the budget. Orphan rows are skipped silently and never affect the flag. Concretely: remove the post-loop `len(included) != len(history)` check; the loop's `trimmed = True` on the first non-fitting pair is the only place the flag is set.

**Acceptance:**

- Through `SecondBrainService.ask`, a conversation whose stored history is `[assistant (orphan), user, assistant]` and fits the budget returns `history_trimmed: false` and sends `[system, user, assistant, current]`.
- The same conversation with a budget that fits only the newest pair returns `history_trimmed: true` when an older complete pair exists and is dropped.
- A history of only orphan rows returns `history_trimmed: false`.
- `tests/unit/test_service_continuation.py::test_orphan_assistant_row_is_left_out_of_the_prompt` additionally asserts `history_trimmed is False`. This test must be shown failing on `c7cf77a` before the fix.
- All existing trimming tests still pass unchanged.

### R3-11 The coverage gate must fire at the first lost tenth of a point

`[tool.coverage.report]` has `fail_under = 99` with coverage's default `precision = 0`. Coverage rounds the total to `precision` digits before comparing, so `should_fail_under(98.6, 99, 0)` is `False`: the suite could lose almost a full point before the gate fires, which contradicts TC-70's intent ("so coverage cannot silently drop").

**Required change.** Set `precision = 1` and `fail_under = 99.4` in `[tool.coverage.report]`. The achieved total is 99.47%, which rounds to 99.5 and passes; 99.3 fails.

**Acceptance:**

- The TC-01 coverage command exits 0 on the final commit.
- `uv run coverage report --fail-under=99.5` exits 2 on the same data (proves the comparison is now at one decimal).
- `docs/operations.md`'s "Test coverage" section states the threshold and that it is compared at one decimal place.

### R3-12 The startup context-window check needs its own short timeout

`verify_context_windows` builds `OllamaClient(config, client)`, whose HTTP client uses `limits.request_timeout_seconds` (default 300 s) as the read timeout. Reproduced: the client's timeout is `Timeout(connect=5, read=300, write=300, pool=300)`. If Ollama accepts connections but answers `/api/show` slowly, `check-config` and `serve` block up to 300 s **per configured tag**. A metadata lookup must not inherit the inference timeout.

**Required change.**

- Add `limits.metadata_timeout_seconds: float = Field(default=10, gt=0, le=120)` to `Limits`, documented in `config.example.yaml` and `docs/operations.md`.
- When `verify_context_windows` is called without a client, it creates one with `httpx.Timeout(config.limits.metadata_timeout_seconds, connect=config.limits.connect_timeout_seconds)` and `base_url=config.ollama_base_url`, and closes it when done. When a client is passed (tests), it is used as is.
- `OllamaClient.show` is unchanged; only the client it is given changes.

**Acceptance:**

- A unit test calls `verify_context_windows(config)` with `metadata_timeout_seconds = 0.05` against a mock transport whose `/api/show` handler sleeps 0.5 s (an `httpx.MockTransport` handler can `await asyncio.sleep`); the call raises `ollama_timeout: Ollama request timed out` and completes in under 0.5 s. If `MockTransport` does not enforce `httpx.Timeout`, the test instead asserts the constructed client's `timeout` object equals the expected `Timeout(...)`, and says so in a comment.
- `check-config` against an unreachable Ollama still exits 1 with the existing message; the default `metadata_timeout_seconds` loads from `config.example.yaml`.

## 4. Test strictness

### R3-20 Exact messages for pydantic-wrapped validation errors

`tests/unit/test_config_validation.py` uses `pytest.raises(ValueError, match=message)` for the TC-31 and TC-32 cases. `match` is a regex search, so it is neither exact nor safe for messages containing regex metacharacters.

**Required change.** Add a helper in that file:

```python
def _value_error_message(exc_info: pytest.ExceptionInfo) -> str:
    error = exc_info.value
    if isinstance(error, ValidationError):
        [detail] = error.errors()
        return detail["msg"].removeprefix("Value error, ")
    return str(error)
```

and assert `_value_error_message(exc_info) == message` for every TC-31 and TC-32 case. The `[detail] = error.errors()` unpacking also proves each case produces exactly one validation error.

### R3-21 Boundary and leakage assertions

- `test_two_hundred_selectable_tags_are_allowed` asserts `len(config.allowed_models) == 196` and that all 200 selectable tags (4 profiles + 196 allowed) are distinct.
- `test_auth_header_helper_rejects_invalid_env_var_name` asserts the 64-character token written to the credentials file does not appear in `stderr`, matching the other TC-61 cases.

### R3-22 Test hygiene

- `tests/integration/test_credential_rotation.py`: `test_failed_replacement_restores_already_rotated_files` uses the `_module()` helper instead of inlining the three `importlib` lines; `_module()` moves above its first use.
- The two tests that patch `os.geteuid` / `os.fsync` through `module.os` get a one-line comment stating that `module.os` is the process-wide `os` module and the patch is restored by `monkeypatch`.
- `cli._conversations` takes explicit arguments: `_conversations(database_path: Path, retention_days: int | None, args: argparse.Namespace)`. `main()` passes `config.database_path, config.retention_days`. The `getattr(config, "database_path", config)` duck-typing is removed, and the three test files that call `_conversations` pass the explicit arguments.

## 5. Server

### R3-23 Full log fields in the `call_tool` fallback

The handlers' error log lines carry `request_id`, `rpc_id`, `tool`, `principal`, `status`, `category`, `mode`, `profile`, `model`, `context_limit_tokens`, `history_trimmed`, `elapsed_ms`, `prompt_tokens`, `completion_tokens`, `conversation_id_hash` (R-44). The `SecondBrainMCP.call_tool` fallback line carries only `request_id`, `tool`, `status`, `category`.

**Required change.** The fallback line uses the same field list and order as the handlers. `rpc_id` comes from `self.get_context().request_id` (available inside `call_tool`; if `get_context()` raises because no request is active, use `-`); `principal` comes from the auth ContextVar (`-` when unset); all other fields are `-`.

**Acceptance:** a `caplog` test triggers an argument-validation error (`mode="nope"`) and an unknown-tool error and asserts each resulting record contains every R-44 field name exactly once, with `rpc_id` equal to the JSON-RPC id sent.

### R3-24 Detect unknown tools without matching SDK message text

`_tool_error` recognizes an unknown tool by `str(exc).startswith("Unknown tool")`. An SDK wording change would turn that case into `internal_error`.

**Required change.** In `SecondBrainMCP.call_tool`, before calling `super().call_tool`, check `self._tool_manager.get_tool(name) is None` and return `invalid_input: unknown tool` directly. Remove the string match from `_tool_error`. (`ToolManager.get_tool` is a public method of the SDK's tool manager; it returns `None` for an unknown name.)

**Acceptance:** `tests/integration/test_error_contract.py::test_unknown_tool_is_invalid_input` still passes, and a second test patches `FastMCP.call_tool` to raise `ToolError("Unknown tool: delete_everything")` with no cause for a **known** tool name and asserts the result is `internal_error`, proving the message text is no longer consulted.

## 6. Documentation

### R3-25 Spec erratum and config docs

- `docs/TEST_COVERAGE_SPEC.md` §10: the row for `ollama.py:350→322` says "context-window loop continuing after a not-installed tag"; it is the duplicate-warning branch. Add an `Erratum (2026-10-26):` line under the table rather than rewriting the row, so the original text stays visible.
- `docs/operations.md`: document `metadata_timeout_seconds` (R3-12) and the coverage threshold (R3-11).
- `config.example.yaml`: add `metadata_timeout_seconds: 10` under `limits`.

## 7. Test runtime

### R3-30 Measured budget, not a guess

The third review attributed the suite's growth from 6 s to 12 s mainly to "about a dozen subprocess-based script tests". Per-file call-time totals measured on `c7cf77a` (`pytest --durations=0`) are:

| File | Call time | Notes |
|---|---:|---|
| `tests/unit/test_service.py` | 2.91 s | 50-ask lock tests required by R2-14; not subprocess-based |
| `tests/integration/test_cli.py` | 1.97 s | 8 `check-config` subprocess cases (`test_check_config_reports_errors_without_traceback`) |
| `tests/integration/test_server.py` | 1.61 s | ASGI tests; 20-call concurrency test |
| `tests/unit/test_todo_integrity.py` | 0.87 s | 11 subprocess cases, each creating a git repo |
| `tests/integration/test_access_log_leakage.py` | 0.58 s | real uvicorn; must stay a subprocess |
| `tests/integration/test_credential_rotation.py` | 0.42 s | 7 subprocess cases |

Subprocess tests account for roughly 3.5 s of about 10 s of call time; the rest is breadth. The claim in the review was therefore only partly right, and this document records the correction.

**Required changes.**

1. `test_check_config_reports_errors_without_traceback`: run seven of the eight cases in-process by calling `cli.main()` with a patched `sys.argv` and asserting `SystemExit(1)` plus the exact stderr line via `capsys`; keep **one** case as a subprocess to prove the console entry point exits 1 without a traceback.
2. `tests/unit/test_todo_integrity.py`: call the script's `main(argv)` in-process (it already accepts `argv`) for the parametrized drift cases and the failure cases; keep **one** subprocess test for the entry point. Use one git repository per test as now.
3. `tests/integration/test_credential_rotation.py` and `tests/security/test_auth_headers.py`: load the script once with `_module()` and call `main()` in-process with `monkeypatch.setenv("HOME", …)` / `SECOND_BRAIN_CREDENTIALS_FILE` and patched `sys.argv`; keep **one** subprocess test per script. The "no traceback" assertions become "`main()` returns 1 and raises nothing".
4. Do not change `tests/unit/test_service.py`'s 50-ask tests; R2-14 requires them.

**Acceptance:** plain `uv run pytest -q` completes in **≤ 10 s** wall time on this workstation (median of three runs), test count is unchanged or higher, and coverage (R3-11) still passes. Record the three timings.

## 8. Final verification

### R3-40

All of the following pass on the final commit and are recorded with the commit hash in `docs/REMEDIATION_3_TODO.md`:

- `uv sync --locked`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q` three times, median ≤ 10 s
- the TC-01 coverage command with `fail_under = 99.4`
- `uv run python scripts/check_todo_integrity.py`
- a fresh clone of the final commit passing the same checks

## 9. Traceability: review findings to requirements

| Finding from the third review | Requirements |
|---|---|
| Bug 1: orphan row sets `history_trimmed: true` | R3-10 |
| Bug 2: `fail_under = 99` with precision 0 permits 98.5% | R3-11 |
| Bug 3: `/api/show` check inherits the 300 s inference timeout | R3-12 |
| `match=` is a regex search, not exact | R3-20 |
| `test_two_hundred_selectable_tags_are_allowed` asserts only truthiness | R3-21 |
| Env-var test doesn't assert the token is absent from stderr | R3-21 |
| Duplicated `_module()` code; process-wide `os` patches | R3-22 |
| `_conversations` duck-types its first argument | R3-22 |
| `call_tool` fallback log line lacks R-44 fields | R3-23 |
| Unknown-tool detection by SDK message prefix | R3-24 |
| Spec §10 mislabels `ollama.py:350→322` | R3-25 |
| Test runtime 11.8 s against a 15 s budget; review misattributed the cause | R3-30 |
