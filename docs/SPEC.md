# Second Brain MCP — Technical Specification

**Status:** Proposed, ready for implementation  
**Version:** 0.1 (MVP specification)  
**Date:** 2026-10-25  
**Repository:** To be created by the project owner  
**Implementation language:** Python 3.12+ (managed with `uv`)

## 1. Purpose

Build a small, private **Model Context Protocol (MCP) server** that lets ChatGPT, Codex, and Claude Code consult an independent Ollama-powered chatbot as a *second brain*. The primary assistant remains responsible for all actions, files, coding, tool calls, and decisions. The second brain accepts a question and optional text context, reasons about it, and returns an answer. **The Ollama model has no tools.**

Examples:

- Ask for an independent architectural opinion before adopting a design.
- Challenge a proposed solution or identify missing assumptions.
- Brainstorm alternatives to a coding or product decision.
- Resume an earlier discussion with the same second brain.
- Compare the primary assistant's reasoning with an independently elicited response.

The first release optimizes for simplicity, private operation, predictable tool behavior, and realistic verification against all three MCP clients. It is **not** a general autonomous agent or a multi-agent orchestration platform.

## 2. Decisions and scope

### 2.1 Firm decisions

1. Use the user's **existing Ollama installation**, NVIDIA GPU (16 GB VRAM), and installed Qwen3.5 9B model variants; do not provision or fine-tune a new model.
2. Support four **configured model profiles**: `4k`, `32k`, `128k`, `256k`. The server's default is `32k`; actual Ollama model tags are configurable and discovered during setup, **not guessed**.
3. Expose **two MCP tools**: `ask_second_brain` for conversation and `list_models` for read-only model discovery.
4. Keep Ollama entirely **tool-free**: do not send tool definitions to `/api/chat`, do not run model-suggested commands, and do not add file, repository, web, shell, or nested-MCP access.
5. Use **one shared application** and a **Streamable HTTP MCP endpoint**; local clients access the loopback endpoint, while the remote ChatGPT integration accesses a secured HTTPS endpoint or supported private tunnel.
6. Separate histories by **authenticated client principal** (ChatGPT, Codex, Claude Code), plus opaque conversation ID. No shared cross-assistant memories in v1.
7. Persist per-conversation messages in **SQLite** so calls can continue after an MCP restart.
8. The primary assistant decides when to consult the second brain. No autonomous AI-to-AI exchanges, polling, recursive consultations, or tools that call back into the primary assistant.
9. The project is **local-first**, uses open-source packages, and must run directly on Ubuntu without Docker or Podman.
10. Verify current ChatGPT connector requirements rather than assume a particular authorization flow or plan support.

### 2.2 In scope for v0.1

- Request-response chat with five behavior modes.
- Discovery of installed Ollama models and their loaded status, plus selection from four existing model profiles or configured approved models.
- Isolated and resumable conversations stored on disk.
- Configurable prompt, context, output, and concurrency limits.
- Secure local access and authenticated remote access.
- Tests, logging, install/run documentation, and client integration instructions.
- Administrative **local CLI** for viewing and deleting stored conversations.

### 2.3 Out of scope for v0.1

- Global or automatically shared knowledge across assistants.
- Semantic/vector search, RAG, embeddings, knowledge graphs, and autonomous memory synthesis.
- File uploads, repository inspection, web browsing, shell execution, and tool calling by Ollama.
- Autonomous debates, scheduled background thought, or follow-up callbacks into host assistants.
- Multi-user SaaS, billing, public anonymous access, model training or fine-tuning.
- A graphical interface, model downloader, or model manager.

## 3. High-level architecture

```text
   ChatGPT (remote)             Codex + Claude Code (local)
          |                                  |
    HTTPS / private tunnel                loopback HTTP
          |                                  |
          +----------------+-----------------+
                           |
                    MCP server (/mcp)
                  tools: ask_second_brain, list_models
                           |
              authenticate / principal mapping
                           |
               conversation and prompt service
                    |                |
                SQLite          Ollama HTTP API
             (per-client)       (/api/chat)
                                        |
                             Qwen3.5 9B model profile
                                  (NO TOOLS)
```

**MCP transport state is not conversation state.** A returned `conversation_id`, rather than an MCP session identifier, identifies a persisted discussion across process restarts and reconnects.

### 3.1 Components

- **MCP layer:** MCP Python SDK (FastMCP or supported equivalent) via Streamable HTTP; input validation, stable tool schema, structured output when client-compatible.
- **Application layer:** principal-based routing, behavior-mode prompt construction, token/context budgeting, request handling, cancellation and errors.
- **Ollama adapter:** HTTP client (`httpx`) to the existing local Ollama service, typically `http://127.0.0.1:11434`; `/api/chat` for inference, read-only `/api/tags` for installed models and `/api/ps` for loaded-model status. No management endpoints.
- **Conversation store:** SQLite using the standard library initially; WAL mode, schema migrations, backups, retention/erase commands.
- **Deployment layer:** loopback-only server behind a trusted HTTPS reverse proxy, supported MCP tunnel, or equivalent protected ingress. Direct unauthenticated Ollama exposure is prohibited.

Recommended dependencies: Python 3.12+, `uv`, maintained MCP Python SDK, `httpx`, `pydantic` (if not already pulled in by the SDK), `uvicorn`/ASGI support, `pytest`, `pytest-asyncio`, and `ruff`. Prefer the standard `sqlite3` package over a database server for v1. Pin compatible versions in `uv.lock`.

## 4. MCP interface

### 4.1 `ask_second_brain`

**Description:** Ask an independent, tool-free Ollama chatbot for an opinion, critique, solution, or follow-up within an isolated conversation.

**Input** (JSON object):

| Field | Type | Required | Semantics |
|---|---|---|---|
| `question` | string | Yes | Current question or message; nonempty after trimming. |
| `context` | string | No | Supplemental facts/code/excerpts explicitly selected by the caller; treated as untrusted task data. |
| `conversation_id` | string | No | Opaque ID returned by an earlier call. Omit to create a new conversation. |
| `mode` | enum | No | `discuss` (default), `brainstorm`, `critic`, `review`, `solve`. |
| `model_profile` | enum | No | `4k`, `32k` (default on new discussions), `128k`, `256k`. On continuation, use the conversation's existing selection unless explicitly changed. |
| `model` | string | No | Exact installed Ollama model tag, as returned by `list_models`; only selectable if configured in the server allowlist. Cannot be supplied together with `model_profile`. On continuation, an explicit model changes the conversation's selected model. |

The server—not the caller—determines the authenticated principal. **Do not accept `client_id`, `owner`, or namespace as a security authority from tool arguments.**

**Successful output** (structured fields, with a readable text fallback for clients without structured results):

```json
{
  "answer": "A concise independent response...",
  "conversation_id": "<opaque random identifier>",
  "mode": "critic",
  "model_profile": "32k",
  "model": "<actual configured Ollama model tag>",
  "context_limit_tokens": 32768,
  "history_trimmed": false,
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 256,
    "elapsed_ms": 1750
  }
}
```

`model_profile` is `null` when an explicit approved model is used without a named profile; `context_limit_tokens` is the server-enforced effective budget for that selection, not a claim about intrinsic model capability. `usage` fields can be `null` where the Ollama backend does not report them. Do not fabricate usage. Return only the current answer and metadata, **not** the entire saved conversation. Exclude hidden reasoning traces from tool output and persisted conversation text unless explicitly enabled by a future design review.

**Failure behavior:** a failed call returns an MCP tool result with `isError: true` and a single text item whose text is exactly `<code>: <message>`, with no SDK prefix or other text. This covers invalid input, inaccessible conversation, unauthorized client, unknown configured profile, context exceeding limits, Ollama unavailable, model unavailable, and timeout. Argument-validation failures (for example, a `mode` outside the published enum) return `invalid_input: invalid value for <field>` and never echo the supplied value; an unknown tool name returns `invalid_input: unknown tool`. Codes include `invalid_input`, `conversation_unavailable`, `model_not_approved`, `model_not_installed`, `context_too_large`, `busy`, `ollama_unavailable`, `ollama_timeout`, `ollama_bad_response`, `unauthorized`, and `internal_error`. Messages are fixed and sanitized; never include bearer tokens, raw private prompts, internal stack traces, or raw SQLite rows in client-visible errors.

### 4.2 `list_models`

**Description:** Discover the Ollama models currently installed on this server, determine which are permitted for `ask_second_brain`, and inspect which are presently loaded. The tool is **read-only** and does not load, pull, delete, run, or modify any models.

**Input:** None (an empty JSON object). Every call requires the same authenticated MCP principal as `ask_second_brain`.

**Backend:** Fetch `GET /api/tags` for the installed model inventory and `GET /api/ps` for currently loaded models. Correlate by exact model tag and annotate with server-side configuration. Do not infer a model's maximum context window solely from its name or `/api/tags`. The running `context_length` value reflects a loaded model's current allocation, not a guarantee about the model's native capabilities. Handle an empty inventory and Ollama unavailability clearly.

Return at most `MAX_LISTED_MODELS = 200` entries and include `truncated: boolean`. When the inventory is truncated, keep all configured and approved model tags in the result.

**Example output** (illustrative names and numbers, not claims about actual installed models):

```json
{
  "models": [
    {
      "name": "EXAMPLE_QWEN9B_32K_TAG",
      "parameter_size": "9B",
      "quantization": "Q4_K_M",
      "installed_size_bytes": 5900000000,
      "loaded": true,
      "loaded_context_tokens": 32768,
      "loaded_vram_bytes": 6200000000,
      "selectable": true,
      "profiles": ["32k"],
      "configured_context_limit_tokens": 32768
    }
  ],
  "default_profile": "32k"
}
```

Fields absent from Ollama's response should be returned as `null` rather than invented; unloaded models have `loaded: false` and `loaded_context_tokens: null`. `selectable` means the model's exact tag is present in the administrator-maintained allowlist, not merely installed. Return all locally installed model names only to authenticated callers, bounded to a documented maximum response size; do not expose local filesystem paths, model files, digests, tokens, or internal service URLs. No arguments grant elevated model-management rights.

If a tag is installed but `selectable: false`, an administrator must explicitly allow it before `ask_second_brain(model=...)` can invoke it. This avoids allowing a remote MCP caller to load arbitrary heavyweight or sensitive models.

### 4.3 Modes

| Mode | Behavior |
|---|---|
| `discuss` | Natural, informed dialogue; acknowledge uncertainty. |
| `brainstorm` | Offer meaningfully different approaches and tradeoffs. |
| `critic` | Identify flawed assumptions, failure modes, and counterarguments without contrarianism for its own sake. |
| `review` | Independently evaluate the provided design, proposed answer, or excerpt against explicit criteria. |
| `solve` | Try to solve the problem from supplied facts without assuming the primary assistant's proposed solution. |

Use concise, versioned system prompts in source-controlled files or constants. Prompt for calibrated, independent reasoning and respectful disagreement; never portray the chatbot as a domain authority or imply access to information not provided. In independent-review use cases, **the caller must withhold its own proposed answer** unless evaluating that answer is the task.

### 4.4 MCP metadata

- Advertise exactly **two v0.1 tools** with deterministic schemas: `ask_second_brain` and `list_models`.
- Set annotations truthfully: `ask_second_brain` can **persist local conversation state** and is not side-effect-free; `list_models` is read-only and does not change loaded models.
- Do not add MCP resources or prompts until a concrete client requirement justifies them.
- Prefer bounded, non-streaming tool replies initially (`stream: false` to Ollama); add end-to-end streaming only if a measured usability problem warrants it.

## 5. Ollama integration and model profiles

The user already has Qwen3.5 9B variants configured with effective contexts of 4K, 32K, 128K and 256K tokens. Define mappings in configuration:

```yaml
ollama:
  base_url: "http://127.0.0.1:11434"
  default_profile: "32k"
  profiles:
    "4k":   { model: "REPLACE_WITH_INSTALLED_MODEL_TAG_4K",   context_tokens: 4096 }
    "32k":  { model: "REPLACE_WITH_INSTALLED_MODEL_TAG_32K",  context_tokens: 32768 }
    "128k": { model: "REPLACE_WITH_INSTALLED_MODEL_TAG_128K", context_tokens: 131072 }
    "256k": { model: "REPLACE_WITH_INSTALLED_MODEL_TAG_256K", context_tokens: 262144 }
  # Optional additional approved models selectable by their exact Ollama tag.
  # Provide a conservative explicit context budget for each.
  allowed_models: {}
```

These model tags are **placeholders**, not actual installed names. Startup and `list_models` use `GET /api/tags` to discover installed tags, with optional `GET /api/ps` to report runtime status; configured tags absent from the inventory must fail with a useful explanation when selected. An approved model is one referenced by a configured profile or explicitly listed in `allowed_models` with an administrator-set context budget. `ask_second_brain(model=...)` accepts exact approved tags only, never an arbitrary user-supplied installed name. Supplying both `model_profile` and `model` is invalid; when both are omitted on a new discussion, default to `32k`. On every continuation, resolve a stored profile through the current profile mapping and require a stored direct model to remain approved with its current budget. An optional per-profile or per-model `completion_tokens` reserve overrides the global reserve. Respect existing per-model Ollama configuration; set `options.num_ctx` only where necessary, consistent with the selected profile, and verify the effective allocation. A configured context size is an **upper bound**, not evidence that answer quality or inference speed remains constant at that length.

Chat requests use `POST /api/chat` with `model`, `messages`, `stream: false`, and supported options/keep-alive. **Do not include a `tools` field**. For `list_models`, make only read-only inventory/status calls. Do not expose arbitrary Ollama endpoints or accept unapproved arbitrary model names.

- `32k` is the normal default; use `4k` for short consultations.
- `128k` and `256k` are explicit choices for large supplied contexts; benchmark their latency, memory footprint, and offloading behavior.
- An optional directly selected model uses its approved explicit context budget and does not inherit a misleading Qwen-specific profile name. Validate its installed/allowed status on invocation.
- Set a configurable output-token reservation (for example 2,048–4,096 tokens for the 32K profile), with a minimum safety margin for system instructions and message framing.
- Bound Ollama concurrency (default 1 inference at a time) and queue time. A single GPU may be saturated by concurrent long-context requests.
- Configure request, connect, and inference timeouts separately. Surface timeouts without blocking indefinitely.

## 6. Conversation persistence and context management

### 6.1 Persistence model

Store each discussion in SQLite, keyed by an unpredictable, server-generated identifier and an **authenticated principal**:

```text
conversations(
    id TEXT PRIMARY KEY,
    principal TEXT NOT NULL,
    model_profile TEXT,              -- null for direct model selection
    model_tag TEXT NOT NULL,         -- persisted exact selected Ollama model tag
    context_limit_tokens INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,              -- user | assistant
    content TEXT NOT NULL,
    context_text TEXT,                -- caller-supplied context for that turn
    mode TEXT,                        -- mode used for that turn
    created_at TEXT NOT NULL
)
```

The exact schema can evolve via numbered migrations. Enable foreign keys and appropriate indexes. Use SQLite WAL and a busy timeout; serialize writes within the same conversation. Store the exact model tag and its validated context budget with every conversation (and track changes when explicitly switched), so resumed discussions behave predictably. Insert a new conversation row and its first question/answer pair in one transaction; for continuations, verify ownership and commit selection changes, `updated_at`, and the successful question/answer pair together. Store only successful turns as complete question/answer pairs. Avoid duplicate partial messages after failed requests; optionally add idempotency keys in a future revision.

### 6.2 Ownership and isolation

- Different principals must never read, continue, enumerate, or delete each other's conversations.
- A conversation belongs to its original principal even if an ID leaks. The random ID is **not** authorization.
- Continuing a conversation returns the same ID; omitting it creates a new one.
- The database survives server restart; MCP transport reconnects have no effect on conversation history.
- Distinct assistants do **not** automatically share history, summaries, project metadata, or Ollama sessions.

### 6.3 Context budget policy

Construct each prompt from: mode-specific system instructions + explicitly included conversation history + the new question and optional context. Check a conservative token estimate **before** sending it to Ollama. Reserve room for the completion; enforce max request bytes and input sizes separately from token budgets.

For MVP, preserve the **complete chronological record on disk** while including only the newest history that fits the selected profile/model's configured active prompt budget. Do not silently truncate the **current question or supplied context**: reject an oversized current input with a useful error and suggested larger profile. If old history is omitted from the model prompt, set `history_trimmed: true` in the response. If a message cannot be represented safely with the available tokenizer/estimator, reject rather than risk runaway context usage.

**Deferred enhancement:** summarize older history into explicit, reviewable conversation summaries to preserve more continuity; introduce only after the basic history behavior is tested.

### 6.4 Administrative controls

Provide a **local administrator CLI**, not additional model-visible MCP tools:

```text
second-brain conversations list [--principal ...]
second-brain conversations show <conversation-id>
second-brain conversations get-any <conversation-id>
second-brain conversations delete <conversation-id>
second-brain conversations purge [--older-than <days>]
second-brain conversations export [<conversation-id>] [--principal P] [--output FILE]
```

Require confirmation for destructive delete and bulk purge unless `--yes` is supplied; EOF or non-interactive input means cancel. `purge` uses `retention_days` when `--older-than` is omitted. Retention is never applied automatically by the server, and the default is **no automatic retention purge**. Export JSON to stdout or create a new output file with mode `0600` and refuse to overwrite an existing path. Keep SQLite at a configured path with restrictive file permissions and support backups. Never store or print credentials in conversation rows or ordinary logs.

## 7. Connectivity and security

### 7.1 Local clients

Serve MCP on `127.0.0.1` only. Configure Codex and Claude Code to use the same local Streamable HTTP endpoint when on that host. Use **separate local bearer credentials/principals** for `codex` and `claude-code` so namespaces cannot be spoofed; secrets belong in environment variables or an OS-level secret store, not checked-in config. If the clients run on another machine, use an authenticated private tunnel or an approved protected network path—`localhost` on another machine is not the Ollama host.

A local `stdio` adapter may be added only if actual client compatibility requires it; it must reuse the same business logic and persistence instead of creating a second implementation.

### 7.2 Remote ChatGPT integration

Expose a stable MCP endpoint (typically `https://<private-host>/mcp`) through a trusted HTTPS reverse proxy or supported private MCP tunnel. Ollama and SQLite stay on the trusted host. The proxy must enforce appropriate Host/Origin policy, TLS, request size limits, and safe forwarded headers. `trusted_hosts` is an explicit list of bare DNS names accepted by both the server Host check and MCP transport security; it does not establish remote authentication.

**Do not assume that a static shared bearer token is sufficient for ChatGPT.** Evaluate the *actual* available connection flow and, where applicable, implement OAuth 2.1-compatible MCP protected-resource metadata, authorization-server integration, PKCE, correctly scoped/audience-bound tokens, and token verification. Reuse an existing trustworthy identity provider if it conforms to the current requirements. Do not write a custom OAuth provider solely to meet the MVP if an existing supported solution is available.

The local bearer middleware currently sets both a principal ContextVar and `scope["user"]` (`SimpleUser`). When SB-042 introduces verified remote identities, migrate principal propagation to the SDK `AuthenticatedUser` / `TokenVerifier` path.

ChatGPT custom MCP connectivity is a **product/workspace capability**, separate from server correctness. Verify the account/workspace can register this connection; a secure, working HTTP server alone cannot confer ChatGPT access. ChatGPT end-to-end verification is an acceptance gate and may be a documented external blocker, while local MVP development proceeds.

### 7.3 Security requirements

- No anonymous access to real tools or conversation records. Fail closed on authentication errors.
- Bind principal identity **only** from verified credentials, not `context`, `question`, headers blindly trusted from the internet, or client-supplied JSON arguments.
- Restrict model names to configured allowlists; sanitize paths, IDs, logs, and error messages.
- Limit request size, question/context length, context tokens, response tokens, concurrency, request rate, and queue depth.
- Treat text supplied to Ollama and text returned by Ollama as **untrusted**. Never execute embedded instructions or silently relay model-suggested tool calls to an agent runtime.
- Do not persist raw model thinking, request authorization headers, access tokens, full prompts in default telemetry, or secrets.
- Avoid exposing Ollama's own HTTP listener over the public interface.
- Test authentication bypass, cross-principal access, malformed JSON, oversized inputs, DNS-rebinding/Host/Origin issues, and model prompt injection.
- Keep data on the local Ollama host except for deliberately exchanged MCP requests and responses. Be explicit that a remote assistant may transmit selected prompts/context to this private server.

## 8. Reliability, telemetry, and operations

- Expose a minimal, non-sensitive local `/healthz` endpoint that checks server process health. Authenticated `list_models` covers safe inventory and loaded-status discovery; local diagnostics may additionally test connection health. Do not leak internal paths, model inventories, or secrets from public unauthenticated endpoints.
- Use structured logs with request correlation IDs, principal, model profile, elapsed time, token counts when available, and categorized error status. **Do not log message contents by default.**
- Run one server process because concurrency admission and per-conversation locks are in memory. Return a server-generated `X-Request-ID` response header on every HTTP response, including authentication and host-policy failures.
- Fail fast and clearly if Ollama is down, the chosen model is missing, the database cannot be opened, credentials are invalid, or the response exceeds operational limits.
- Handle cancellation and shutdown without leaving incomplete conversation turns.
- Provide a systemd unit and a non-root, direct-host deployment guide; Docker/Podman are not required or part of acceptance.
- Keep configuration in a documented sample file plus environment-backed secrets. Never commit real tokens, user conversations, or production DB files.
- Make tests self-contained with an Ollama mock; mark real-model and client integration tests as separate opt-in checks.

## 9. Suggested repository structure

```text
.
├── SPEC.md
├── TODO.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── config.example.yaml
├── src/second_brain_mcp/
│   ├── __init__.py
│   ├── server.py            # MCP transport and tool registration
│   ├── service.py           # ask orchestration and validation
│   ├── ollama.py            # HTTP adapter and model profiles
│   ├── prompts.py           # system prompts / modes
│   ├── store.py             # SQLite data access and migration
│   ├── auth.py              # verified principal mapping
│   ├── config.py            # configuration and env loading
│   └── cli.py               # local administration
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
└── deploy/
    ├── second-brain-mcp.service.example
    └── reverse-proxy.example
```

This is a starting structure, not an obligation to create unnecessary files. Keep the codebase small and consolidate modules where appropriate.

## 10. Verification and release acceptance

### 10.1 Mandatory automated checks

1. **MCP tool contracts:** exactly `ask_second_brain` and `list_models` are exposed; verify field validation, structured output, inventory/status accuracy, read-only behavior, and safe errors using MCP Inspector/client tests.
2. **No-tool guarantee:** tests assert Ollama requests contain no `tools` definitions and server exposes no filesystem/shell/web/agent capabilities.
3. **Model discovery and selection:** inventory comes from `/api/tags`, loaded status from `/api/ps`; each of `4k`, `32k`, `128k`, `256k` maps to the correct configured model, the default is `32k`, approved direct model selection works, unapproved names and conflicting selectors fail, and absent tags fail clearly.
4. **Modes:** all five modes yield the intended system-instruction variants without access to hidden primary-agent context.
5. **Persistence:** create, follow up, restart service, and follow up again using the original conversation ID with coherent history.
6. **Isolation:** requests with another principal's conversation ID fail without disclosing its existence or contents.
7. **Budget handling:** older stored turns can be omitted from inference with `history_trimmed=true`; current oversized input is rejected and no history is corrupted.
8. **Robustness:** concurrent calls, tool timeouts, Ollama outages, SQLite contention, malformed JSON, and cancellation are covered.
9. **Security:** unauthorized remote/local calls fail closed; credentials and conversation contents are not emitted to logs.

### 10.2 Real integration smoke tests

- **Ollama:** ask a normal question on the real `32k` Qwen3.5 9B profile; check `/api/chat` reply and actual configured model/tag.
- **Codex:** install MCP connection, discover both tools, invoke `list_models` and `ask_second_brain`, continue conversation with same ID.
- **Claude Code:** same discovery, model inventory, and continuation checks.
- **ChatGPT:** from the actual authorized ChatGPT account/workspace, register the remote/private MCP endpoint, discover both tools, invoke them, and resume a conversation. If account permission or connection policy prevents integration, record exact reproducible blocker—not a false pass.
- **Reconnection:** restart/reconnect MCP and verify persistence and absence of cross-client history leakage.
- **Long context:** smoke-test 128K and 256K configured profiles with measured VRAM allocation, processing time, response quality, and any CPU offloading; do not claim full GPU residency based only on configured `num_ctx`.

### 10.3 Definition of done for v0.1

A single maintained Python codebase serves both MCP tools; model inventory and loaded status are available read-only; the tool-free Ollama call works on the existing installation; modes, all configured profiles, and optionally approved direct models are selectable; persisted discussions survive restart; authenticated principals are isolated; Codex and Claude Code have passing live smoke tests; the remote endpoint is safely deployed; and ChatGPT has either a **passing real invocation test** or a clearly marked **external account/connector blocker**. All tests, security checks, docs, and administrator controls are complete.

The project should not be reported as **fully integrated with all three assistants** unless the ChatGPT test actually passes.

## 11. Future versions (not MVP commitments)

1. Rolling summarization of old discussions, with explicit summaries visible in administrative tools.
2. Opt-in shared project knowledge across principals, with access controls and provenance.
3. A semantic index for searching archived discussions, only if SQLite text search is insufficient.
4. Side-by-side model comparisons or consensus/debate workflows, explicitly initiated and bounded.
5. Real-time streaming where clients and proxies support it reliably.
6. Opt-in project-specific system prompts, evaluation benchmarks, and metrics dashboards.

## 12. Engineering references (checked 2026-10-25)

- MCP server construction and transport: <https://modelcontextprotocol.io/docs/develop/build-server>
- MCP Python SDK deployment/security: <https://py.sdk.modelcontextprotocol.io/run/deploy/>
- Ollama `/api/chat`: <https://docs.ollama.com/api/chat>
- Ollama installed models `/api/tags`: <https://docs.ollama.com/api/tags>
- Ollama running models `/api/ps`: <https://docs.ollama.com/api/ps>
- Ollama context settings and GPU checks: <https://docs.ollama.com/context-length>
- Claude Code MCP integration: <https://code.claude.com/docs/en/mcp>
- Codex MCP integration: <https://learn.chatgpt.com/docs/extend/mcp?surface=cli>
- ChatGPT custom MCP availability and setup: <https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt>
- OpenAI MCP authentication guidance: <https://developers.openai.com/plugins/build/auth>

**Implementation note:** MCP transport and client support are actively evolving. Confirm installed SDK versions, current client capabilities, and exact authentication requirements before selecting flags or committing deployment configuration.
