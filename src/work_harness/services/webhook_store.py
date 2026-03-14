from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from work_harness.domain.models import WebhookDeliveryEnvelope, WebhookProvider


class WebhookStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivery_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    verified BOOLEAN NOT NULL,
                    verification_method TEXT NOT NULL,
                    verification_reason TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    resource_hint TEXT,
                    actor_hint TEXT,
                    status TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_webhook_provider_received
                ON webhook_deliveries(provider, received_at DESC)
                """
            )
            await db.commit()

    async def persist_delivery(self, envelope: WebhookDeliveryEnvelope) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO webhook_deliveries (
                    provider,
                    received_at,
                    delivery_id,
                    event_type,
                    verified,
                    verification_method,
                    verification_reason,
                    headers_json,
                    payload_hash,
                    resource_hint,
                    actor_hint,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope.provider.value,
                    envelope.received_at.isoformat(),
                    envelope.delivery_id,
                    envelope.event_type,
                    int(envelope.verified),
                    envelope.verification_method,
                    envelope.verification_reason,
                    json.dumps(envelope.headers_json),
                    envelope.payload_hash,
                    envelope.resource_hint,
                    envelope.actor_hint,
                    envelope.status,
                ),
            )
            await db.commit()

    async def list_deliveries(
        self,
        provider: WebhookProvider | None = None,
        verified: bool | None = None,
        limit: int = 20,
    ) -> list[WebhookDeliveryEnvelope]:
        clauses: list[str] = []
        values: list[object] = []
        if provider is not None:
            clauses.append("provider = ?")
            values.append(provider.value)
        if verified is not None:
            clauses.append("verified = ?")
            values.append(int(verified))

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT provider, delivery_id, event_type, verified, verification_method,
                       verification_reason, headers_json, payload_hash, resource_hint,
                       actor_hint, status, received_at
                FROM webhook_deliveries
                {where_clause}
                ORDER BY received_at DESC, id DESC
                LIMIT ?
                """,
                values,
            )
            rows = await cursor.fetchall()

        return [
            WebhookDeliveryEnvelope(
                provider=WebhookProvider(row[0]),
                delivery_id=row[1],
                event_type=row[2],
                verified=bool(row[3]),
                verification_method=row[4],
                verification_reason=row[5],
                headers_json=json.loads(row[6]),
                payload_hash=row[7],
                resource_hint=row[8],
                actor_hint=row[9],
                status=row[10],
                received_at=row[11],
            )
            for row in rows
        ]
