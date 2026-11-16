# Why build this when X already exists?

Honest answer, as of late 2026.

## Not novel — own it

- **Local Docker execution for agents.** OpenHands 1.0 does this by default.
  Several community MCP servers (`code-sandbox-mcp`, `mcp-server-docker`) do
  it too.
- **Reflection/retry on tool failure.** Standard LangGraph pattern
  (`agent/graph.py`'s `reflect_node`).
- **Human-in-the-loop interrupts.** LangGraph `interrupt()`, OpenHands
  confirmation mode, Claude Code permission prompts all do this.
- **"Sandboxed code execution" as a category.** Crowded and well-funded: E2B,
  Daytona, Modal Sandboxes, Docker Sandboxes (GA Sept 2026), Anthropic's own
  self-hosted-sandboxes beta (Nov 2026).

## What's actually defensible — the composition

No public project, as far as I've found, combines all five of:

1. **Persistent, user-owned, bind-mounted container** reused across
   sessions — hosted sandboxes are ephemeral by design; local MCP exec
   servers are stateless one-shot wrappers.
2. **Observability as the product, not an afterthought** — a per-command
   ledger (`.sandbox_audit/*.jsonl`: command, stdout/stderr, exit code) plus
   a LangSmith trace of the decision graph. Codex cloud's own docs say
   "review the work log"; MCP audit gateways log the protocol hop, not what
   actually ran inside the container.
3. **Policy/approval gates fused into the execution graph itself**
   (`core/policy.py` + `core/executor.py`), not bolted onto a UI afterward.
4. **MCP + skill exposure** — bring your own observable sandbox to a hosted
   model. Vendors now concede users want self-hosted execution (Anthropic's
   beta), but keep the loop and visibility on their side.
5. **A small, readable, LLM-pluggable codebase** (Anthropic proxy or Ollama)
   versus a full product like OpenHands.

**Positioning:** lead with *user-owned + persistent + traceable*, not "local
Docker" — that part is commoditized now that Docker Sandboxes is GA.

**Trade-off to volunteer, not hide:** bind-mounting the real workspace trades
isolation for utility. A container is not a microVM security boundary. This
is a deliberate choice for dev workflows, not a security claim.

**Credible fast-follow threat:** Docker's own MCP Toolkit + Gateway, which
already does containerized MCP execution with some guardrails/observability
at the protocol layer.

## Scripted answers

**"E2B/Modal exist."**
They rent you an opaque, ephemeral VM. This inverts the threat model:
execution in a container I own, my real workspace mounted, persistent
across sessions, every command in an audit trail and a LangSmith trace.
Anthropic shipping self-hosted sandboxes this year is the market agreeing
with the bet.

**"OpenHands already does local Docker + confirmations."**
OpenHands is a full autonomous engineer. This is a reusable *execution
harness* — a small LangGraph with a failure-classifying reflection node and
HITL as first-class graph nodes, designed to be mounted *under* other
agents via MCP, which OpenHands isn't.

**"There are already Docker MCP servers."**
The existing ones are stateless one-shot exec wrappers — no audit, no
traces, no approvals, no persistent container identity. The gap isn't "run
code in Docker over MCP" — it's doing that with a durable environment and a
forensic record.

**"Claude/ChatGPT already execute code."**
Exactly — that's the problem statement. Codex cloud's own docs tell you to
"review the work log" after the fact, with no egress log. This keeps the
frontier model's reasoning but moves execution into a container you
control, behind your approval gates, with a trace you can replay — the
piece hosted interpreters structurally can't give you.
