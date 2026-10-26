# One-time setup: register the Second Brain (jcricket) MCP server with Claude Code

**For Codex.** The user wants you to set up the local `second-brain` MCP server **for Claude Code** (not for yourself). Claude Code cannot edit its own credentials-bearing config here, so you do it, using the `claude` CLI. Do the steps in order, once, then report. Background: `docs/integrations/local-clients.md`.

The server is a private, tool-free Ollama chatbot. It listens on loopback only and identifies each client by its own bearer token. Claude Code's principal is **`claude-code`**; do not use Codex's token or principal for this task.

## Rules

- Never print, copy, or commit a token. Do not read `~/.config/second-brain/credentials.env`; the helper script reads it for you.
- Do not read or edit `~/.claude.json` directly. Use the `claude mcp` commands.
- Do not start, stop, or reconfigure the server, and do not change Codex's own config. Change only Claude Code's `second-brain` entry.
- If a step fails and this file does not say what to do, stop and report.

## 1. Check that the server is running (do this first)

```sh
grep '^port' /home/jovyan/work/jcricket/config.yaml     # expect: port: 18765
curl -s -m3 http://127.0.0.1:18765/healthz               # expect: {"status":"ok"}
```

If you do not get `{"status":"ok"}`, **stop**. Do not start the server. Tell the user it is not running and ask them to run:

```sh
cd /home/jovyan/work/jcricket && setsid nohup scripts/run_local.sh > ~/second-brain.log 2>&1 < /dev/null &
```

Continue only after the health check passes. (If `config.yaml` shows a different port, use it in place of `18765` everywhere below.)

## 2. Check the token helper for the `claude-code` principal

```sh
python3 /home/jovyan/work/jcricket/deploy/auth_headers.py claude-code \
  | python3 -c 'import json,sys; print(list(json.load(sys.stdin)))'
```

Expect `['Authorization']`. If it prints `cannot read local MCP credentials: …`, **stop and report that message**; the user must fix the credentials.

## 3. Register the server with Claude Code

```sh
claude mcp get second-brain
```

- If it shows `Type: http`, `URL: http://127.0.0.1:18765/mcp`, and `Status: ✔ Connected`, it is already set up. Skip to step 4.
- Otherwise (not found, a different URL such as the old port `8000`, or `Failed to connect`), re-register it. User scope makes it available in every project:

  ```sh
  claude mcp remove second-brain -s user      # only if an entry already exists
  claude mcp add-json second-brain '{"type":"http","url":"http://127.0.0.1:18765/mcp","headersHelper":"python3 /home/jovyan/work/jcricket/deploy/auth_headers.py claude-code"}' --scope user
  claude mcp get second-brain
  ```

  If `Status` says `Failed to connect`, check step 1 again (the server may have stopped) before changing anything else.

If the `claude` command is missing, or your sandbox stops it from writing to the user's home (for example `~/.claude.json`), **do not work around that**. Stop and give the user the two `claude mcp` commands above to run themselves.

## 4. Verify

```sh
claude mcp get second-brain      # expect: Connected, URL http://127.0.0.1:18765/mcp

AUTH=$(python3 /home/jovyan/work/jcricket/deploy/auth_headers.py claude-code \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["Authorization"])')
curl -s -m5 http://127.0.0.1:18765/mcp \
  -H "Authorization: $AUTH" -H "Host: 127.0.0.1:18765" \
  -H "Accept: application/json, text/event-stream" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; print([t["name"] for t in json.load(sys.stdin)["result"]["tools"]])'
```

Expect `['ask_second_brain', 'list_models']`. Do not echo `$AUTH`.

A Claude Code session that is already open does not pick up a changed MCP entry on its own. Tell the user to start a **new** Claude Code session (or run `/mcp` and reconnect `second-brain`), then ask Claude Code to call `list_models` (expect a list of Ollama models and `default_profile: "32k"`) and `ask_second_brain` once with a short question and `model_profile: "32k"` (expect an `answer` and a `conversation_id`).

## 5. Report

Tell the user, briefly: whether the server was running, whether Claude Code was already registered or you changed it, the results of step 4, and anything you stopped on. Include no tokens.
