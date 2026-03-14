from work_harness.domain.models import DecisionType, ToolInvocation
from work_harness.safety.action_policy import ActionPolicy


def test_denies_unregistered_tools() -> None:
    policy = ActionPolicy()

    allowed = policy.evaluate(
        ToolInvocation(tool="curl", args=["https://example.com"]),
        decision=None,
    )

    assert allowed.allowed is False
    assert allowed.requires_approval is False
    assert "not in the allowlist" in allowed.reason


def test_requires_human_approval_for_push_operations() -> None:
    policy = ActionPolicy()

    evaluation = policy.evaluate(
        ToolInvocation(tool="git", args=["push", "origin", "feature/test"]),
        decision=None,
    )

    assert evaluation.allowed is False
    assert evaluation.requires_approval is True
    assert "human approval" in evaluation.reason


def test_allows_push_after_accept_decision() -> None:
    policy = ActionPolicy()

    evaluation = policy.evaluate(
        ToolInvocation(tool="git", args=["push", "origin", "feature/test"]),
        decision=DecisionType.ACCEPT,
    )

    assert evaluation.allowed is True
    assert evaluation.requires_approval is False
