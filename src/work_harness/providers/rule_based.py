from __future__ import annotations

from work_harness.providers.base import CompletionResult


class RuleBasedChatProvider:
    async def complete_json(self, prompt: str, schema: dict) -> CompletionResult:
        lowered = prompt.lower()
        recommended_agent = "briefing"
        priority = "medium"
        if "slack" in lowered:
            recommended_agent = "slack_context"
            priority = "high"
        elif "github" in lowered:
            recommended_agent = "github_change"
            priority = "high"
        elif "jira" in lowered or "confluence" in lowered:
            recommended_agent = "atlassian_context"
        return CompletionResult(
            content="rule-based",
            data={
                "summary": "AI reviewed the incoming activity and prepared a work item.",
                "suggested_action": "Review the proposal and decide whether to proceed.",
                "priority": priority,
                "recommended_agent": recommended_agent,
            },
        )

