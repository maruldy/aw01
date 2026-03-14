from __future__ import annotations

import json
from pathlib import Path

import aiosqlite


class SettingsStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_subscription_preferences (
                    source TEXT PRIMARY KEY,
                    selected_event_keys TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_runtime_settings (
                    source TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_oauth_states (
                    state TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    frontend_origin TEXT NOT NULL,
                    next_path TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def get_selected_event_keys(self, source: str) -> list[str] | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT selected_event_keys
                FROM connector_subscription_preferences
                WHERE source = ?
                """,
                (source,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def set_selected_event_keys(self, source: str, selected_event_keys: list[str]) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO connector_subscription_preferences (
                    source,
                    selected_event_keys,
                    updated_at
                )
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source) DO UPDATE SET
                    selected_event_keys = excluded.selected_event_keys,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source, json.dumps(selected_event_keys)),
            )
            await db.commit()

    async def get_runtime_settings(self, source: str) -> dict[str, str]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT settings_json
                FROM connector_runtime_settings
                WHERE source = ?
                """,
                (source,),
            )
            row = await cursor.fetchone()
        if row is None:
            return {}
        return json.loads(row[0])

    async def set_runtime_settings(self, source: str, values: dict[str, str]) -> None:
        current = await self.get_runtime_settings(source)
        merged = current.copy()
        for key, value in values.items():
            if value:
                merged[key] = value
            else:
                merged.pop(key, None)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO connector_runtime_settings (
                    source,
                    settings_json,
                    updated_at
                )
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source, json.dumps(merged)),
            )
            await db.commit()

    async def save_oauth_state(
        self,
        source: str,
        state: str,
        frontend_origin: str,
        next_path: str,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO connector_oauth_states (
                    state,
                    source,
                    frontend_origin,
                    next_path,
                    updated_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(state) DO UPDATE SET
                    source = excluded.source,
                    frontend_origin = excluded.frontend_origin,
                    next_path = excluded.next_path,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (state, source, frontend_origin, next_path),
            )
            await db.commit()

    async def consume_oauth_state(self, state: str) -> dict[str, str] | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT source, frontend_origin, next_path
                FROM connector_oauth_states
                WHERE state = ?
                """,
                (state,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            await db.execute(
                """
                DELETE FROM connector_oauth_states
                WHERE state = ?
                """,
                (state,),
            )
            await db.commit()
        return {
            "source": str(row[0]),
            "frontend_origin": str(row[1]),
            "next_path": str(row[2]),
        }
