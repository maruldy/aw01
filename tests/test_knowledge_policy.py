from work_harness.config import Settings
from work_harness.domain.models import ActivityEvent, ConnectorSource
from work_harness.services.knowledge_policy import evaluate_storeability


def test_jira_storeability_requires_allowlisted_project() -> None:
    settings = Settings(jira_projects="OPS,PLATFORM")
    allowed_event = ActivityEvent(
        source=ConnectorSource.JIRA,
        event_type="jira:issue_updated",
        title="OPS-12 issue updated",
        body="Latency regression",
        external_id="10001",
        metadata={"issue": {"key": "OPS-12"}},
    )
    blocked_event = ActivityEvent(
        source=ConnectorSource.JIRA,
        event_type="jira:issue_updated",
        title="APP-5 issue updated",
        body="Unrelated app issue",
        external_id="10002",
        metadata={"issue": {"key": "APP-5"}},
    )

    allowed = evaluate_storeability(allowed_event, settings)
    blocked = evaluate_storeability(blocked_event, settings)

    assert allowed.storeable is True
    assert allowed.scope_key == "OPS"
    assert blocked.storeable is False
    assert blocked.scope_key == "APP"


def test_slack_storeability_requires_allowed_channel_or_direct_message() -> None:
    settings = Settings(slack_allowed_channels="COPS,CPLATFORM")
    channel_event = ActivityEvent(
        source=ConnectorSource.SLACK,
        event_type="app_mention",
        title="Mention in ops",
        body="deploy failed",
        external_id="evt-1",
        metadata={"event": {"channel": "COPS", "channel_type": "channel"}},
    )
    blocked_channel_event = ActivityEvent(
        source=ConnectorSource.SLACK,
        event_type="message",
        title="General chatter",
        body="random note",
        external_id="evt-2",
        metadata={"event": {"channel": "CRANDOM", "channel_type": "channel"}},
    )
    direct_message_event = ActivityEvent(
        source=ConnectorSource.SLACK,
        event_type="message.im",
        title="Direct message",
        body="Can you review this?",
        external_id="evt-3",
        metadata={"event": {"channel": "D123", "channel_type": "im"}},
    )

    allowed = evaluate_storeability(channel_event, settings)
    blocked = evaluate_storeability(blocked_channel_event, settings)
    direct = evaluate_storeability(direct_message_event, settings)

    assert allowed.storeable is True
    assert allowed.scope_key == "COPS"
    assert blocked.storeable is False
    assert blocked.scope_key == "CRANDOM"
    assert direct.storeable is True
    assert direct.scope_type == "channel"
