from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from work_harness.domain.models import AnalysisRecord
from work_harness.services.knowledge_store import KnowledgeStore


@dataclass
class BackfillStatus:
    state: str = "idle"
    processed: int = 0
    total: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None


class BackfillService:
    def __init__(self, knowledge_store: KnowledgeStore) -> None:
        self._knowledge_store = knowledge_store
        self._status = BackfillStatus()
        self._task: asyncio.Task | None = None

    async def trigger(self) -> dict:
        if self._task and not self._task.done():
            return asdict(self._status)
        self._task = asyncio.create_task(self._run())
        return asdict(self._status)

    async def _run(self) -> None:
        self._status = BackfillStatus(
            state="running",
            processed=0,
            total=1,
            started_at=datetime.now(tz=UTC).isoformat(),
        )
        try:
            record = AnalysisRecord(
                ticket_key="BACKFILL-0",
                core_issue="Backfill initialized the knowledge store.",
                summary="Backfill dry run completed.",
                final_summary="Backfill completed without remote connector data.",
            )
            await self._knowledge_store.store_analysis(record)
            self._status.processed = 1
            self._status.state = "completed"
        except Exception as exc:  # pragma: no cover - defensive
            self._status.state = "failed"
            self._status.last_error = str(exc)
        finally:
            self._status.finished_at = datetime.now(tz=UTC).isoformat()

    async def status(self) -> dict:
        return asdict(self._status)

    async def daily_delta_scan(self) -> dict:
        return {"job": "daily_delta_scan", "status": "ok"}

    async def weekly_digest(self) -> dict:
        return {"job": "weekly_digest", "status": "ok"}
