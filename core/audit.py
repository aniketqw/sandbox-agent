"""
core/audit.py — Per-tool-call observability: a local JSONL ledger that
survives without any SaaS, plus a LangSmith span so the same call shows up
as a traceable run.

This is the differentiator described in the plan: hosted sandboxes give you
"review the work log" after the fact; this gives you every command, its
stdout/stderr/exit code, who triggered it (local agent vs. Claude Code vs.
ChatGPT), and why — as it happens, in infra you own.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from langsmith import trace

AUDIT_DIR = os.path.join(os.path.dirname(__file__), "..", ".sandbox_audit")

_session_id: str | None = None


def get_session_id() -> str:
    """One audit session per process run, unless SANDBOX_SESSION_ID is set
    (e.g. by the MCP server to tie a session to one host-side conversation)."""
    global _session_id
    if _session_id is None:
        _session_id = os.getenv("SANDBOX_SESSION_ID") or uuid.uuid4().hex[:12]
    return _session_id


def _log_path(session_id: str) -> str:
    os.makedirs(AUDIT_DIR, exist_ok=True)
    return os.path.join(AUDIT_DIR, f"{session_id}.jsonl")


def _truncate(value: Any, limit: int = 4000) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [truncated, {len(value) - limit} more chars]"
    return value


def _append_jsonl(session_id: str, record: dict) -> None:
    with open(_log_path(session_id), "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_audit_log(session_id: str | None = None, limit: int = 100) -> list[dict]:
    """Read back the most recent `limit` entries for a session (default: current)."""
    session_id = session_id or get_session_id()
    path = _log_path(session_id)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        lines = f.readlines()
    records = [json.loads(line) for line in lines if line.strip()]
    return records[-limit:]


def record_and_trace(
    tool_name: str,
    args: dict[str, Any],
    fn,
    *,
    caller: str = "local-agent",
    policy_decision: dict | None = None,
):
    """Run `fn(**args)`, logging it to the JSONL ledger and to LangSmith.

    `fn` is called exactly once, inside the LangSmith span, so the trace's
    timing reflects the real execution window. Policy denials/approvals are
    recorded even when `fn` is never actually called (pass policy_decision
    and a no-op fn, or see core/executor.py for how denies short-circuit).
    """
    session_id = get_session_id()
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    with trace(
        name=f"tool:{tool_name}",
        run_type="tool",
        inputs={"args": args},
        metadata={"session_id": session_id, "caller": caller, "tool": tool_name},
        tags=[caller, tool_name],
    ) as run:
        error = None
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001 - we want to log and re-raise everything
            error = str(e)
            duration = time.time() - started
            run.end(error=error)
            _append_jsonl(session_id, {
                "ts": started_at,
                "session_id": session_id,
                "caller": caller,
                "tool": tool_name,
                "args": {k: _truncate(v) for k, v in args.items()},
                "duration_s": round(duration, 3),
                "error": error,
                "policy": policy_decision,
                "langsmith_run_id": str(run.id) if run else None,
            })
            raise

        duration = time.time() - started
        run.end(outputs={"result": _truncate_result(result)})

    _append_jsonl(session_id, {
        "ts": started_at,
        "session_id": session_id,
        "caller": caller,
        "tool": tool_name,
        "args": {k: _truncate(v) for k, v in args.items()},
        "duration_s": round(duration, 3),
        "exit_code": result.get("exit_code") if isinstance(result, dict) else None,
        "result_preview": _truncate_result(result),
        "policy": policy_decision,
        "langsmith_run_id": str(run.id) if run else None,
    })
    return result


def _truncate_result(result: Any) -> Any:
    if isinstance(result, dict):
        return {k: _truncate(v) for k, v in result.items()}
    return _truncate(result)


def get_trace_url_info() -> dict:
    """Best-effort LangSmith project URL for this session's traces."""
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT", "sandbox-agent")
    tracing_on = bool(os.getenv("LANGSMITH_API_KEY")) or os.getenv("LANGCHAIN_TRACING_V2") == "true"
    if not tracing_on:
        return {"tracing_enabled": False, "note": "Set LANGSMITH_API_KEY to enable LangSmith tracing."}
    return {
        "tracing_enabled": True,
        "project": project,
        "url": f"https://smith.langchain.com/o/-/projects/p/{project}",
        "note": "Filter by metadata.session_id to see only this session's run tree.",
    }


def record_policy_event(tool_name: str, args: dict[str, Any], *, caller: str, decision: dict) -> None:
    """Log a call that never ran at all because the policy gate denied it,
    or is waiting on a human/host decision before it can run."""
    session_id = get_session_id()
    _append_jsonl(session_id, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "caller": caller,
        "tool": tool_name,
        "args": {k: _truncate(v) for k, v in args.items()},
        "duration_s": 0,
        "policy": decision,
        "executed": False,
    })
