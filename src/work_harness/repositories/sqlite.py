"""SQLite-backed repositories for WorkItem and ExecutionRun."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

from work_harness.domain.models import ExecutionRun, WorkItem

logger = logging.getLogger("work_harness.repositories.sqlite")


class SqliteWorkItemRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS work_items (
                    id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_wi_updated
                ON work_items(updated_at DESC)
                """
            )
            await db.commit()
        logger.info("WorkItem repository initialized: %s", self._db_path)

    async def upsert(self, item: WorkItem) -> WorkItem:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO work_items (id, data_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (item.id, item.model_dump_json()),
            )
            await db.commit()
        return item

    async def get(self, item_id: str) -> WorkItem | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data_json FROM work_items WHERE id = ?",
                (item_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return WorkItem.model_validate_json(row[0])

    async def list(self) -> list[WorkItem]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data_json FROM work_items ORDER BY updated_at DESC LIMIT 100"
            )
            rows = await cursor.fetchall()
        return [WorkItem.model_validate_json(row[0]) for row in rows]


class SqliteRunRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_runs (
                    thread_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()
        logger.info("Run repository initialized: %s", self._db_path)

    async def upsert(self, run: ExecutionRun) -> ExecutionRun:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO execution_runs (thread_id, data_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(thread_id) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (run.thread_id, run.model_dump_json()),
            )
            await db.commit()
        return run

    async def get(self, thread_id: str) -> ExecutionRun | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data_json FROM execution_runs WHERE thread_id = ?",
                (thread_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return ExecutionRun.model_validate_json(row[0])

    async def append_event(self, thread_id: str, event: dict[str, Any]) -> None:
        run = await self.get(thread_id)
        if run:
            run.events.append(event)
            await self.upsert(run)

    async def get_events(self, thread_id: str) -> list[dict[str, Any]]:
        run = await self.get(thread_id)
        return run.events if run else []
