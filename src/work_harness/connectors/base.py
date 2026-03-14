from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from work_harness.domain.models import ActivityEvent, ConnectorSource, EventSubscription


class ConnectorAdapter(ABC):
    source: ConnectorSource

    @abstractmethod
    async def validate(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def poll_events(self) -> list[ActivityEvent]:
        raise NotImplementedError

    @abstractmethod
    async def handle_webhook(self, payload: dict[str, Any]) -> ActivityEvent:
        raise NotImplementedError

    @abstractmethod
    async def fetch_context(self, event: ActivityEvent) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def execute_remote_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def available_subscriptions(self) -> list[EventSubscription]:
        raise NotImplementedError

    @abstractmethod
    def classify_event(self, event: ActivityEvent) -> str | None:
        raise NotImplementedError
