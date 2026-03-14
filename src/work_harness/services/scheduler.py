from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


class SchedulerService:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def list_jobs(self) -> list[dict[str, str]]:
        return [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else "",
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]
