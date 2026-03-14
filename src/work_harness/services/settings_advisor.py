from __future__ import annotations

from typing import Any

from work_harness.domain.models import (
    CapabilityStatus,
    ConnectorCapability,
    ConnectorSource,
    EventSubscription,
)
from work_harness.providers.base import ChatModelProvider


def _verified_keys(capabilities: list[ConnectorCapability]) -> set[str]:
    return {cap.key for cap in capabilities if cap.status == CapabilityStatus.VERIFIED}


class SettingsAdvisor:
    def __init__(self, provider: ChatModelProvider | None = None) -> None:
        self._provider = provider
        self._cache: dict[str, dict[str, Any]] = {}

    async def recommend(
        self,
        source: ConnectorSource,
        capabilities: list[ConnectorCapability],
        subscriptions: list[EventSubscription],
    ) -> dict[str, Any]:
        verified = _verified_keys(capabilities)
        cache_key = f"{source.value}:{','.join(sorted(verified))}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        if self._provider is not None:
            recommendation = await self._recommend_with_llm(
                source, capabilities, subscriptions,
            )
            if recommendation is not None:
                self._cache[cache_key] = recommendation
                return recommendation
        result = self._fallback_recommendation(
            source, capabilities, subscriptions,
        )
        self._cache[cache_key] = result
        return result

    async def _recommend_with_llm(
        self,
        source: ConnectorSource,
        capabilities: list[ConnectorCapability],
        subscriptions: list[EventSubscription],
    ) -> dict[str, Any] | None:
        prompt = (
            "You are a safety-focused harness advisor.\n"
            "Recommend the minimum event subscriptions needed for a safe initial setup.\n"
            f"Source: {source.value}\n"
            f"Capabilities: {[cap.model_dump(mode='json') for cap in capabilities]}\n"
            f"Subscriptions: {[sub.model_dump(mode='json') for sub in subscriptions]}\n"
            "Return only the minimum safe set. Prefer fewer subscriptions."
        )
        schema = {
            "title": "ConnectorRecommendation",
            "type": "object",
            "properties": {
                "recommended_event_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "advisory": {"type": "string"},
            },
            "required": ["recommended_event_keys", "advisory"],
        }
        try:
            completion = await self._provider.complete_json(prompt, schema)
            data = completion.data or {}
            return {
                "recommended_event_keys": list(data.get("recommended_event_keys", [])),
                "advisory": str(data.get("advisory", "")),
            }
        except Exception:
            return None

    def _fallback_recommendation(
        self,
        source: ConnectorSource,
        capabilities: list[ConnectorCapability],
        subscriptions: list[EventSubscription],
    ) -> dict[str, Any]:
        verified = _verified_keys(capabilities)
        available = [
            subscription.key
            for subscription in subscriptions
            if set(subscription.required_capabilities).issubset(verified)
        ]

        recommended_by_source = {
            ConnectorSource.GITHUB: ["review_requested", "pull_request_activity"],
            ConnectorSource.SLACK: ["app_mention"],
            ConnectorSource.JIRA: ["issue_created", "issue_transitioned"],
            ConnectorSource.CONFLUENCE: ["page_updated"],
        }
        recommended_event_keys = [
            key for key in recommended_by_source.get(source, []) if key in available
        ]

        if not recommended_event_keys:
            advisory = (
                "No safe default subscriptions are enabled yet. "
                "Either connect the token first or choose subscriptions manually."
            )
        else:
            advisory = (
                "The harness recommends a minimal initial subscription set based on verified "
                "read-only capabilities. You can widen it later after reviewing noise and scope."
            )

        return {
            "recommended_event_keys": recommended_event_keys,
            "advisory": advisory,
        }
