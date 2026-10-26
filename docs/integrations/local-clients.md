# Local client setup

The local server exposes Streamable HTTP at `http://127.0.0.1:8000/mcp` and uses independent tokens for `codex` and `claude-code`. Create the user credential file once with `uv run python scripts/init_credentials.py`; it writes `~/.config/second-brain/credentials.env` with mode `0600`. It refuses to overwrite an existing file. Start the server with `scripts/run_local.sh`. The helper reads the user credential file and emits only the requested bearer header as JSON; it never prints tokens to stderr or a log. For systemd, `/etc/second-brain/credentials.env` is a separate service credential file, read by systemd and normally owned by `root:second-brain` with mode `0640`. The helper does not read the service file.

## Codex

Add the server to user configuration with `codex mcp add second-brain --url http://127.0.0.1:8000/mcp`. In `~/.codex/config.toml`, add `http_headers_helper = "python3 /absolute/path/to/jcricket/deploy/auth_headers.py codex"` under `[mcp_servers.second-brain]`. Check `codex mcp list`; then start a fresh Codex session and verify `list_models`, a question, a continuation, and persistence across restart.

## Claude Code

Add the user-scoped server with `claude mcp add-json second-brain '{"type":"http","url":"http://127.0.0.1:8000/mcp","headersHelper":"python3 /absolute/path/to/jcricket/deploy/auth_headers.py claude-code"}' --scope user`. Verify `claude mcp get second-brain` and `/mcp`, then run the same tool and persistence checks in a fresh session.

Rotate local tokens with `uv run python scripts/init_credentials.py --rotate`. It replaces only the `CODEX_MCP_TOKEN` and `CLAUDE_CODE_MCP_TOKEN` lines, keeps every other line and comment, and saves the previous file as a private `.bak` (replaced on each rotation, so it always holds the immediately previous tokens). If systemd uses the service credential file, include `--service-file /etc/second-brain/credentials.env` (with suitable privileges) so both files get the same new tokens. Rotation is all-or-nothing: every file is staged before any is replaced, and if a later replacement fails, earlier files are restored and the command exits 1. Then restart the service and reconnect each client.

For a principal other than `codex` or `claude-code`, pass the environment variable name explicitly, for example `python3 deploy/auth_headers.py chatgpt --env-var CHATGPT_MCP_TOKEN`; the helper requires `--env-var` for any name outside its default map and accepts lowercase names matching `[a-z][a-z0-9-]{0,31}`. Project directories and committed configs must never contain real tokens. If a client reports an authorization failure, verify the helper path, principal name (`codex` or `claude-code`), credential file permissions, and that the service was restarted after rotation. Confirm available models with `list_models` before selecting a profile.

## ChatGPT (through an OpenAI Secure MCP Tunnel — documented, not yet verified live)

**Status.** Nothing in this section has been run end to end against a real ChatGPT workspace (SB-054 is still open). It is assembled from the `tunnel-client` 0.0.16 built-in help (`tunnel-client help quickstart`, `help samples`, `init --help`, `run --help`) and from the owner's working Ralph Bridge setup, which uses the same tunnel mechanism with a stdio server. Treat every step as a procedure to verify, and record results in `docs/TODO.md` (SB-046, SB-054).

### How it works

```text
ChatGPT custom app (connection type: Tunnel)
  -> OpenAI Secure MCP Tunnel            (tied to your ChatGPT workspace)
  -> tunnel-client on this machine        (connects OUTBOUND to OpenAI)
  -> http://127.0.0.1:8000/mcp            (this server, loopback only)
```

- **No public port, reverse proxy, or OAuth server is needed.** The server stays bound to loopback. `tunnel-client` makes only outbound connections to OpenAI.
- **ChatGPT never holds this server's token.** `tunnel-client` adds `Authorization: Bearer <token>` to each request it forwards (the profile's `mcp.extra_headers`). The token is a dedicated `chatgpt` principal, so ChatGPT conversations are isolated from Codex and Claude Code.
- **Why not a public URL.** Hosted ChatGPT cannot reach `127.0.0.1`. Vendor guides describe ChatGPT's own connector authentication as OAuth or none (they did not confirm bearer-token support), and the spec forbids running this server unauthenticated. The tunnel avoids both problems. Use the supported `tunnel-client` path rather than an ad hoc public tunnel such as ngrok; `deploy/reverse-proxy.example` remains a non-functional sketch.

### Prerequisites

1. This server running locally on current code (`scripts/run_local.sh`), with `uv run second-brain --config config.yaml check-config` passing.
2. `tunnel-client` on `PATH` (check with `tunnel-client --version`).
3. A ChatGPT plan and role that allow Developer mode and custom apps. The owner expects this workspace to allow tools that are not read-only, which `ask_second_brain` needs because it saves conversations. That is an expectation, not something this project has seen work: confirm it when you scan the tools (step 4), and expect ChatGPT to ask for confirmation on calls that are not read-only. OpenAI's own documentation page could not be read by this project.
4. Access to OpenAI Platform with permission to create tunnels and runtime API keys.

### 1. OpenAI Platform values

Keep these separate and out of the repository, shell history, screenshots, and chat messages.

| Value | Where it comes from | Notes |
|---|---|---|
| `CONTROL_PLANE_TUNNEL_ID` (`tunnel_…`) | <https://platform.openai.com/settings/organization/tunnels> | Not a secret, but operator-only. Must be associated with the ChatGPT workspace that will use the app. |
| `CONTROL_PLANE_API_KEY` | <https://platform.openai.com/settings/organization/api-keys> | A **restricted runtime key** with Tunnels Read and Use. Never use an admin key for the long-running process. |
| `OPENAI_ADMIN_KEY` | Admin keys page | Only for `tunnel-client admin …` management commands. Do not give it to the daemon. |

Use a **dedicated tunnel for this server**, separate from any other private MCP app (for example Ralph Bridge). Section "Several private MCP apps on one computer" below explains why and how to create it.

### 2. Add the `chatgpt` principal

1. In `config.yaml`, add a third entry to `token_env` (the `codex` and `claude-code` entries stay):

   ```yaml
   token_env:
     codex: CODEX_MCP_TOKEN
     claude-code: CLAUDE_CODE_MCP_TOKEN
     chatgpt: CHATGPT_MCP_TOKEN
   ```

2. Generate a token and append it to the private credentials file (mode `0600`):

   ```sh
   printf 'CHATGPT_MCP_TOKEN=%s\n' "$(openssl rand -hex 32)" >> ~/.config/second-brain/credentials.env
   ```

   `scripts/init_credentials.py --rotate` keeps unrelated lines, but it only rotates the Codex and Claude Code tokens; rotate `CHATGPT_MCP_TOKEN` by hand.
3. Restart the server so it reads the new variable, then run `check-config`.

Tested behavior (`tests/security/test_additional_principal.py`): each configured token maps to its own principal, an unconfigured token gets 401, and a `chatgpt` conversation is invisible to the other principals.

### 3. Create and check the tunnel profile

Put the secrets in a private environment file instead of typing them (see `deploy/tunnel.env.example`) and load it. The profile then refers to them by name, so the YAML contains no secret.

```sh
export CONTROL_PLANE_API_KEY=...                         # runtime key from step 1
export SECOND_BRAIN_UPSTREAM_AUTH="Bearer $CHATGPT_MCP_TOKEN"   # the whole header value

tunnel-client init --sample sample_mcp_remote_no_auth --profile second-brain \
  --tunnel-id tunnel_xxx \
  --mcp-server-url http://127.0.0.1:8000/mcp \
  --health-listen-addr 127.0.0.1:18081
```

`init` writes `~/.config/tunnel-client/second-brain.yaml` (mode `0600`). Add the upstream header to it with `tunnel-client profiles edit second-brain` (the command validates the file before saving), so that the `mcp:` block reads:

```yaml
mcp:
  extra_headers:
    Authorization: "env:SECOND_BRAIN_UPSTREAM_AUTH"
  server_urls:
    - channel: main
      url: "http://127.0.0.1:8000/mcp"
```

Then check and run it:

```sh
tunnel-client doctor --profile second-brain --explain
tunnel-client run --profile second-brain
```

- **The key is `mcp.extra_headers`, a map** from header name to value (checked 2026-10-26 with `tunnel-client` 0.0.16). Profile validation is strict. In a scratch directory, `tunnel-client profiles add --from-file` accepted the map form above, and it rejected a list of `"Name: value"` strings ("cannot unmarshal !!seq into map[string]string"), `mcp.headers`, `extra_headers` under a server URL, and an invented key. A typo therefore fails loudly when you save. That test did not contact OpenAI, so it shows the key is valid but not that the header reaches this server at runtime. `doctor --explain` and test row 1 below are the real checks.
- **Value format.** `env:NAME` and `file:/path` are the documented reference forms for header values (from `tunnel-client run --help`); the variable must contain the complete header value, `Bearer <token>`, not just the token.
- **Fallback.** Instead of editing the profile, you can export `MCP_EXTRA_HEADERS="Authorization: env:SECOND_BRAIN_UPSTREAM_AUTH"` before `tunnel-client run`. Use one form or the other, not both.
- `sample_mcp_remote_no_auth` is the sample for an HTTP MCP server that does not advertise OAuth metadata. This server answers `404` for `/.well-known/…` paths, which the sample treats as ready.
- Keep the health listener on loopback. `127.0.0.1:18081` avoids the default `8080`, and the Ralph Bridge launchers use `18080`.
- `tunnel-client run` must stay running while ChatGPT scans or calls the app. For a service, adapt `deploy/second-brain-tunnel.service.example`; keep `SECOND_BRAIN_UPSTREAM_AUTH` in its `0600` environment file.

### 4. Create the ChatGPT app

1. Enable **Developer mode** for the account or workspace. Depending on plan and role this is under **Settings → Apps → Advanced settings**, **Workspace settings → Apps → Create**, or **Workspace settings → Permissions & roles → Connected data**. The UI changes; the requirement is the relationship: app → tunnel → `tunnel-client` → this server.
2. **Settings → Apps → Create** (or the workspace equivalent). Name it, for example, `Second Brain`.
3. Choose **Tunnel** as the connection type and select the tunnel from step 1.
4. With `tunnel-client run` healthy, use **Scan Tools** / **Refresh Tools**.
5. Confirm exactly two tools, `ask_second_brain` and `list_models`, with the `mode` and `model_profile` enums, `ask_second_brain` marked as not read-only, and `list_models` marked read-only. Save the app.
6. Start a **new** conversation (an open conversation will not see a rescan) and select or mention the app.

### 5. Test

Run these in order in a new conversation, and record the outcome of each:

| # | Ask ChatGPT to… | Expect |
|---|---|---|
| 1 | Use the Second Brain app and call only `list_models`. | Your configured model tags and `default_profile: "32k"`. Proves the whole path and that the injected token was accepted. |
| 2 | Call `ask_second_brain` with a short question and `model_profile: "4k"` or `"32k"`. | An answer plus `conversation_id`, `model`, and `usage`. Approve the confirmation if shown. |
| 3 | Call it again with the returned `conversation_id` and a follow-up. | The follow-up uses earlier context. |
| 4 | Call it with an empty question. | Exactly `invalid_input: question must not be empty`. |
| 5 | (On this machine) `uv run second-brain --config config.yaml conversations list --principal chatgpt` | Your conversations appear under `chatgpt` and not under `codex` or `claude-code`. |
| 6 | Stop `tunnel-client`, then ask for `list_models` again. | The call fails cleanly; restarting the tunnel restores it. |

Logs show `principal=chatgpt` for these calls. Prompts, answers, and tokens are not logged.

### Several private MCP apps on one computer

Use **one tunnel, one profile, one `tunnel-client run` process, and one ChatGPT app per private MCP server.** For example, Ralph Bridge (stdio) and Second Brain (HTTP) on the same host:

| | Ralph Bridge | Second Brain | A third app |
|---|---|---|---|
| OpenAI tunnel | `tunnel_aaa…` | `tunnel_bbb…` | `tunnel_ccc…` |
| `tunnel-client` profile | `ralph-bridge` | `second-brain` | `…` |
| Upstream | stdio command | `http://127.0.0.1:8000/mcp` | its own port |
| Health listener | `127.0.0.1:18080` | `127.0.0.1:18081` | `127.0.0.1:18082` |
| Secrets file (mode `0600`) | its own | its own | its own |
| Service unit | `ralph-bridge-tunnel` | `second-brain-tunnel` | `…` |
| ChatGPT app (type Tunnel) | `Ralph Bridge` | `Second Brain` | `…` |

**Why separate tunnels.** Each app can be started, stopped, rescanned, and revoked on its own; a leaked or rotated key affects one app; and the mapping from ChatGPT app to local process is unambiguous. The profile format has a `channel:` field (`main` in every sample), which suggests one tunnel could carry several servers, but this project found no documentation of how a ChatGPT app selects a non-`main` channel, so it is not recommended.

**Create the additional tunnel.** Either way, associate it with the **same ChatGPT workspace** that will use the app.

- In the OpenAI Platform tunnels page (<https://platform.openai.com/settings/organization/tunnels>): create a tunnel, name it for the app (for example `second-brain`), give it a description, attach it to the workspace, and copy its `tunnel_…` ID.
- Or from the command line, with an **admin key** that you use only for this command and never put in a service environment:

  ```sh
  export OPENAI_ADMIN_KEY=...                     # admin key, this shell only
  tunnel-client admin tunnels create \
    --name "second-brain" \
    --description "Second Brain MCP (Ollama)" \
    --organization-id org_xxx \
    --workspace-id ws_xxx
  tunnel-client admin tunnels list --workspace-id ws_xxx    # confirm; list takes exactly one scope filter
  unset OPENAI_ADMIN_KEY
  ```

  After `create` succeeds, wait 25 to 30 seconds before expecting the tunnel to be active. To find the organization and workspace IDs, look up the existing Ralph Bridge tunnel with `tunnel-client admin tunnels get tunnel_aaa…` (it accepts a runtime key) and reuse its attachments; this project has not seen that output.

**Runtime keys.** Each `tunnel-client` needs a restricted key with Tunnels Read and Use. You can create one per app to limit what a leaked key can do. This project did not verify whether a key can be limited to a single tunnel, so check the key's permissions in Platform.

**Keep the apps apart on the computer.**

1. Unique profile names and, for services, a separate service user and `HOME` per app so profiles in `~/.config/tunnel-client/` cannot collide.
2. Unique health listener ports. List what is taken first: `ss -ltn | grep -E ':180[0-9]{2}\b'`.
3. Unique upstream ports. If another HTTP MCP server already uses `8000`, change `port:` in this server's `config.yaml`, and the profile URL with it.
4. A separate environment file per app containing only that app's secrets. The Second Brain tunnel must never see Ralph's GitHub credentials, and Ralph's must never see `SECOND_BRAIN_UPSTREAM_AUTH`.
5. Separate service units, named per app (`deploy/second-brain-tunnel.service.example` is one).

**ChatGPT side.** Create one app per tunnel and name them distinctly. After any change, rescan that app's tools while its tunnel is running, then start a new conversation and mention the app by name.

**Check that they do not interfere.** With both tunnels running, `curl -s http://127.0.0.1:18080/readyz` and `curl -s http://127.0.0.1:18081/readyz` should both report ready. Run each app's smoke test (`ralph_ping` for Ralph; test row 1 above for this server). Stop one `tunnel-client`: only that app should fail, and the other should keep working. Restart it and rescan.

If Ralph Bridge runs on a different machine, the tunnels are independent anyway and only the unique-name, unique-secrets, and ChatGPT-app points apply.

### Troubleshooting

- **`doctor` or `/readyz` reports degraded.** Run `tunnel-client doctor --profile second-brain --explain`. Plain HTTP servers should reach ready when OAuth discovery returns 404 on every candidate; a 5xx or malformed metadata response keeps readiness degraded.
- **Tools scan fails with 401.** The header is not reaching the server: check that the profile has `mcp.extra_headers` with `Authorization: "env:SECOND_BRAIN_UPSTREAM_AUTH"` (or that `MCP_EXTRA_HEADERS` is exported), that `SECOND_BRAIN_UPSTREAM_AUTH` is set in the same shell or service environment file that runs `tunnel-client` and holds `Bearer <token>` (not just the token), and that the server was restarted after adding `CHATGPT_MCP_TOKEN`.
- **403 from the server.** The Host or Origin check rejected the request. The tunnel calls `http://127.0.0.1:8000/mcp`, which the default policy accepts; a different upstream URL needs a matching `trusted_hosts` entry.
- **Tool missing or stale.** Rescan while the tunnel is running, then start a new conversation.
- **Oversized responses.** The Ralph Bridge project recorded a tunnel disconnect on a response of about 10 MiB. This server's responses are bounded by `limits.response_bytes` (256 KiB by default), far below that.

### Security notes

- The token injected by `tunnel-client` is a bearer credential for this server. Keep it in a `0600` file or a protected environment file, never in the profile YAML committed anywhere.
- Anyone who can use the app in your ChatGPT workspace can send prompts and selected context to your local Ollama and read the answers. Choose the workspace and its members accordingly.
- Stopping `tunnel-client` makes the server unreachable from ChatGPT immediately.
- ChatGPT content sent to this server is stored on this machine under the `chatgpt` principal; see `docs/operations.md` for retention and export.

For setup, database backup, administration, and troubleshooting, see [`../operations.md`](../operations.md). Ollama model tags are machine-specific; never copy another workstation's private `config.yaml` blindly.
