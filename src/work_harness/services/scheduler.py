from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from work_harness.config import Settings
from work_harness.services.backfill import BackfillService


class SchedulerService:
    def __init__(self, settings: Settings, backfill_service: BackfillService) -> None:
        self._settings = settings
        self._backfill_service = backfill_service
        self._scheduler = AsyncIOScheduler()
        self._configured = False

    def start(self) -> None:
        if not self._configured:
            self._scheduler.add_job(
                self._backfill_service.daily_delta_scan,
                CronTrigger(hour=self._settings.daily_delta_scan_hour, minute=0),
                id="daily_delta_scan",
                replace_existing=True,
            )
            self._scheduler.add_job(
                self._backfill_service.weekly_digest,
                CronTrigger(
                    day_of_week=self._settings.weekly_digest_day,
                    hour=self._settings.weekly_digest_hour,
                    minute=0,
                ),
                id="weekly_digest",
                replace_existing=True,
            )
            self._configured = True
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
