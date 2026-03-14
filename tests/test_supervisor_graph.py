import pytest

from work_harness.domain.models import ActivityEvent, ConnectorSource, WorkItemStatus
from work_harness.graph.supervisor import SupervisorService
from work_harness.providers.base import CompletionResult


class FakeChatProvider:
    async def complete_json(self, prompt: str, schema: dict) -> CompletionResult:
        return CompletionResult(
            content="",
            data={
                "summary": "Slack mention needs follow-up",
                "suggested_action": "Prepare a short response draft",
                "priority": "high",
                "recommended_agent": "slack_context",
            },
        )


@pytest.mark.asyncio
async def test_supervisor_creates_work_item_from_event() -> None:
    service = SupervisorService(chat_provider=FakeChatProvider())

    event = ActivityEvent(
        source=ConnectorSource.SLACK,
        event_type="slack.mention",
        title="Mentioned in #platform",
        body="Can someone explain why the deploy failed?",
        external_id="evt-1",
        actor="U123",
    )

    result = await service.handle_event(event)

    assert result.work_item.source == ConnectorSource.SLACK
    assert result.work_item.status == WorkItemStatus.PENDING
    assert result.work_item.proposal.summary == "Slack mention needs follow-up"
    assert result.work_item.proposal.recommended_agent == "slack_context"
    assert result.run.current_step == "proposal_ready"
