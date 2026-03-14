from __future__ import annotations

import asyncio
import logging

from work_harness.domain.models import DecisionType, ToolInvocation
from work_harness.safety.action_policy import ActionPolicy

logger = logging.getLogger("work_harness.safety.tool_registry")


class ToolRegistry:
    def __init__(self, policy: ActionPolicy | None = None) -> None:
        self._policy = policy or ActionPolicy()

    async def run(
        self,
        invocation: ToolInvocation,
        decision: DecisionType | None = None,
    ) -> dict[str, object]:
        logger.info("Tool invocation: tool=%s args=%s", invocation.tool, invocation.args)
        evaluation = self._policy.evaluate(invocation, decision)
        if not evaluation.allowed:
            logger.warning("Tool blocked: tool=%s reason=%s", invocation.tool, evaluation.reason)
            return {
                "ok": False,
                "reason": evaluation.reason,
                "requires_approval": evaluation.requires_approval,
            }

        process = await asyncio.create_subprocess_exec(
            invocation.tool,
            *invocation.args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return {
            "ok": process.returncode == 0,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "returncode": process.returncode,
        }
