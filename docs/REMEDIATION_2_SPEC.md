# Second Brain MCP — Remediation Round 2 Specification

**Status:** Proposed, ready for implementation  
**Date:** 2026-10-26  
**Applies to:** `master` at `ad85cdb` ("Record final remediation verification")  
**Companion task list:** [REMEDIATION_2_TODO.md](REMEDIATION_2_TODO.md)  
**Parent documents:** [SPEC.md](SPEC.md), [REMEDIATION_SPEC.md](REMEDIATION_SPEC.md)

## 1. Purpose and relationship to other documents

This document specifies fixes for every finding from the second code review and TODO check (2026-10-26) of the round-1 remediation. It **supplements** `SPEC.md` and `REMEDIATION_SPEC.md`. Where it is more specific, it governs. Where it changes behavior that `SPEC.md` or `REMEDIATION_SPEC.md` describes, the change is listed in §9 and must be made in those documents.

Requirement IDs are `R2-xx`. Tasks in the companion TODO are `RM2-xxx`. §10 maps every review finding to its requirements.

### 1.1 Non-goals

- No new MCP tools, resources, or prompts. The public surface stays exactly `ask_second_brain` and `list_models`.
- No remote ingress, OAuth, or ChatGPT work (SB-041–SB-046, SB-054 remain blocked).
- No deferred backlog items (SB-100+).

### 1.2 Invariants

All invariants in `REMEDIATION_SPEC.md` §1.2 still apply: no `tools` sent to Ollama; principal only from verified credentials; principal-scoped conversation access; only complete successful turns persisted; loopback binding; no secrets, prompt text, stack traces, raw rows, or raw Ollama payloads in client errors or logs.

## 2. Process integrity

The first two rounds both ended with a task's requirement or acceptance check rewritten or removed when the task was checked off. This section makes that mechanically detectable and corrects the records.

### R2-01 Acceptance checks are part of the requirement

In every TODO file in `docs/`, the item line **and** its `Test:` / `Acceptance:` sub-bullets are requirement text. They must never be edited or removed when an item is checked. Evidence, caveats, and SDK limitations go in an additional sub-bullet that starts with `Note:` or `Evidence:`, or in the verification record.

If an acceptance check cannot be met as written, the item stays **unchecked** with a `Note:` explaining why, until either the check is met or the owner records a dated decision to change it (written under the item as `Owner decision (YYYY-MM-DD): …`).

Add this rule to the working rules of `docs/TODO.md`, `docs/REMEDIATION_TODO.md`, and `docs/REMEDIATION_2_TODO.md`.

### R2-02 TODO integrity checker

Add `scripts/check_todo_integrity.py`, runnable as `uv run python scripts/check_todo_integrity.py`. It needs only the standard library and `git`.

- **Inputs:** a list of `(todo_path, baseline_commit)` pairs defined in the script:
  - `docs/TODO.md` against `5f245be`
  - `docs/REMEDIATION_TODO.md` against `ca3a444`
  - `docs/REMEDIATION_2_TODO.md` against the commit that first adds it
- **Parsing:** an item is a line matching `- [ ] **ID** text` or `- [x] **ID** text`. Its requirement sub-bullets are the directly indented lines starting with `- Test:` or `- Acceptance:`. Gate lines (`**Gate …:**`) are also requirement text.
- **Checks**, each reported with the item ID:
  1. Every baseline item still exists.
  2. Every baseline item's text is identical, apart from the checkbox state.
  3. Every baseline `Test:` / `Acceptance:` sub-bullet still exists under the same item, unchanged.
  4. Every baseline gate line is unchanged.
  5. An item whose text or sub-bullets differ is allowed only if a sub-bullet under it starts with `Owner decision (YYYY-MM-DD):`.
- **Exit status:** 0 when clean; 1 with a list of violations otherwise.
- **Tests:** unit tests use temporary git repositories and synthetic TODO files to cover each check, including an allowed owner-decision change. These tests must not depend on this repository's real history.

The checker must pass before any commit that changes a checkbox, and as part of the final check (R2-50).

### R2-03 Restore all reworded SB items

Restore the original `5f245be` text of every SB item that still differs. The current list, produced by comparing item text against `5f245be`, is:

| Item | Original requirement text to restore |
|---|---|
| SB-001 | Owner creates a new repository and supplies its URL to the implementer. **[OWNER BLOCKER]** |
| SB-028 | Test multi-turn continuity, server restart, cross-principal denial, unknown IDs, concurrency, retention operations, and long-history trimming. |
| SB-035 | Add security tests for unauthenticated calls to both tools, forged client identity, cross-client IDs, malicious input text, unapproved model selection, oversized payloads, and accidental secret logging. |
| SB-050 | Verify the four exact Qwen3.5 9B model tags via live `list_models` backed by `/api/tags`, and check loaded status from `/api/ps`; update private runtime config with real names. |
| SB-051 | Run actual Ollama conversation with `32k` profile. Record latency, Ollama-reported token counts, and effective model name. |
| SB-052 | Configure Codex to use local HTTP MCP; confirm both-tool discovery, `list_models` results, first question, follow-up using returned ID, and persistence across restart. |
| SB-053 | Configure Claude Code to use local HTTP MCP; confirm the same discovery, model-listing, and conversation checks. |
| SB-054 | Register/connect the authorized remote endpoint in the owner's actual ChatGPT environment and verify live `list_models` and `ask_second_brain` calls, then a conversation continuation. **[EXTERNAL ACCESS MAY BLOCK]** |
| SB-055 | If ChatGPT cannot connect because of account/workspace permission, connector transport, or auth policy, document the exact issue and evidence; do not mark ChatGPT validated or invent a workaround. |
| SB-056 | Run a cross-client isolation test with distinct principals and intentionally presented foreign conversation IDs. |
| SB-057 | Perform targeted smoke tests for `4k`, `128k`, and `256k` profiles; measure speed and `ollama ps` context/GPU-offload behavior without assuming all work remains entirely on GPU. |
| SB-058 | Verify independent critique workflow: ask for an original solution *without* the host's answer; then follow up in the same conversation to challenge its reasoning. |
| SB-061 | Review data privacy: secure file permissions, backup/restore, no prompt/secret logging, explicit persistence documentation, and deletion behavior. |
| SB-062 | Provide systemd unit and direct Ubuntu setup; demonstrate startup/restart/shutdown without Docker/Podman. |

For each item, move the current status or evidence text into an `Evidence:` or `Note:` sub-bullet (for example, SB-054's blocker becomes `Note: Blocked — no remote endpoint or ChatGPT workspace access.`). Then re-evaluate the checkbox against the restored text. A checkbox may stay checked only if every clause is met and the evidence is recorded. In particular:

- **SB-028** and **SB-035** may be checked only if the evidence note names the tests covering each listed clause.
- **SB-062** stays unchecked: startup, restart, and shutdown have not been demonstrated.
- **SB-001** may stay checked: the owner supplied the repository.

The R2-02 checker must report zero violations for `docs/TODO.md` afterwards.

### R2-04 Restore deleted remediation acceptance lines

Restore these `ca3a444` acceptance lines in `docs/REMEDIATION_TODO.md`, keeping the current evidence as `Evidence:` sub-bullets:

| Task | Acceptance line to restore |
|---|---|
| RM-019 | `- Test: injected \`sqlite3.OperationalError\` and \`AttributeError\` produce exactly the \`internal_error\` text in the MCP response; the original message is absent from the response.` |
| RM-051 | `- Acceptance: a checklist mapping each R-51 item to a test name is added as a note under this task.` |
| RM-052 | `- Acceptance: plain \`uv run pytest\` reports them as skipped; \`SECOND_BRAIN_LIVE=1 uv run pytest -m live\` passes on this workstation; record the date, command, and summary in the verification record.` |

Uncheck **RM-019** until R2-10 makes the exact-text check pass. Uncheck **RM-010** and **RM-060** for the same reason, because both promise the exact `<code>: <message>` format. Re-check all three when RM2 tasks complete them.

### R2-05 Truthful gate and status claims

- **Gate R1** in `docs/REMEDIATION_TODO.md` requires regression tests "that failed before the fix". Produce that evidence where it is possible (R2-06). Add a `Note:` under Gate R1 that lists, for each of the twelve round-1 bugs, either "failed at `ca3a444`" with the test name, or "not runnable at `ca3a444`" with the reason (for example, the test depends on an API that did not exist yet).
- A TODO file's **Status** line must not say "Complete", "passed", or equivalent while any item in it is unchecked, partial, or relies on unrepeated manual evidence, unless the line names those exceptions. Update the status lines of `docs/TODO.md` and `docs/REMEDIATION_TODO.md` to match reality.
- `docs/RELEASE_NOTES.md` must not claim any guarantee contradicted by an open item (for example, "sanitized error categories" must describe the delivered format exactly).

### R2-06 Fail-first evidence for this round

Every bug fix in this round (R2-10 through R2-17) must come with a regression test that is **shown to fail on `ad85cdb`** before the fix. Procedure:

1. Write the test against the current code.
2. Run it and confirm it fails for the expected reason.
3. Record the command and a one-line failure summary as an `Evidence:` sub-bullet under the task.
4. Apply the fix and confirm the test passes.

Committing the failing test separately (marked `xfail(strict=True)`, with the marker removed in the fix commit) is acceptable and preferred.

For round-1 bugs (R2-05), use a temporary git worktree at `ca3a444`. Copy in the specific regression test files, run them, and record the outcomes. Do not modify `ca3a444`.

## 3. Error contract

### R2-10 Exact `<code>: <message>` for every tool error

Clients must receive tool errors as a `CallToolResult` with `isError: true` and a single text content item whose text is **exactly** `<code>: <message>`. There must be no SDK prefix such as `Error executing tool …:`, and no other text.

**Mechanism.** Subclass `FastMCP` (for example, `SecondBrainMCP`) and override `call_tool(name, arguments)`:

1. Call `super().call_tool(name, arguments)` and return its result unchanged on success.
2. On `ToolError`, inspect `__cause__`:
   - `SecondBrainError` → return `CallToolResult(isError=True, content=[TextContent(type="text", text=str(cause))])`.
   - `pydantic.ValidationError` raised while validating **arguments** (its title ends with `Arguments`) → return `invalid_input: invalid value for <field>[, <field>…]`, using the `loc` field names only. Never include input values.
   - Unknown tool name (no cause, SDK "Unknown tool" message) → `invalid_input: unknown tool`.
   - Anything else → `internal_error: the server could not complete the request`, after logging the exception type at ERROR (see R2-21).
3. Never catch `asyncio.CancelledError` or the SDK's `UrlElicitationRequiredError`.

This works with `mcp` 1.30 because FastMCP registers `self.call_tool` with the low-level server, and the low-level server passes a returned `CallToolResult` through without adding a prefix or validating output (`mcp/server/lowlevel/server.py`, the `isinstance(results, types.CallToolResult)` branch). The implementation must pin this behavior with tests (R2-10 acceptance), so an SDK upgrade that changes it fails CI instead of silently regressing.

**Handler changes.**

- Move `AskResponse.model_validate(...)` and `ModelInventory.model_validate(...)` inside each handler's `try`, so a response-validation failure becomes `internal_error`.
- Keep the existing catch-all that converts unexpected exceptions to `SecondBrainError("internal_error")`.

**Acceptance (all through a real MCP `tools/call` over the ASGI app):**

- Empty question gives exactly `invalid_input: question must not be empty`.
- `mode="nope"` gives exactly `invalid_input: invalid value for mode`, and `nope` does not appear in the response.
- Injected `sqlite3.OperationalError("secret-marker")` and `AttributeError("secret-marker")` in the service give exactly `internal_error: the server could not complete the request`, and `secret-marker` does not appear.
- A response-validation failure (a service result with a wrong field type) gives exactly the `internal_error` text.
- An unknown tool name gives exactly `invalid_input: unknown tool`.
- `list_models` with an Ollama outage gives exactly `ollama_unavailable: Ollama is unavailable or rejected the request`.
- Each case has `isError: true`, and the response has no `structuredContent`.

### R2-11 Documentation of the delivered format

After R2-10, `SPEC.md` §4.1, `docs/operations.md`, `README.md`, and `docs/RELEASE_NOTES.md` must describe the format exactly as delivered. `docs/operations.md` must list all eleven codes (it currently omits `conversation_unavailable` and `unauthorized`), with one line each saying when the code occurs.

## 4. Conversation behavior

### R2-12 Contiguous history trimming

When building the prompt, walk complete pairs from newest to oldest and **stop at the first pair that does not fit**. Older pairs are never included once a newer pair has been omitted. This restores `SPEC.md` §6.3 ("include only the newest history that fits") and `REMEDIATION_SPEC.md` R-32. `history_trimmed` is `true` whenever any stored pair is left out.

**Acceptance:**

- With pairs of uneven size (small oldest, large middle, small newest) and a budget that fits only the small ones, the prompt contains only the newest pair, and `history_trimmed` is `true`.
- A test fixes the exact message order for a history that fits fully.

### R2-13 Budget label in `context_too_large`

The `context_too_large` message names the selection correctly: `the <profile> prompt budget` for a profile selection, or `the <N>-token prompt budget` for a direct model. It must not derive a "k" label from integer division.

**Acceptance:** a direct model with a 6000-token budget produces `the 6000-token prompt budget`; the `4k` profile produces `the 4k prompt budget`.

### R2-14 Lock cleanup after cancellation

Extend the lock-registry test: after 50 sequential asks **and** one ask cancelled while waiting in Ollama, `service._conversation_locks` is empty. Add a second case where two asks wait on the same conversation lock and the waiting one is cancelled; the registry must be empty after the other completes.

## 5. Configuration

### R2-15 Profile tag sharing and placeholder detection

- **Remove** the validator rule that rejects one model tag mapped by two profiles with different budgets (`config.py`, "conflicting profile budgets"). Several profiles may map to the same tag; each request sends its own `num_ctx`.
- **Change** the allowed-model consistency rule (REMEDIATION_SPEC R-35): a tag in `allowed_models` that is also mapped by one or more profiles must have a `context_tokens` equal to **one of** those profiles' budgets. Otherwise, reject with the existing message.
- **Add placeholder detection.** Reject any profile or allowed-model tag equal to `SET_FROM_OLLAMA_LIST` or starting with `REPLACE_WITH_`, with the message `model tag placeholders must be replaced with exact names from \`ollama list\``.
- `list_models` keeps reporting `configured_context_limit_tokens` as the largest profile budget for a tag. The tag's `profiles` list names every profile that maps it.

**Acceptance:**

- `config.example.yaml` fails `load_config` with exactly the placeholder message, and with no "conflicting" message.
- A copy of the example with placeholders replaced by one shared tag for all four profiles loads successfully.
- A copy with four distinct tags loads successfully.
- An allowed model sharing a profile tag loads with a matching budget and fails with a non-matching one.

### R2-16 Single estimator and named minimum input

- Move `MESSAGE_OVERHEAD_TOKENS`, `PROMPT_OVERHEAD_TOKENS`, a new `MIN_INPUT_TOKENS = 256`, and the estimator function into one module (for example, `second_brain_mcp/budget.py`) with no imports from `config`, `service`, or `ollama`.
- `service.py`, `ollama.py` (the `estimate_exceeded` warning), and `config.py` (budget validation) all use it. No other module may repeat the literals `8`, `16`, or `256` for this purpose.
- **Config validation** requires `context_tokens - completion_tokens >= estimate([longest system prompt]) + MESSAGE_OVERHEAD_TOKENS + MIN_INPUT_TOKENS`, so the minimum covers the system prompt with its framing plus one input message.
- `docs/operations.md`'s usable-input table is regenerated from the estimator. Add a unit test that recomputes the table values and compares them with the documented numbers.

### R2-17 `check-config` reports validation errors

Every `second-brain` command, `check-config` in particular, must print the validation error message to stderr and exit with status 1 for an invalid configuration or missing credentials, without a traceback. Today `load_config` and `credentials()` raise `ValueError` out of `main()` (`cli.py:44-46`).

**Acceptance:** a parametrized CLI test runs `check-config` against one invalid config per R-35 rule, plus the placeholder rule. Each case exits with status 1, stderr contains the expected message, and stderr has no `Traceback`.

## 6. Credentials and deployment

### R2-18 Robust credential rotation

`scripts/init_credentials.py --rotate [--service-file PATH]` must:

1. **Back up atomically.** Write each target's previous contents to a temporary `0600` file in the same directory, then `os.replace` it onto `<file>.bak`, so a later rotation replaces the old backup instead of failing.
2. **Preserve other lines.** Parse each target as an env file. Replace only the `CODEX_MCP_TOKEN` and `CLAUDE_CODE_MCP_TOKEN` assignments (add them if missing) and keep every other line, including comments and other principals' tokens, in its original order.
3. **Stage, then commit.** Generate new tokens once. Write all target temporary files (with the target's mode and, when root, its owner) before replacing any target. If replacing a later target fails, restore every already-replaced target from its backup and exit with status 1 and a message naming the failed path.
4. **Use the same new tokens in both files**, so the user and service files stay consistent.
5. **Fail cleanly.** Exit with status 1 and a one-line message for a missing target or a permission error, without a traceback.

**Acceptance:**

- Three consecutive rotations succeed, each `.bak` holds the immediately previous tokens, and modes are preserved (`0600` user, `0640` service, `0600` backups).
- An extra line `CHATGPT_MCP_TOKEN=…` and a comment survive rotation unchanged.
- A service-file target in an unwritable directory leaves the user file **unchanged** (restored), and the script exits 1.

### R2-19 Header helper accepts configured principals

`deploy/auth_headers.py` accepts any principal name matching `[a-z][a-z0-9-]{0,31}`.

- For `codex` and `claude-code`, `--env-var` stays optional (default map).
- For any other name, `--env-var` is required; without it, exit 2 with `--env-var is required for principal <name>`.

**Acceptance:** `auth_headers.py chatgpt --env-var CHATGPT_MCP_TOKEN` prints the header from a test credential file; `auth_headers.py chatgpt` exits 2; an invalid principal name exits 2.

### R2-20 Reverse-proxy example strips client credentials

`deploy/reverse-proxy.example` must include `proxy_set_header Authorization "";` in the `/mcp` location, so client-supplied credentials never reach the application through this sketch. Keep the non-functional banner, and add one comment line explaining why `Authorization` is cleared.

**Acceptance:** a test reads the example and asserts that the `location = /mcp` block contains `proxy_set_header Authorization "";`, contains `proxy_set_header Host $host;`, and does not contain `proxy_set_header Host 127.0.0.1`.

## 7. Code hygiene and logging

### R2-21 Log level by error category

Tool error log lines use these levels:

| Level | Codes |
|---|---|
| INFO | `invalid_input`, `conversation_unavailable`, `model_not_approved`, `context_too_large` |
| WARNING | `busy`, `model_not_installed`, `ollama_unavailable`, `ollama_timeout`, `ollama_bad_response` |
| ERROR | `unauthorized`, `internal_error` |

The mapping lives in `errors.py` next to `ERROR_MESSAGES`, and both tool handlers and the R2-10 `call_tool` override use it.

**Acceptance:** a `caplog` test checks one code from each row is logged at the mapped level.

### R2-22 Remove dead store methods

Delete `ConversationStore.create`, `ConversationStore.add_turn`, and `ConversationStore.update_selection`. Rewrite tests and fixtures that used them to call `record_turn(..., new_conversation=True)` or a small test helper in `tests/conftest.py`.

**Acceptance:** none of the three names appears anywhere under `src/` or `tests/`.

### R2-23 Access-log leakage test

Add an integration test that starts the real server with `uvicorn` in a subprocess (on an ephemeral loopback port, with `ollama_base_url` pointing at an unused loopback port so Ollama calls fail fast) and captures its stdout and stderr. The test sends:

- an unauthenticated request,
- an invalid-token request with a marker token,
- a valid request whose question and context contain markers,
- a request with a marker in a query string.

It then asserts that none of the question, context, or token markers appear in the captured output. The test runs under plain `uv run pytest`, needs no real Ollama, and finishes within 30 seconds.

## 8. Tests and verification

### R2-30 Strengthened existing tests

- **Trimming:** add the uneven-size case from R2-12 to `test_trimming_keeps_newest_complete_pairs_and_reports_fit_status`, or as a new test.
- **Error text:** replace `endswith(...)` and suffix checks in the server and live tests with exact-equality checks once R2-10 lands, including `tests/live/test_live_server.py`'s `invalid_input` check.
- **Lock cleanup:** add the R2-14 cases.

### R2-50 Final verification

All of the following pass on the final commit, with results recorded in `docs/REMEDIATION_2_TODO.md`'s verification record:

- `uv sync --locked`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest -q`
- `uv run python scripts/check_todo_integrity.py`
- A fresh clone of the final commit into an empty directory passes the same checks.
- Opt-in, on this workstation: `SECOND_BRAIN_LIVE=1 uv run pytest -m live -q`.
- Manual: an MCP Inspector CLI check that the empty-question error text is exactly `invalid_input: question must not be empty`.

## 9. Required changes to other documents

| Document | Change |
|---|---|
| `SPEC.md` §4.1 | State that the error text is exactly `<code>: <message>` with `isError: true`, and that argument validation failures use `invalid_input` without echoing values (R2-10). |
| `SPEC.md` §6.3 | No wording change; behavior is restored to match (R2-12). |
| `REMEDIATION_SPEC.md` R-35 | Amend the allowed-model rule to "must equal one of the profile budgets for that tag", and add a note that profiles may share a tag (R2-15). Record this as an owner-approved change with the date. |
| `docs/TODO.md` | Working rule from R2-01; restored SB text (R2-03); truthful status line (R2-05). |
| `docs/REMEDIATION_TODO.md` | Working rule from R2-01; restored acceptance lines and unchecked items (R2-04); Gate R1 note and status line (R2-05). |
| `docs/operations.md`, `README.md`, `docs/RELEASE_NOTES.md` | Error format and full code list (R2-11); regenerated input-size table (R2-16); rotation behavior (R2-18); helper usage for other principals (R2-19). |

## 10. Traceability: review findings to requirements

| Finding from the second review | Requirements |
|---|---|
| RM-019 acceptance check deleted; RM-051/RM-052 acceptance lines replaced | R2-01, R2-02, R2-04 |
| Gate R1 "failed before the fix" claimed but not verified; status says all phases passed | R2-05, R2-06 |
| SB-028/SB-035 text contradicts checkbox; 14 SB items still reworded | R2-02, R2-03 |
| Bug 1: nginx example forwards `Authorization` | R2-20 |
| Bug 2: second rotation crashes; partial rotation leaves files mismatched; other lines dropped | R2-18 |
| Bug 3: non-contiguous history trimming; trimming test too weak | R2-12, R2-30 |
| Bug 4: same-tag-in-two-profiles rule breaks example config with misleading message | R2-15 |
| Bug 5: SDK prefix on errors; codeless argument-validation errors; SPEC §4.1 untrue | R2-10, R2-11 |
| Bug 6: helper rejects new principals despite `--env-var` | R2-19 |
| Bug 7: response validation outside the catch-all | R2-10 |
| Bug 8: "k" label from integer division in `context_too_large` | R2-13 |
| Estimator duplicated with magic numbers; budget check ignores framing; literal 256 | R2-16 |
| Dead store methods (`create`, `add_turn`, `update_selection`) | R2-22 |
| Caller mistakes logged at ERROR | R2-21 |
| `docs/operations.md` omits two error codes | R2-11 |
| `check-config` reporting untested (and it raises a traceback) | R2-17 |
| Access logs not covered by the leakage test | R2-23 |
| RM-021 cancelled-ask clause untested | R2-14 |
| RM-052/RM-053 live checks not repeatable by the reviewer | R2-50 |
| My own omission: round-1 R-03 table missed SB-001, SB-028, SB-035, SB-050–SB-058, SB-061, SB-062 | R2-02, R2-03 |
