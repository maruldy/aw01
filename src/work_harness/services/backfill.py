from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class BackfillStatus:
    state: str = "disabled"
    processed: int = 0
    total: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None


class BackfillService:
    def __init__(self, _knowledge_store: object | None = None) -> None:
        self._status = BackfillStatus()

    async def trigger(self) -> dict:
        return asdict(self._status)

    async def status(self) -> dict:
        return asdict(self._status)

    async def daily_delta_scan(self) -> dict:
        return {"job": "daily_delta_scan", "status": "disabled"}

    async def weekly_digest(self) -> dict:
        return {"job": "weekly_digest", "status": "disabled"}
