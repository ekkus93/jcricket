# Second Brain MCP — Unit Test Coverage Specification

**Status:** Proposed, ready for implementation  
**Date:** 2026-10-26  
**Applies to:** `master` at `588dbfb` ("Document the one-variant-per-profile requirement")  
**Companion task list:** [TEST_COVERAGE_TODO.md](TEST_COVERAGE_TODO.md)  
**Parent documents:** [SPEC.md](SPEC.md), [REMEDIATION_SPEC.md](REMEDIATION_SPEC.md), [REMEDIATION_2_SPEC.md](REMEDIATION_2_SPEC.md)

## 1. Purpose

A coverage run on 2026-10-26 (mocked suite: 202 passed, 1 skipped) found that the core modules are well covered (90–100% of lines), but most of the remaining gaps are error paths, plus a few core behaviors that never execute in any test. This document specifies the tests that close those gaps, the tooling to measure coverage honestly (including code run in subprocesses), and two small code changes the work exposed.

Requirement IDs are `TC-xx`. Tasks in the companion TODO are `TCT-xxx`. §10 maps every uncovered line or branch from the baseline run to a requirement.

### 1.1 Baseline (2026-10-26, `coverage run --branch`, subprocesses not traced)

| Module | Stmts | Miss | Branch | Partial | Cover |
|---|---:|---:|---:|---:|---:|
| `src/second_brain_mcp/auth.py` | 92 | 3 | 22 | 2 | 96% |
| `src/second_brain_mcp/cli.py` | 124 | 48 | 54 | 8 | 61% |
| `src/second_brain_mcp/config.py` | 171 | 13 | 62 | 11 | 90% |
| `src/second_brain_mcp/ollama.py` | 195 | 16 | 56 | 10 | 90% |
| `src/second_brain_mcp/prompts.py` | 8 | 2 | 0 | 0 | 75% |
| `src/second_brain_mcp/server.py` | 109 | 2 | 10 | 1 | 97% |
| `src/second_brain_mcp/service.py` | 160 | 5 | 68 | 7 | 95% |
| `src/second_brain_mcp/store.py` | 134 | 2 | 24 | 4 | 96% |
| `budget.py`, `errors.py`, `schemas.py`, `__init__.py` | — | 0 | — | 0 | 100% |
| `scripts/init_credentials.py` | 100 | 38 | 30 | 4 | 63% |
| `scripts/check_todo_integrity.py` | 100 | 100 | 42 | 0 | 0% |
| `deploy/auth_headers.py` | 49 | 49 | 18 | 0 | 0% |

The `cli.py`, `scripts/`, and `deploy/` figures understate real coverage, because their tests run them as subprocesses, which this run did not trace. TC-01 fixes the measurement.

### 1.2 Non-goals

- No new features and no changes to the MCP tool surface.
- No changes to behavior, except the two defects or dead code listed in §8. Any other defect a new test exposes is handled by TC-03.
- No tests that need Ollama, a GPU, the network, or real credentials. The opt-in live test is unchanged.

## 2. Test principles

### TC-02 How the new tests are written

- **Assert behavior, not lines.** Each test checks an observable outcome: the exact error text (`<code>: <message>` or the exact `ValueError` message), the return value, the files written, the HTTP status, or the log record. A test that only executes a line without asserting its effect does not count.
- **Use public entry points first.** Prefer `SecondBrainService.ask`, `OllamaClient` methods, `AppConfig` / `load_config`, `ConversationStore`, the ASGI app, and the CLI entry points. Call a private helper directly only when no public path reaches the branch, and say so in a comment.
- **Mock only the boundary.** Mock Ollama with `httpx.MockTransport`; never patch the code under test.
- **Follow the existing layout.** Unit tests go in `tests/unit/`, ASGI/CLI/subprocess tests in `tests/integration/`, and auth or credential-handling tests in `tests/security/`. Reuse `tests/conftest.py` fixtures (`app_config`, `mock_ollama`, `make_conversation`).
- **Stay fast.** The default `uv run pytest` must stay under 15 seconds on this workstation.

### TC-03 Defects found by new tests

If a new test fails because the code is wrong, not the test:

1. keep the failing test;
2. record the failure as fail-first evidence;
3. fix the code in the same task;
4. note the defect in the task's `Evidence:` lines.

If the right behavior is unclear, leave the task unchecked with a `Note:` and ask the owner. Never weaken a test to make it pass.

## 3. Coverage tooling

### TC-01 Honest, repeatable measurement

- Add `coverage[toml]>=7.10` to the `dev` dependency group and update `uv.lock`. Version 7.17.0 is available in the local `uv` cache, so this works offline.
- Add `[tool.coverage.run]` to `pyproject.toml` with:
  - `branch = true`;
  - `source = ["src/second_brain_mcp", "scripts", "deploy"]`;
  - `parallel = true`;
  - `patch = ["subprocess"]`, so code run through `subprocess` (CLI, scripts, the uvicorn leakage test) is measured.
- Add `[tool.coverage.report]` with `show_missing = true`, `skip_covered = false`, and `fail_under` (set by TC-70).
- Document one command in `docs/operations.md` (under a new "Test coverage" heading):

  ```sh
  uv run coverage erase && uv run coverage run -m pytest -q && uv run coverage combine && uv run coverage report
  ```

- Coverage stays out of the default `uv run pytest`, which keeps that command fast and dependency-light.
- Ignore coverage data files (`.coverage`, `.coverage.*`) in `.gitignore`. They are already ignored; verify.

**Acceptance:** the documented command runs offline. The report for `deploy/auth_headers.py` and `scripts/check_todo_integrity.py` is above 0%, which proves subprocesses are measured.

## 4. Group 1 — Ollama adapter error paths (`ollama.py`)

### TC-10 Chat response limits and failures

Through `OllamaClient.chat` with a mock transport:

- An answer whose UTF-8 size exceeds `limits.response_bytes` raises `OllamaError` with text `ollama_bad_response: Ollama returned malformed data` (`ollama.py:79-80`).
- HTTP 500 from `/api/chat` raises `ollama_unavailable: Ollama is unavailable or rejected the request` (`:110-111`).
- A 200 response with a non-JSON body raises `ollama_bad_response: …` (`:112-113`).
- An answer exactly at the byte limit is accepted. This is a boundary test.

### TC-11 Ollama unavailable on the ask path

Through `SecondBrainService.ask`:

- `/api/tags` connection refused gives exactly `ollama_unavailable: Ollama is unavailable or rejected the request`, with no conversation row written (`:288-291`).
- `/api/tags` timeout gives `ollama_timeout: Ollama request timed out` (`:288-289`).
- `/api/tags` returning `{"models": "nope"}` or a non-JSON body gives `ollama_bad_response: …` (`:279-280`, `:292-293`).
- With `limits.inventory_cache_seconds: 0`, two consecutive asks make two `/api/tags` requests (`:259-260`). With the default TTL they make one; that case is already covered and stays.

### TC-12 `/api/show` failures

Through `OllamaClient.show` and `verify_context_windows`:

- HTTP 500 → `ollama_unavailable`.
- A timeout → `ollama_timeout`.
- A JSON body that is a list → `ollama_bad_response` (`:228-229`).
- A non-JSON body → `ollama_bad_response` (`:249-254`).
- A `parameters` field that isn't a string, and a `model_info` value that isn't an integer, are treated as absent rather than raising.

### TC-13 Inventory parsing edge cases

Through `OllamaClient.models`:

- `/api/ps` entries that are not objects, or that have a missing or blank `name`, are ignored; the corresponding installed model reports `loaded: false` (`:141-145`).
- A tag listed twice in `/api/tags` appears once in the result (`:160-161`).
- An `/api/tags` or `/api/ps` body that is a JSON list, not an object, gives `ollama_bad_response` (`:126-127`).

## 5. Group 2 — Continuation and validation in the service (`service.py`)

### TC-20 Direct-model continuation (core behavior that never runs today)

Create a conversation with `model="other:tag"` (an allowed model). Change the config's budget for `other:tag`, then continue the conversation **without** `model` or `model_profile`. The response has `model: "other:tag"`, `model_profile: null`, and the **new** budget, and the stored conversation row has the new budget (`service.py:198-210`, in particular `:205`).

### TC-21 Stored profile no longer configured

A conversation row whose `model_profile` names a profile that is not in the current config (insert it with `record_turn` and a `ModelSelection("legacy", …)`) fails on continuation with exactly `model_not_approved: this conversation's profile is no longer approved; choose a profile`. No turn is written (`:184-191`).

Config validation always requires the four standard profiles, so this guards rows written by older or hand-edited configurations.

### TC-22 Remaining service validation branches

- A direct model that is approved but missing from `/api/tags` fails with exactly `model_not_installed: model tag "other:tag" is not installed in Ollama` (`:62→67`).
- `conversation_id="   "` fails with `invalid_input: conversation_id must not be empty` (`:130`).
- Calling `service.ask` directly with `mode="nope"` fails with `invalid_input: mode is not supported` (`:136`). The MCP schema rejects it earlier for MCP clients, but direct callers rely on this check.
- A history whose first stored row is an orphan `assistant` turn builds messages without it (`:280→285`).

## 6. Group 3 — Credential and config validation (`config.py`)

### TC-30 Credentials

Through `AppConfig.credentials()` with environment variables set by `monkeypatch`:

- A `token_env` without `claude-code` fails with `token_env must map distinct credentials for codex and claude-code` (`config.py:222`).
- A 31-character token fails with `bearer tokens must contain at least 32 characters for principals: codex` (`:243`).
- Two principals with the same token fail with `each configured principal must use a distinct token` (`:259`).
- Valid distinct tokens return the principal-to-token map.

### TC-31 Ollama URL

- `ftp://127.0.0.1` and `http://` (no host) fail with `ollama_base_url must use http or https and include a host` (`:207`).
- `http://localhost:11434`, `http://127.0.0.1:11434/`, and `http://[::1]:11434` are accepted. A trailing `/` is stripped (`:211-214`).
- `http://example.com` and `http://10.0.0.5:11434` fail with `ollama_base_url must point to a loopback address`.

### TC-32 Remaining field validation

Each case fails with the exact message:

| Input | Message | Line |
|---|---|---|
| `default_profile: "64k"` | `default_profile must be one of 4k, 32k, 128k, 256k` | `:136` |
| profile `4k` with `context_tokens: 8192` | `profile context token budgets must match their names` | `:115` |
| `trusted_hosts: ["a.example", "A.example"]` | `trusted_hosts entries must be unique` | `:94` |
| `allowed_models: ["x"]` | `allowed_models must be a mapping` | `:122` |
| `allowed_models: {"   ": 8192}` | `allowed model tags and context budgets must be valid` | `:127` |
| 4 profiles + 197 distinct allowed models | `no more than 200 distinct selectable model tags are allowed` | `:190` |
| YAML file containing a list at the top level | `configuration root must be a mapping` (wrapped by `load_config` as `invalid configuration in <path>: …`) | `:290` |

## 7. Group 4–6 — Store, HTTP surface, CLI, and helper scripts

### TC-40 Store data safety (`store.py`)

- Opening a database with `PRAGMA user_version = 3` raises `RuntimeError("conversation database schema is newer than this application")`, and the file is left unchanged (`store.py:82-83`).
- `purge(0)` and `purge(-1)` raise `ValueError("older_than_days must be positive")` and delete nothing (`:278-279`).
- A version-1 database that already has all three round-2 columns migrates to version 2 without altering the table (`:132→134`, `:134→138`).

### TC-50 HTTP and error-contract edges

- `GET /unknown` and `POST /mcp/extra` return 404 with body `{"error":"not found"}` and an `X-Request-ID` header (`auth.py:94-96`).
- `current_principal()` with no authenticated principal raises `SecondBrainError` whose text is exactly `unauthorized: authenticated principal required` (`auth.py:29-30`).
- **Tool-error fallback** (`server.py:67-72`): when `FastMCP.call_tool` raises `ToolError("boom")` caused by `RuntimeError("secret-marker")`, `SecondBrainMCP.call_tool` returns `isError: true` with exactly `internal_error: the server could not complete the request`. Patch the parent class method, which is a boundary of our subclass. The response must not contain `secret-marker` or `boom`, and an ERROR log record must include `unexpected_error_type=RuntimeError`.

### TC-60 Admin CLI (`cli.py`)

In-process tests that call `_conversations` or `main()` with a patched `sys.argv`:

- `conversations get-any <id>` prints the conversation's metadata JSON. An unknown ID exits with `conversation not found` (`cli.py:92-95`).
- `conversations export` with no ID prints a JSON list of every conversation to stdout. With `--principal codex` it lists only that principal's conversations (`:122-131`).
- `conversations export <unknown-id> --output FILE` exits with `conversation not found` and creates no file (`:127-128`).
- `conversations purge` with no `--older-than` and no `retention_days` exits with `purge requires --older-than or configured retention_days` (`:111`).
- Interactive confirmation (stdin is a TTY, input `y`) deletes the conversation (`:155-159`).
- `main()` dispatch:
  - `check-config` with a valid config, valid tokens, and a patched `verify_context_windows` prints `Configuration is valid.`;
  - `conversations list` prints the list;
  - `serve` calls `server.run` with the loaded config, patched so no server starts.

  This covers `cli.py:20-63` in-process.
- `system_prompt("nope")` raises `ValueError("unsupported mode: nope")` (`prompts.py:35-36`).

### TC-61 `deploy/auth_headers.py` failure cases

As subprocess tests, which are measured once TC-01 lands:

- `--env-var bad-name` exits 2 with `environment variable name is invalid`.
- A credential line without `=` exits 1 with `cannot read local MCP credentials: credential file contains a malformed assignment`.
- A 20-character token exits 1 with `cannot read local MCP credentials: configured bearer token is missing or too short`.
- A missing credentials file exits 1 with stderr starting `cannot read local MCP credentials:`.
- A quoted value (`CODEX_MCP_TOKEN="…"`) is printed without the quotes.
- In every case, stdout is empty on failure, and the token never appears in stderr.

### TC-62 `scripts/check_todo_integrity.py` failure cases

- An unknown baseline commit reports `<path>: baseline <commit> could not be read` and exits 1.
- A missing TODO file reports `<path>: file could not be read` and exits 1.
- `--baseline TODO.md` (no `@`) exits 2 with `--baseline must use PATH@COMMIT`.

### TC-63 `scripts/init_credentials.py` failure cases

- **Rotate, missing file:** `--rotate` with no existing user file exits 1 with `cannot rotate credentials: credentials file does not exist: <path>` and no traceback.
- **Create, existing file** (see §8, TC-81): running without `--rotate` when the file already exists exits 1 with `credentials file already exists: <path>; use --rotate to replace its tokens`, no traceback, and the existing file unchanged.

## 8. Code changes exposed by this work

### TC-80 Remove an unreachable branch (`service.py:171-183`)

When a new conversation has no selector, `_selection` looks up `config.default_profile` and raises `model_not_approved: no model profile is configured` if it is missing. Config validation guarantees the default profile is one of the four required profiles, so that branch cannot run. Remove the `None` check and index the profile directly, with a one-line comment naming the validator that guarantees it.

**Acceptance:** `test_default_selection_is_32k` still passes; the branch no longer exists; no other behavior changes.

### TC-81 Creating credentials over an existing file crashes

`scripts/init_credentials.py` without `--rotate` uses `O_CREAT | O_EXCL`, which correctly refuses to overwrite. But the resulting `FileExistsError` escapes as a traceback (reproduced on 2026-10-26), while `docs/integrations/local-clients.md` says the script "refuses to overwrite an existing file". Catch the error, print `credentials file already exists: <path>; use --rotate to replace its tokens` to stderr, and exit 1.

The TC-63 test must be shown failing before the fix (TC-03).

## 9. Coverage gate and verification

### TC-70 Coverage targets

After all tasks, the TC-01 command must report:

| Scope | Line + branch target |
|---|---|
| `src/second_brain_mcp` (combined) | **≥ 97%** |
| `scripts/` and `deploy/` (combined) | **≥ 90%** |
| Every line and branch listed in §10 | Covered, except where §10 says "removed" |

- Set `fail_under` in `[tool.coverage.report]` to the achieved total, rounded down to a whole number, so coverage cannot silently drop.
- Record the final per-module table in the TODO's verification record.
- Do not add `# pragma: no cover` to reach a target. Any exclusion needs a `Note:` in the TODO explaining why the line cannot be tested, and owner agreement.

### TC-71 Final verification

All of the following pass on the final commit, and are recorded with the commit hash:

- `uv sync --locked`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q` (still under 15 seconds)
- the TC-01 coverage command, meeting TC-70
- `uv run python scripts/check_todo_integrity.py`

## 10. Traceability: uncovered code to requirements

| Location (at `588dbfb`) | What is untested | Requirement |
|---|---|---|
| `ollama.py:79-80` | response-size limit | TC-10 |
| `ollama.py:110-113` | chat HTTP error, malformed JSON | TC-10 |
| `ollama.py:126-127` | non-object `/api/tags` or `/api/ps` body | TC-13 |
| `ollama.py:141-145`, `:160-161` | `/api/ps` entry filtering, duplicate tags | TC-13 |
| `ollama.py:228-229`, `:238→248`, `:249-254` | `/api/show` malformed body and failures | TC-12 |
| `ollama.py:259-260` | inventory cache disabled | TC-11 |
| `ollama.py:279-280`, `:288-293` | installed-tag lookup failures on the ask path | TC-11 |
| `ollama.py:350→322` | context-window loop continuing after a not-installed tag | TC-12 |
| `service.py:62→67` | `model_not_installed` for a direct model | TC-22 |
| `service.py:130`, `:136` | empty `conversation_id`, unknown mode (service level) | TC-22 |
| `service.py:175` | default profile missing (unreachable) | TC-80 (removed) |
| `service.py:187` | stored profile no longer configured | TC-21 |
| `service.py:205` | direct-model continuation | TC-20 |
| `service.py:280→285` | orphan `assistant` row in history | TC-22 |
| `config.py:94`, `:115`, `:122`, `:127`, `:136`, `:190`, `:290` | field validation messages | TC-32 |
| `config.py:207`, `:211-214` | Ollama URL scheme and loopback forms | TC-31 |
| `config.py:222`, `:243`, `:259` | credential validation | TC-30 |
| `store.py:83`, `:279`, `:132→134`, `:134→138` | newer schema, bad purge age, migration branches | TC-40 |
| `auth.py:30`, `:95-96` | unauthorized safeguard, 404 for unknown paths | TC-50 |
| `server.py:67-72` | tool-error fallback to `internal_error` | TC-50 |
| `cli.py:20-63`, `:92-95`, `:111`, `:122-131`, `:155-159` | parser and dispatch in-process, admin paths | TC-60 |
| `prompts.py:35-36` | unknown mode | TC-60 |
| `deploy/auth_headers.py` (subprocess only) | failure paths and measurement | TC-01, TC-61 |
| `scripts/check_todo_integrity.py` (subprocess only) | failure paths and measurement | TC-01, TC-62 |
| `scripts/init_credentials.py:22-49`, `:58`, `:65-70` | create over existing file, rotate missing file | TC-63, TC-81 |
| `scripts/init_credentials.py:106`, `:113-116`, `:128` | staging failure cleanup, restore on failure | TC-01 measurement first; add tests if still uncovered |

**Erratum (2026-10-26):** the row for `ollama.py:350→322` above describes that branch as the context-window loop "continuing after a not-installed tag". It is actually the duplicate-warning branch (a second selection whose tag already produced the same "does not pin num_ctx" warning). The not-installed case is covered by `test_context_window_check_continues_after_missing_tag`; the duplicate-warning branch by `test_context_window_warning_is_reported_once_per_tag`. The original row is left unchanged for traceability.
