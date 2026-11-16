"""
core/executor.py — Shared execution facade.

Every caller that wants to run a sandbox tool — the local LangGraph agent,
the MCP server (used by Claude Code / ChatGPT / Codex), or a future UI —
funnels through execute_tool() instead of calling tools/dispatch.py directly.
Each call passes through, in order:

1. the policy gate (core/policy.py)      — deny stops it outright; approve
   either prompts the human at the terminal (local-agent) or returns a
   structured "needs_approval" result the host surfaces to its user (MCP
   callers, who have no terminal to prompt);
2. the audit/trace layer (core/audit.py) — every executed call is logged to
   a local JSONL ledger and emitted as a LangSmith span, tagged with which
   caller triggered it.

Nothing here duplicates tool logic — it only adds one dispatch point on top
of the existing sandbox/container.py and tools/implementations.py.
"""

from __future__ import annotations

from typing import Any

from sandbox.container import ensure_sandbox

# Imported lazily inside functions below: tools/__init__.py imports
# tools.langchain_adapter, which imports this module — a top-level import
# here would be circular.


class UnknownToolError(ValueError):
    """Raised when execute_tool() is asked to run a tool that isn't registered."""


def list_tools() -> list[str]:
    from tools.dispatch import TOOL_DISPATCH
    return sorted(TOOL_DISPATCH.keys())


def _prompt_local_approval(tool_name: str, args: dict[str, Any], reason: str) -> bool:
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    console.print(Panel(
        f"[bold yellow]Policy requires approval:[/] {reason}\n\n"
        f"Tool: {tool_name}\nArgs: {args}",
        title="Approval Required",
        border_style="yellow",
    ))
    answer = console.input("[bold green]Approve? (y/n): [/]").strip().lower()
    return answer in ("y", "yes")


def execute_tool(name: str, args: dict[str, Any], *, caller: str = "local-agent") -> dict[str, Any]:
    """Run one tool by name inside the sandbox, gated by policy and audited.

    Args:
        name: tool name, must be a key in tools.dispatch.TOOL_DISPATCH.
        args: keyword arguments to pass to the tool function.
        caller: identifies who initiated the call — "local-agent", "claude-code",
            "chatgpt", etc. Drives both the approval UX (prompt vs. structured
            return) and the audit trail's "who ran this" field.

    Raises:
        UnknownToolError: if `name` isn't a registered tool.
    """
    from tools.dispatch import TOOL_DISPATCH
    from core.policy import check_policy
    from core.audit import record_and_trace, record_policy_event

    if name not in TOOL_DISPATCH:
        raise UnknownToolError(f"Unknown tool: {name!r}. Available: {list_tools()}")

    decision = check_policy(name, args)
    decision_dict = {"action": decision.action, "reason": decision.reason}

    if decision.denied:
        record_policy_event(name, args, caller=caller, decision=decision_dict)
        return {"error": f"Blocked by policy: {decision.reason}", "policy": decision_dict, "executed": False}

    if decision.needs_approval:
        if caller == "local-agent":
            approved = _prompt_local_approval(name, args, decision.reason)
            decision_dict["approved"] = approved
            if not approved:
                record_policy_event(name, args, caller=caller, decision=decision_dict)
                return {"error": "Not approved by user.", "policy": decision_dict, "executed": False}
        else:
            # No terminal to prompt — surface the pending approval to the host
            # (Claude Code / ChatGPT) instead of blocking or guessing.
            record_policy_event(name, args, caller=caller, decision=decision_dict)
            return {
                "needs_approval": True,
                "reason": decision.reason,
                "tool": name,
                "args": args,
                "policy": decision_dict,
                "executed": False,
            }

    ensure_sandbox()
    fn = TOOL_DISPATCH[name]
    return record_and_trace(name, args, lambda: fn(**args), caller=caller, policy_decision=decision_dict)
