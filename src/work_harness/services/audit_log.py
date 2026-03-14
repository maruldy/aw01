from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class AuditLog:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    async def append(self, event_type: str, payload: dict[str, Any]) -> None:
        self._entries.append(
            {
                "event_type": event_type,
                "payload": payload,
                "created_at": datetime.now(tz=UTC).isoformat(),
            }
        )

    async def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._entries[-limit:]

