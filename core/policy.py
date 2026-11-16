"""
core/policy.py — Approval/deny gate checked before a tool actually runs.

Rules live in policy.yaml at the repo root (overridable via SANDBOX_POLICY_FILE).
Each rule matches a tool name and, optionally, a regex against one of that
tool's string arguments (e.g. `command` for run_shell_command). The first
matching rule wins; if nothing matches, `default` applies.

This exists so a hosted model (Claude/ChatGPT via MCP) can't silently run a
destructive or sensitive command just because it decided to — denies stop
the call outright, approvals require a human in the loop before execution.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import yaml

DEFAULT_POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "policy.yaml")


@dataclass
class PolicyDecision:
    action: str  # "allow" | "deny" | "approve"
    reason: str
    rule: dict | None = None

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    @property
    def denied(self) -> bool:
        return self.action == "deny"

    @property
    def needs_approval(self) -> bool:
        return self.action == "approve"


_STRING_ARG_CANDIDATES = ("command", "code", "script", "url", "packages", "filename", "content")


def _rule_text(args: dict[str, Any]) -> str:
    """Flatten the string-ish arguments of a tool call into one blob to regex against."""
    parts = []
    for key in _STRING_ARG_CANDIDATES:
        if key in args and args[key] is not None:
            parts.append(str(args[key]))
    return "\n".join(parts)


_cached_policy: dict | None = None
_cached_path: str | None = None


def _load_policy() -> dict:
    global _cached_policy, _cached_path
    path = os.getenv("SANDBOX_POLICY_FILE", DEFAULT_POLICY_PATH)
    if _cached_policy is not None and _cached_path == path:
        return _cached_policy
    if not os.path.exists(path):
        _cached_policy, _cached_path = {"default": "allow", "rules": []}, path
        return _cached_policy
    with open(path, "r") as f:
        _cached_policy = yaml.safe_load(f) or {"default": "allow", "rules": []}
    _cached_path = path
    return _cached_policy


def reload_policy() -> None:
    """Force the next check_policy() call to re-read policy.yaml from disk."""
    global _cached_policy
    _cached_policy = None


def check_policy(tool_name: str, args: dict[str, Any]) -> PolicyDecision:
    policy = _load_policy()
    text = _rule_text(args)

    for rule in policy.get("rules", []):
        if rule.get("tool") not in (tool_name, "*"):
            continue
        pattern = rule.get("match")
        if pattern is not None and not re.search(pattern, text, re.IGNORECASE):
            continue
        return PolicyDecision(action=rule.get("action", "allow"), reason=rule.get("reason", ""), rule=rule)

    return PolicyDecision(action=policy.get("default", "allow"), reason="No matching rule; default policy applies.")
