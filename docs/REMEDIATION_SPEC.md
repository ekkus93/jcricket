# Second Brain MCP — Remediation Specification

**Status:** Proposed, ready for implementation  
**Date:** 2026-10-26  
**Applies to:** v0.1 working tree as reviewed on 2026-10-26 (uncommitted implementation on `master`, `HEAD` = `5f245be`)  
**Companion task list:** [REMEDIATION_TODO.md](REMEDIATION_TODO.md)  
**Parent specification:** [SPEC.md](SPEC.md)

## 1. Purpose and relationship to SPEC.md

This document specifies the fixes for every finding from the 2026-10-26 code review and TODO verification of the v0.1 implementation. It **supplements** `SPEC.md`; it does not replace it. Where this document is more specific than `SPEC.md` (for example, error codes or transaction boundaries), this document governs the implementation. Where this document requires a change to `SPEC.md` itself, that change is listed explicitly (§12) and must be made in `SPEC.md` so a single source of truth remains.

Requirement IDs (`R-xx`) are referenced by the companion TODO. Every review finding maps to at least one requirement (§13).

### 1.1 Non-goals

- No new MCP tools, resources, or prompts. The public surface stays exactly `ask_second_brain` and `list_models`.
- No remote ChatGPT ingress or OAuth implementation. That remains SB-041–SB-046 in `TODO.md`; this document only constrains the deploy example and prepares the code for it (R-41, R-42).
- No summarization, retrieval, or other deferred backlog items (SB-100+).

### 1.2 Invariants that every change must preserve

1. Ollama receives no `tools` field and the application never executes model output.
2. The principal comes only from verified credentials, never from tool arguments.
3. Every conversation read or write is scoped by principal.
4. Only complete, successful question/answer turns are persisted.
5. The service binds to loopback by default; Ollama must be loopback.
6. Errors and logs never contain bearer tokens, prompt/context/answer text, stack traces, raw SQLite rows, or raw Ollama payloads.

## 2. Process and repository hygiene

### R-01 Commit the implementation

The implementation, packaging, tests, deploy examples, scripts, and docs (`pyproject.toml`, `uv.lock`, `src/`, `tests/`, `deploy/`, `scripts/`, `config.example.yaml`, `docs/operations.md`, `docs/integrations/`, `AGENTS.md`, and the modified `.gitignore`, `README.md`, `docs/TODO.md`) must be committed so that Gate P0 ("fresh checkout installs reproducibly") is true of the repository, not just the working tree.

**Acceptance:** In a fresh clone into an empty directory, `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest` all succeed with no network access to Ollama. No `__pycache__`, `.venv`, database, `config.yaml`, or credentials file is tracked.

### R-02 TODO integrity rules

`docs/TODO.md` items record **requirements**, not outcomes. The following rules apply to every future TODO update:

1. Never reword an item's requirement text when checking it off. Evidence and caveats go in the verification record or as an indented note under the item.
2. Narrowing scope requires an explicit owner decision recorded in the TODO with a date, and, where it contradicts `SPEC.md`, a matching `SPEC.md` change.
3. An item is checked only when every clause of its original text is implemented **and** verified. Partial completion stays unchecked with a note.

Add these rules to the "Working rules" section of `docs/TODO.md`.

### R-03 Restore original TODO wording

Restore the original requirement text from `HEAD:docs/TODO.md` for items that were reworded when checked off, then re-evaluate each checkbox against the restored text:

| Item | Restored requirement (from `HEAD`) | Expected state after restore |
|---|---|---|
| SB-018 | Test all five modes, every profile mapping, approved direct model selection, disallowed/missing names, both selectors supplied, input validation, malformed Ollama output, and timeouts via mocks. | Unchecked until R-51 tests exist |
| SB-019 | Run MCP Inspector against loopback server and confirm exactly two discoverable tools with usable schemas, valid responses, read-only model inventory, and safe errors. | Unchecked until safe errors are confirmed (R-53) |
| SB-031 | … `codex` and `claude-code` credentials (or equivalent secure local mechanism) before any conversation access. | May stay checked after R-21 |
| SB-033 | Provide `.env`/secret provisioning instructions and test token rotation without committing real credentials. | Unchecked until R-34 rotation test exists |
| SB-040 | Inspect the owner's working Ralph Bridge connectivity/auth deployment as a design reference (without copying credentials); verify current ChatGPT workspace/account feature support. | See R-04 |
| SB-063 | Provide separate Codex, Claude Code, and ChatGPT connection guides, `list_models` examples, sample prompts, profile/direct-model selection, troubleshooting, and secure token instructions. | Unchecked (ChatGPT blocked) |
| SB-064 | Document runtime configuration, admin CLI, profile switching, usage reporting, backup, migration, and removal. | Re-verify after R-36 and R-38 doc changes |
| SB-065 | Run `uv sync --locked`, `ruff check`, formatting checks, full mocked pytest suite, and explicit opt-in live integration tests; fix all actionable failures. | Unchecked until R-52 live tests exist in the repo |
| SB-066 | Reconcile TODO checkboxes against code and verified evidence. Document deferred items and exact blockers. Produce v0.1 release notes. | Unchecked until R-05 |

Current blockers and progress notes may be kept as indented notes under each item.

### R-04 Ralph Bridge decision (resolved by owner, 2026-10-26)

The owner chose option **(b): drop the Ralph Bridge design-reference requirement**. Ralph Bridge is not a dependency of this Ollama MCP server. The owner decision and date are recorded under SB-040 in `TODO.md`, and `SPEC.md` §§2.1.10 and 7.2 have been amended to remove the references. SB-040 remains unchecked as a requirement whose scope was explicitly dropped; the decision task is complete.

### R-05 Release notes

Create `docs/RELEASE_NOTES.md` with a v0.1 section listing implemented features, known limitations (including the 4k usable-input size from R-31), external blockers (ChatGPT, systemd lifecycle), and the verification evidence summary. SB-066 is checked only after this exists.

### R-06 `.gitignore` completeness

Add `.serena/`, `*.db`, `*.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, and `credentials.env` (while still allowing `*.env.example`). Keep the existing `*.sqlite3*`, `config.yaml`, and `.env*` rules.

## 3. Model selection and allowlist enforcement

### R-10 Re-validate the stored selection on every continuation

When a continuation omits both `model` and `model_profile`, the server must re-resolve the conversation's stored selection against the **current** configuration before any Ollama call:

| Stored selection | Current config | Behavior |
|---|---|---|
| `model_profile = P` (non-null) | `P` exists | Use the **current** mapping of `P` (tag and budget). If the tag or budget changed, the new selection is persisted with the turn (R-12). |
| `model_profile = P` | `P` no longer exists | Reject with `model_not_approved`; suggest choosing a profile. |
| `model_profile = null`, `model_tag = T` | `T` in `allowed_models` | Use `T` with the **current** configured budget. |
| `model_profile = null`, `model_tag = T` | `T` not in `allowed_models` | Reject with `model_not_approved` ("this conversation's model is no longer approved; choose a model_profile"). |

A stored tag or budget is never trusted on its own. The installed check (R-13) still applies after resolution.

**Acceptance:** Tests show (1) revoking a direct model blocks continuation, (2) remapping a profile's tag makes the continuation use the new tag and persists it, (3) a budget change takes effect on continuation.

### R-11 Explicit selection on continuation

An explicit `model_profile` or `model` on continuation is validated exactly as on a new conversation (profile must exist; model must be in `allowed_models`; not both). It becomes the conversation's selection **only if the turn succeeds** (R-12).

### R-12 Selection changes are part of the successful turn

Persisting a changed selection (profile, tag, budget) must happen in the **same SQLite transaction** as inserting the user/assistant pair. A failed, rejected, timed-out, cancelled, or busy-rejected request leaves the stored selection unchanged.

**Acceptance:** Tests for each failure path (Ollama timeout, Ollama error, busy rejection, cancellation, oversized input) assert that the conversation row is byte-for-byte unchanged afterward.

### R-13 Installed-model check

- The installed check uses the **complete** `/api/tags` list, never a truncated one (see R-15).
- For `ask_second_brain`, only `/api/tags` is needed; do not call `/api/ps` on the ask path.
- Cache the installed-tag set in memory for a short TTL (default 10 seconds, config `limits.inventory_cache_seconds`, `0` disables). On a cache miss or expiry, fetch once and share the result between concurrent callers. Never cache a failure.
- When the tag is missing, the error (`model_not_installed`) names the profile (if any) and the configured tag, for example: `profile 32k maps to tag "qwen35-32k:latest", which is not installed in Ollama`. Tags are already visible to authenticated callers through `list_models`, so naming them is not a disclosure.

### R-14 Enum-typed tool inputs

`ask_second_brain` input schema must declare:

- `mode`: `Literal["discuss", "brainstorm", "critic", "review", "solve"]`, default `"discuss"`.
- `model_profile`: `Literal["4k", "32k", "128k", "256k"] | None`, default `None`.

The service-layer validation stays as a second line of defense. The published JSON schema for these fields must contain `enum` arrays.

### R-15 Bounded, documented `list_models` output

- The maximum number of returned entries is a named constant `MAX_LISTED_MODELS = 200`, documented in `docs/operations.md` and the tool description.
- Add a `truncated: bool` field to `ModelInventory`, `true` when more installed models existed than were returned. Entries for configured profile tags and allowlisted tags must always be included, even when the list is truncated; fill the rest in `/api/tags` order.
- Record this one-field addition in `SPEC.md` §4.2's example output.

## 4. Ollama adapter robustness

### R-16 Fully sanitized inventory parsing

All parsing of `/api/tags` and `/api/ps` happens inside error handling that converts any parsing problem to `OllamaError` (category `ollama_bad_response`). Field-level rules:

- A non-dict entry or an entry whose `name` is not a non-empty string is skipped.
- `details` that is not a dict is treated as `{}`.
- Each optional field (`parameter_size`, `quantization_level`, `size`, `context_length`, `size_vram`) is returned only if it has the expected type (`str` for the first two; non-negative `int` for the rest), otherwise `null`.
- The result must always validate against `ModelInventory`; validation failure there is a bug, not a user-facing error.

**Acceptance:** Parametrized tests with `details: null`, `details: "x"`, `size: "big"`, `context_length: -1`, a non-list `models`, a non-JSON body, HTTP 500 on `/api/tags`, HTTP 500 on `/api/ps`, a timeout on each endpoint, and an empty inventory. Every case yields either a valid inventory or an `OllamaError` with a fixed message.

### R-17 Chat response checks

Keep the existing checks (non-empty string answer, size limit, no `tools`). Additionally:

- After a successful response, if `prompt_eval_count` is present and exceeds the server's prompt estimate (R-30), log a warning `category=estimate_exceeded` with both numbers (no content). This detects estimator drift without failing the request.
- If `prompt_eval_count + eval_count >= num_ctx`, log a warning `category=context_saturated`, because Ollama may have truncated silently.

## 5. Error handling

### R-20 Stable error categories

Every tool failure returned to a client uses the form `<code>: <message>`, where `<code>` is one of:

| Code | When |
|---|---|
| `invalid_input` | Empty question, over-length fields, empty selector strings, both selectors given, unknown mode |
| `conversation_unavailable` | Unknown ID, or an ID owned by another principal (indistinguishable) |
| `model_not_approved` | Unknown profile, unapproved model, revoked stored selection (R-10) |
| `model_not_installed` | Resolved tag absent from `/api/tags` (R-13) |
| `context_too_large` | Current question/context exceeds the prompt budget (R-31 adds a suggestion) |
| `busy` | Admission limit reached (R-32) |
| `ollama_unavailable` | Connection error or non-2xx from Ollama |
| `ollama_timeout` | Any httpx timeout |
| `ollama_bad_response` | Malformed or oversized Ollama payload |
| `unauthorized` | Principal missing in tool context (defensive; middleware should prevent it) |
| `internal_error` | Anything else |

Implement as one exception hierarchy (`SecondBrainError` with a `code` attribute; `ServiceError` and `OllamaError` become subclasses or are replaced) with fixed, pre-written messages.

### R-21 Catch-all sanitization in tool handlers

Each tool handler catches `SecondBrainError` and re-raises it unchanged, and catches **every other `Exception`** (including `sqlite3.Error`, `pydantic.ValidationError`, `AttributeError`, `TypeError`) and raises `internal_error: the server could not complete the request` instead. The original exception type and request ID are logged at `ERROR`; the exception message and traceback are logged only at `DEBUG` and must not contain prompt text (do not log `repr` of arguments). `asyncio.CancelledError` is never caught or converted.

**Acceptance:** Tests inject a `sqlite3.OperationalError` and an `AttributeError` into the service and assert that the client-visible message is exactly the `internal_error` text.

### R-22 Non-ASCII and malformed credentials

Credential comparison must operate on bytes: encode the presented token as `latin-1` (the header encoding) and the expected tokens as UTF-8, then use `hmac.compare_digest` on bytes. Any token that is not printable ASCII returns **401 `invalid credentials`**, never 500. Configured tokens must be printable ASCII; enforce this in `AppConfig.credentials()`.

**Acceptance:** Tests for `Bearer café` (raw byte 0xE9), an empty token, `Bearer` with extra spaces, a lowercase `bearer` scheme, and a token with a trailing newline all return 401 or succeed exactly as specified, never 500.

## 6. Persistence and concurrency

### R-23 Transactional turn recording

Replace the create-then-delete-on-failure pattern with a single store operation:

```text
record_turn(principal, conversation_id | None, selection, question, context, answer, mode)
    -> conversation_id
```

- For a new conversation the ID is generated **before** inference (so it can key the lock) but the `conversations` row is inserted only inside `record_turn`, in the same `BEGIN IMMEDIATE` transaction as the message pair. No conversation row exists while inference is running, and nothing needs deleting on failure.
- For an existing conversation, `record_turn` verifies within the transaction that the row still exists **and** belongs to `principal` (it may have been deleted by the admin CLI during inference). If not, the transaction rolls back and the request fails with `conversation_unavailable`.
- Selection updates (R-12) and `updated_at` are written in the same transaction.

### R-24 Read the conversation inside its lock

The authoritative read of an existing conversation (selection and history) happens **after** acquiring that conversation's lock. A read before the lock may be used only for fast rejection of unknown IDs.

### R-25 Bounded per-conversation locks

Per-conversation locks are reference-counted and removed from the registry when no request holds or waits on them. The registry size must return to zero after all requests finish.

**Acceptance:** A test runs 50 sequential asks on distinct conversations and asserts the registry is empty afterward.

### R-26 Admission control covers the whole request

The admission counter (capacity `concurrency + queue_depth`) is taken at the **start** of `ask` (after cheap input validation, before any store read, inventory fetch, or lock wait) and released in `finally`. A request rejected for capacity performs no Ollama call and no store write. Waiting for a conversation lock counts against admission.

### R-27 Connection lifecycle

Every SQLite connection opened by the store is closed deterministically (for example, a `_connection()` context manager that wraps `contextlib.closing` and commits or rolls back). `with sqlite3.connect(...) as db` alone is not sufficient.

**Acceptance:** A test wraps `sqlite3.connect` to count opens and closes across create, get, history, record, list, delete, and purge, and asserts they are equal.

### R-28 Atomic, idempotent migrations

Each migration step runs inside one explicit transaction (`BEGIN IMMEDIATE` … `PRAGMA user_version = N` … `COMMIT`). SQLite supports transactional DDL; use `isolation_level=None` with explicit `BEGIN`, or equivalent. Column-adding steps must check `PRAGMA table_info(messages)` and skip columns that already exist, so a database left half-migrated by an older build still upgrades.

**Acceptance:** Tests migrate (1) a clean v1 database, (2) a v1 database that already has `model_profile` but not the other two columns, and (3) an injected failure mid-migration, which must leave the database at v1 with no new columns.

### R-29 Multi-process note

Per-conversation serialization is in-process only. Document in `docs/operations.md` that the server must run as a single process (one uvicorn worker), and make `run()` pass `workers=1` explicitly. The `record_turn` ownership check (R-23) keeps the data consistent even if this is violated, but ordering guarantees are not provided across processes.

## 7. Context budgeting

### R-30 Estimator with framing overhead

The prompt estimate is:

```text
estimate = Σ over messages (utf8_bytes(content) + MESSAGE_OVERHEAD_TOKENS) + PROMPT_OVERHEAD_TOKENS
```

with `MESSAGE_OVERHEAD_TOKENS = 8` and `PROMPT_OVERHEAD_TOKENS = 16` as named constants. UTF-8 byte count remains the default per-text upper bound because byte-level tokenizers emit at least one byte per token; the constants cover chat-template framing that the byte count misses.

### R-31 Per-selection completion reserve and usable-size reporting

- `ModelProfile` gains an optional `completion_tokens` override; `allowed_models` values accept either an integer budget (current form) or a mapping `{context_tokens: int, completion_tokens: int | null}`. The effective reserve is the override, else `limits.completion_tokens`.
- `config.example.yaml` sets the `4k` profile's reserve to `1024`, leaving about 2.5 KB of usable input instead of about 1.5 KB.
- Config validation (R-35) guarantees every selection leaves room for the system prompt plus a minimum input.
- The `context_too_large` message includes the approximate maximum input size in bytes for the current selection and names the **smallest configured profile whose budget would fit** the current input, if any (for example, `… exceeds the 4k prompt budget (about 2400 bytes available); try model_profile "32k"`).
- `docs/operations.md` documents the usable input size for each default profile.

### R-32 History inclusion

Keep the current policy (newest complete pairs that fit; `history_trimmed` true if any stored pair is omitted). The pairing must be robust: build pairs by walking the history and pairing each `user` turn with the immediately following `assistant` turn, skipping unpaired rows rather than assuming strict alternation by index.

## 8. Configuration

### R-35 Additional config validation

`AppConfig` validation must reject:

- `log_level` not in `DEBUG | INFO | WARNING | ERROR | CRITICAL` (case-insensitive; normalize to upper case).
- Any profile or allowed model whose `context_tokens - effective_completion_tokens` is less than `estimate(system prompt for the longest mode) + MIN_INPUT_TOKENS` (constant `256`).
- `completion_tokens` greater than or equal to the selection's `context_tokens`.
- A tag listed in `allowed_models` that is also mapped by a profile with a **different** budget. The message tells the administrator to select that tag through the profile instead, so one tag never has two conflicting budgets.
- `token_env` principal names that are not lowercase `[a-z][a-z0-9-]{0,31}` or env var names that are not `[A-Z_][A-Z0-9_]*`.
- `limits.inventory_cache_seconds` outside `0–300`.

`second-brain check-config` must exercise all of these plus `credentials()`.

### R-36 Retention and export configuration

- Add `retention_days: int | null` (default `null`, meaning no automatic purge, as SPEC §6.4 requires).
- `second-brain conversations purge` uses `--older-than` if given, otherwise `retention_days` if set, otherwise fails with a usage message.
- Retention is never applied automatically by the server process. Document a systemd timer example (`deploy/second-brain-purge.timer.example` and `.service.example`) that runs `purge --yes` using configured retention.
- Add `second-brain conversations export [<conversation-id>] [--principal P] [--output FILE]` that writes JSON (conversation metadata plus turns). The output file is created with mode `0600` using `O_CREAT | O_EXCL`; stdout is used when `--output` is omitted.

### R-37 FastMCP environment isolation

`create_app` passes every security-relevant FastMCP setting explicitly (`host`, `port`, `debug=False`, `log_level`, `streamable_http_path`, `json_response`, `stateless_http`, `max_request_body_size`, `transport_security`). Document in `docs/operations.md` that `FASTMCP_*` environment variables and a `.env` file in the working directory can affect the SDK and are unsupported. The systemd example sets `WorkingDirectory` to a directory without a `.env` file.

**Acceptance:** A test sets `FASTMCP_DEBUG=true` and `FASTMCP_HOST=0.0.0.0` and asserts the created app's settings are unchanged.

### R-38 CLI structure

Rebuild the CLI with `argparse` subparsers so each command accepts only its own arguments:

```text
second-brain [--config PATH] serve
second-brain [--config PATH] check-config
second-brain [--config PATH] conversations list [--principal P]
second-brain [--config PATH] conversations show <id>
second-brain [--config PATH] conversations delete <id> [--yes]
second-brain [--config PATH] conversations purge [--older-than DAYS] [--yes]
second-brain [--config PATH] conversations export [<id>] [--principal P] [--output FILE]
```

- `show` and `delete` look up the single row by ID (add `ConversationStore.get_any(id)` for admin use) instead of listing every conversation.
- `delete` asks for confirmation unless `--yes` is given.
- Confirmation prompts treat EOF or a non-interactive stdin as "no" and exit with status 1 and the message `Cancelled.`
- Admin commands must not require bearer-token environment variables.

## 9. Authentication, logging, and HTTP surface

### R-40 Remove redundant and dead code

- Remove the duplicate distinct-token check in `server.py` (`config.credentials()` already enforces it) and the empty-credentials check that can never trigger.
- Remove the unreachable `/healthz` route from the Starlette app; the middleware owns `/healthz`. Keep a test that `/healthz` returns `{"status":"ok"}` without auth and without a valid Host (it reveals nothing).

### R-41 Principal propagation safeguard

Keep the ContextVar mechanism for local auth, but add a regression test that issues concurrent `tools/call` requests from both principals (for example, 20 interleaved calls through `httpx.AsyncClient` with an ASGI transport) and asserts every call observes its own principal. This protects against SDK changes in how stateless requests spawn tasks. Also set `scope["user"]` to an object carrying the principal so the code can move to the SDK's `AuthenticatedUser` / `TokenVerifier` path when SB-042 (OAuth) is implemented. Record that migration as a design note in `SPEC.md` §7.2.

### R-42 Deploy example correctness

`deploy/reverse-proxy.example` must not defeat the application's Host check:

- Remove `proxy_set_header Host 127.0.0.1:8000;`. Instead, add an `AppConfig.trusted_hosts: list[str]` (default empty; each entry a bare DNS name, validated) that the middleware and `TransportSecuritySettings` accept in addition to loopback names, and pass the original `Host`.
- Mark the example at the top as **non-functional until SB-041/SB-042 are complete**, because the local bearer tokens are not a remote authentication mechanism and remote Origin policy is not defined yet.
- Do not forward client `Authorization` headers to the app until the remote principal design exists.

### R-43 Request correlation IDs

The middleware generates a server-side request ID (`uuid4().hex`) for every HTTP request, stores it in a ContextVar, and returns it in an `X-Request-ID` response header (including on 401/403/404/429). Tool logs use this ID. The JSON-RPC `id` may be logged separately as `rpc_id`.

### R-44 Log contents

Each tool log line contains: `request_id`, `rpc_id`, `tool`, `principal`, `status`, `category` (error code), `mode`, `profile`, `model` (exact tag), `context_limit_tokens`, `history_trimmed`, `elapsed_ms`, `prompt_tokens`, `completion_tokens`. It never contains question, context, answer, conversation contents, the `Authorization` header, or tokens. The conversation ID may be logged only as a truncated SHA-256 prefix (8 hex characters).

**Acceptance:** A `caplog` test runs a successful ask, a failed ask, an unauthenticated request, and an invalid-token request with distinctive marker strings in the question, context, answer, and tokens, and asserts none of the markers appear in any captured log record or in uvicorn access logs.

## 10. Credentials tooling and documentation

### R-34 Credential helper and rotation

- `deploy/auth_headers.py` accepts `principal` plus optional `--env-var NAME` (default from the built-in `codex`/`claude-code` map) so additional principals do not require editing the script.
- Clarify in `docs/integrations/local-clients.md` and `docs/operations.md` that the **user** credential file (`~/.config/second-brain/credentials.env`, mode `0600`, read by the helper and `scripts/run_local.sh`) and the **service** credential file (`/etc/second-brain/credentials.env`, `root:second-brain` `0640`, read by systemd) are different files. Remove the claim that the helper reads the service file. Rotation must update both when both are used.
- Add `scripts/init_credentials.py --rotate`, which writes new tokens to a temporary `0600` file and atomically replaces the existing file (keeping a `0600` `.bak` of the previous file), then prints the restart and reconnect steps.
- **Rotation test:** with the app built from tokens A, a request with A succeeds; rebuilding the app after rotation to tokens B makes A fail with 401 and B succeed.

### R-39 Documentation corrections

- `docs/operations.md`: single-process requirement (R-29), usable input size per profile (R-31), `MAX_LISTED_MODELS` and `truncated` (R-15), retention and export (R-36), FastMCP environment note (R-37), error codes table (R-20), `X-Request-ID` (R-43).
- `README.md`: list error codes briefly and link to operations.
- `docs/integrations/local-clients.md`: credential file distinction (R-34).

## 11. Testing

### R-50 Test layout

Split tests into `tests/unit/`, `tests/integration/` (in-process ASGI app plus mocked Ollama), `tests/security/`, and `tests/live/` as SPEC §9 suggests. Shared fixtures stay in `tests/conftest.py`.

### R-51 Required mocked tests

In addition to tests named elsewhere in this document, the mocked suite must cover:

1. **Modes:** for each mode, the system prompt contains the base prompt and only its own mode instruction; all five prompts are pairwise distinct; an unknown mode is rejected at the schema level and at the service level.
2. **Profiles:** each of the four profiles maps to its configured tag and budget, and the default with no selector is `32k`.
3. **Selectors:** approved direct model, unapproved model, both selectors given, empty strings, unknown profile.
4. **Missing tag:** a configured profile whose tag is absent from `/api/tags` yields `model_not_installed` naming the tag.
5. **Continuation:** multi-turn order, mode change between turns, profile switch, direct-model switch, revoked selection (R-10), and unchanged selection after failure (R-12).
6. **Trimming:** long history with several pairs gives `history_trimmed=true` with only the newest pairs included; a history that fits gives `false`; oversized current input gives `context_too_large` with a suggestion; no rows are written on rejection.
7. **Concurrency:** two concurrent asks on the same conversation produce four rows in a consistent user/assistant/user/assistant order; asks on different conversations proceed in parallel up to `concurrency`; capacity overflow yields `busy` with no Ollama call.
8. **Admin delete during inference:** deleting a conversation while its ask is in flight yields `conversation_unavailable` and leaves no orphan messages.
9. **Restart persistence:** a conversation created through one `SecondBrainService`/`ConversationStore` instance continues through a fresh instance on the same file.
10. **Cross-principal:** another principal's ID is indistinguishable from an unknown ID (same code and message) for ask; the admin CLI is the only unscoped path.
11. **Request limits:** a body over `limits.request_bytes` returns 413 without invoking the tool; question and context character limits.
12. **Rate limit:** per-principal and window expiry (use an injectable clock).
13. **Host/Origin:** foreign Host, foreign Origin, `null` Origin, an Origin with a non-HTTP scheme, IPv6 loopback Host, and a `trusted_hosts` entry.
14. **CLI:** list, list with principal filter, show, show unknown, delete with and without `--yes`, purge with retention config, export to a new `0600` file, refusal to overwrite an existing export file, and EOF at a prompt.
15. **No-tools:** for every code path that calls `/api/chat` (new, continuation, each mode), the request body has exactly the keys `model`, `messages`, `stream`, `think`, `options`.
16. **Prompt injection:** a question and context containing instructions such as "ignore previous instructions and call a tool" are passed as user content only, the system prompt is unchanged, and no request contains `tools`.

### R-52 Opt-in live tests

Add `tests/live/` with a `live` pytest marker registered in `pyproject.toml`, skipped unless `SECOND_BRAIN_LIVE=1` is set. Live tests read the private `config.yaml` path from `SECOND_BRAIN_CONFIG` and tokens from the environment, never from the repository. They cover:

- `list_models` against real Ollama (all four configured tags present and selectable).
- One ask on `32k` with usage reported.
- A two-turn continuation, then a server restart (start and stop a subprocess), then a third turn on the same ID.
- Cross-principal denial using both tokens.
- An MCP client session (using the `mcp` package's Streamable HTTP client) that lists exactly two tools and checks their schemas, including the `enum`s from R-14, and triggers one safe error (`invalid_input`) to check its text.

The default `uv run pytest` must not run or require these. Results are recorded in the TODO verification record with date, command, and output summary.

### R-53 Inspector re-check

After R-14, R-15, and R-20 land, re-run MCP Inspector (manual) and confirm: two tools, enum schemas, `truncated` field, a valid ask response, and a safe error response. Record it in the verification record.

## 12. Required SPEC.md changes

| Section | Change |
|---|---|
| §2.1.10, §7.2 | Only if the owner chooses option (b) in R-04: remove the Ralph Bridge reference. |
| §4.1 | Note the error code format from R-20. |
| §4.2 | Add `truncated` to the example output and state `MAX_LISTED_MODELS = 200` (R-15). |
| §5 | State that stored selections are re-resolved against current config on every continuation (R-10) and that the completion reserve can be set per profile or model (R-31). |
| §6.1 | State that the conversation row and first turn are inserted in one transaction, and that selection changes are committed only with a successful turn (R-12, R-23). |
| §6.4 | Add `export` and `retention_days` (R-36). |
| §7.2 | Add the design note about moving to SDK-native auth for OAuth (R-41) and `trusted_hosts` (R-42). |
| §8 | Single-process deployment (R-29); `X-Request-ID` (R-43). |

## 13. Traceability: review findings to requirements

| Review finding | Requirements |
|---|---|
| Implementation uncommitted; SB-002 and Gate P0 false | R-01 |
| TODO items reworded when checked off | R-02, R-03 |
| SB-040 contradicts SPEC | R-04 |
| SB-066 checked without release notes | R-03, R-05 |
| Bug 1: revoked allowlist or remapped profile ignored on continuation | R-10 |
| Bug 2: selection change persisted on failure | R-11, R-12, R-23 |
| Bug 3: malformed inventory leaks `AttributeError` / `ValidationError` | R-16, R-21 |
| Bug 4: non-ASCII bearer token gives HTTP 500 | R-22 |
| Bug 5: request ID is client JSON-RPC id; model tag not logged | R-43, R-44 |
| Bug 6: 200-entry truncation breaks installed check; cap undocumented | R-13, R-15 |
| Bug 7: approved budget ≤ completion reserve accepted | R-35 |
| Bug 8: conversation read outside lock | R-24 |
| Bug 9: unbounded lock registry; queue depth incomplete | R-25, R-26 |
| Bug 10: SQLite connections not closed | R-27 |
| Bug 11: non-atomic migration | R-28 |
| Bug 12: `log_level` unvalidated | R-35 |
| Unexpected exceptions return raw text | R-20, R-21 |
| `mode` / `model_profile` not enums | R-14 |
| 4k profile nearly unusable; global reserve; framing not counted | R-30, R-31 |
| History pairing assumes strict alternation | R-32 |
| Duplicate distinct-token check; dead `/healthz` route | R-40 |
| ContextVar auth relies on SDK internals | R-41 |
| Helper hardcodes principal map | R-34 |
| Credential file doc drift (0640 vs 0600; "same file") | R-34, R-39 |
| Token rotation untested | R-34 |
| Reverse-proxy example defeats Host check and cannot work | R-42 |
| Two extra HTTP calls per ask | R-13 |
| `.gitignore` gaps | R-06 |
| FastMCP reads `FASTMCP_*` and `.env` | R-37 |
| Export and configurable retention missing | R-36 |
| CLI argument structure; `show` lists everything; EOF on prompt | R-38 |
| Missing tests (queue, 413, switch, missing tag, concurrency, CLI, log leakage) | R-44, R-51 |
| Weak mode test | R-51 (1) |
| No repeatable live tests in repo | R-52 |
| SB-019 "safe errors" never confirmed | R-53 |
| Single-process assumption undocumented | R-29 |
