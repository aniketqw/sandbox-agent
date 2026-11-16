# sandbox-agent

An observable, policy-gated code-execution harness: a persistent Docker
container you own, with every command an agent runs logged to a local audit
trail and traced in LangSmith. Use it standalone (a LangGraph ReAct agent,
`harness.py`) or plug it into **Claude Code, ChatGPT/Codex, or any other
MCP-speaking host** via the bundled MCP server — so instead of executing code
in their opaque hosted sandbox, they execute it in yours, where you can see
every command, gate the risky ones, and replay the whole session as a trace.

## Why this exists

Hosted code-execution sandboxes (Claude's, ChatGPT's, E2B, Modal, ...) are
ephemeral and opaque by design — you get a result and maybe a "review the
work log" afterward. This project inverts that: the container is **yours**,
**persistent** across sessions, with your real workspace bind-mounted into
it, and **every single call** — command, stdout/stderr, exit code, who ran
it, why it was allowed/denied/held for approval — is written to
`.sandbox_audit/<session>.jsonl` and emitted as a LangSmith span.

See [`docs/DIFFERENTIATION.md`](docs/DIFFERENTIATION.md) for the honest
version of "why build this when X already exists."

## Architecture

```
                    ┌─────────────────────────────┐
  harness.py  ────▶ │                             │
  (local LangGraph  │     core/executor.py        │──▶ policy.yaml (allow/deny/approve)
   ReAct agent)     │   execute_tool(name, args,   │
                     │       caller=...)           │──▶ core/audit.py
  mcp_server/   ──▶ │                             │      (JSONL ledger + LangSmith span)
  server.py          └─────────────┬───────────────┘
  (Claude Code /                   │
   ChatGPT / Codex)                ▼
                          tools/dispatch.py
                          (16 tool implementations)
                                    │
                                    ▼
                          sandbox/container.py
                          (persistent Docker container,
                           agent_workspace/ ↔ /workspace)
```

Both callers — the local agent and any MCP host — funnel through the same
`core.executor.execute_tool()`, so instrumentation and policy are identical
regardless of who's driving.

## Quickstart: standalone agent

```bash
conda activate sandbox-agent   # or: pip install -r requirements.txt
docker --version                # make sure Docker Desktop/Colima/Rancher is running
python harness.py
```

The sandbox image (`sandbox-agent:latest`) builds from `Dockerfile.sandbox`
on first run if it doesn't exist. Set `LLM_PROVIDER=ollama` to use a local
model instead of the Anthropic proxy; see `.env` for all config.

## Quickstart: as an MCP server (Claude Code / ChatGPT / Codex)

**Claude Code (local stdio):**

```bash
claude mcp add --transport stdio sandbox-exec -- python -m mcp_server.server
```

or copy `mcp_server/claude_code.mcp.json.example` to `.mcp.json` and fill in
the absolute path. The bundled skill at `.claude/skills/sandbox-exec/` tells
Claude to route execution through these tools instead of its own Bash tool —
or install both together as a plugin via `.claude-plugin/plugin.json`.

**ChatGPT / Codex / OpenAI Agents SDK (streamable HTTP — stdio isn't supported there):**

```bash
python -m mcp_server.server --http --host 127.0.0.1 --port 8765
```

See `mcp_server/codex.config.toml.example` for Codex CLI registration. For
ChatGPT's hosted developer-mode connectors (which can't reach `127.0.0.1`),
tunnel the port (`ngrok http 8765`, a Tailscale Funnel, etc.) and register
the public HTTPS URL instead.

Either transport exposes the same 9 tools: `run_shell`, `run_python`,
`write_file`, `read_file`, `list_files`, `install_package`, `run_playwright`,
plus `get_audit_log` and `get_trace_url` — so the model can answer "what
have you run and why" about its own actions.

## Observability

```bash
python trace_cli.py              # tail the most recent session live
python trace_cli.py --list        # list known sessions
python trace_cli.py --no-follow   # print existing entries and exit
```

Set `LANGSMITH_API_KEY` (see `.env`) to also get a full LangSmith run tree —
`trace_cli.py` prints the project URL on startup.

## Policy

`policy.yaml` at the repo root is checked before every tool call
(`core/policy.py`). First matching rule wins; unmatched calls fall back to
`default`. A denied call never executes; an approval-required call either
prompts at the terminal (local agent) or returns a structured
`{"needs_approval": true, ...}` to the MCP host — nothing executes silently
behind your back either way.

## Known trade-offs

- The container's `agent_workspace/` bind mount trades isolation for
  utility — this is a dev-workstation container, not a hardened sandbox;
  don't point it at untrusted code.
- MCP timeouts are enforced client-side (a thread pool with `.result(timeout=...)`);
  a timed-out call's underlying container process is not killed.
- `--http` mode's caller identity (`SANDBOX_MCP_CALLER`) is set once at
  server launch, not per-connection — run separate server instances if you
  need to distinguish simultaneous ChatGPT/Codex sessions.

## Project layout

```
core/           execute_tool() facade, audit/trace layer, policy gate — shared by both callers below
agent/          LangGraph graph, state, and worker definitions (local agent)
mcp_server/     MCP server (stdio + streamable HTTP) for Claude Code / ChatGPT / Codex
tools/          Tool schemas, implementations, and dispatch table
sandbox/        Docker container lifecycle management
.claude/skills/sandbox-exec/  Claude Code skill instructing it to use the MCP tools
.claude-plugin/ Plugin manifest bundling the skill + MCP server for one-command install
policy.yaml     Allow/deny/approve rules checked before every tool call
trace_cli.py    Live audit-log tail + LangSmith URL
harness.py      Standalone LangGraph agent entry point (Rich REPL)
```

See `CLAUDE.md` for contributor-facing details (conda env, sub-agent pattern, debugging).
