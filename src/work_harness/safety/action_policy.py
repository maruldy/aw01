from __future__ import annotations

from work_harness.domain.models import DecisionType, PolicyEvaluation, ToolInvocation


class ActionPolicy:
    _allowlist = {
        "git": {"status", "diff", "add", "commit", "push", "checkout", "switch"},
        "pytest": set(),
        "ruff": set(),
        "mypy": set(),
    }
    _approval_required = {
        ("git", "push"),
        ("git", "commit"),
        ("git", "checkout"),
        ("git", "switch"),
    }

    def evaluate(
        self,
        invocation: ToolInvocation,
        decision: DecisionType | None,
    ) -> PolicyEvaluation:
        if invocation.tool not in self._allowlist:
            return PolicyEvaluation(
                allowed=False,
                requires_approval=False,
                reason=f"{invocation.tool} is not in the allowlist.",
            )

        subcommand = invocation.args[0] if invocation.args else ""
        allowed_commands = self._allowlist[invocation.tool]
        if allowed_commands and subcommand not in allowed_commands:
            return PolicyEvaluation(
                allowed=False,
                requires_approval=False,
                reason=f"{invocation.tool} {subcommand} is not permitted.",
            )

        if (
            invocation.tool,
            subcommand,
        ) in self._approval_required and decision != DecisionType.ACCEPT:
            return PolicyEvaluation(
                allowed=False,
                requires_approval=True,
                reason=f"{invocation.tool} {subcommand} requires human approval.",
            )

        return PolicyEvaluation(allowed=True, requires_approval=False, reason="Allowed by policy.")
