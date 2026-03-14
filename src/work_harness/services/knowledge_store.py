from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite
import chromadb
from chromadb.config import Settings as ChromaSettings

from work_harness.domain.models import AnalysisRecord

logger = logging.getLogger("work_harness.services.knowledge_store")


class KnowledgeStore:
    def __init__(self, db_path: Path, chroma_path: Path | None = None) -> None:
        self._db_path = db_path
        self._chroma_path = chroma_path or db_path.parent / f"{db_path.stem}_chroma"
        self._collection = None

    async def initialize(self) -> bool:
        logger.info(
            "Initializing KnowledgeStore: db=%s chroma=%s",
            self._db_path, self._chroma_path,
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._chroma_path.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT UNIQUE NOT NULL,
                    ticket_key TEXT NOT NULL,
                    source TEXT,
                    scope_type TEXT,
                    scope_key TEXT,
                    actor TEXT,
                    canonical_url TEXT,
                    core_issue TEXT,
                    keywords TEXT,
                    summary TEXT,
                    final_summary TEXT,
                    searchable_text TEXT,
                    storeable BOOLEAN DEFAULT 1,
                    jira_search_results TEXT,
                    confluence_search_results TEXT,
                    cross_reference_results TEXT,
                    iterations INTEGER DEFAULT 0,
                    response_language TEXT DEFAULT 'ko',
                    session_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_ka_ticket ON knowledge_analyses(ticket_key);
                CREATE INDEX IF NOT EXISTS idx_ka_created ON knowledge_analyses(created_at);

                CREATE TABLE IF NOT EXISTS knowledge_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    decision_text TEXT NOT NULL,
                    rationale TEXT,
                    confidence_score REAL DEFAULT 0.5,
                    domain TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS knowledge_work_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT NOT NULL,
                    repo_path TEXT,
                    branch_name TEXT,
                    pr_url TEXT,
                    compare_url TEXT,
                    claude_code_output TEXT,
                    changed_files TEXT,
                    pr_requested BOOLEAN DEFAULT 0,
                    pr_created BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await self._ensure_column(db, "knowledge_analyses", "source", "TEXT")
            await self._ensure_column(db, "knowledge_analyses", "scope_type", "TEXT")
            await self._ensure_column(db, "knowledge_analyses", "scope_key", "TEXT")
            await self._ensure_column(db, "knowledge_analyses", "actor", "TEXT")
            await self._ensure_column(db, "knowledge_analyses", "canonical_url", "TEXT")
            await self._ensure_column(db, "knowledge_analyses", "searchable_text", "TEXT")
            await self._ensure_column(
                db,
                "knowledge_analyses",
                "storeable",
                "BOOLEAN DEFAULT 1",
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ka_scope
                ON knowledge_analyses(source, scope_key, created_at)
                """
            )
            await db.commit()
        client = chromadb.PersistentClient(
            path=str(self._chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(name="knowledge_analyses")
        logger.info("KnowledgeStore initialized successfully")
        return True

    async def store_analysis(self, record: AnalysisRecord) -> str:
        logger.debug(
            "Storing analysis: id=%s key=%s source=%s",
            record.analysis_id, record.ticket_key, record.source,
        )
        searchable_text = record.searchable_text or self._default_searchable_text(record)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO knowledge_analyses (
                    analysis_id, ticket_key, source, scope_type, scope_key, actor, canonical_url,
                    core_issue, keywords, summary, final_summary, searchable_text, storeable,
                    jira_search_results, confluence_search_results, cross_reference_results,
                    iterations, response_language, session_id, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
                )
                """,
                (
                    record.analysis_id,
                    record.ticket_key,
                    record.source.value if record.source else None,
                    record.scope_type,
                    record.scope_key,
                    record.actor,
                    record.canonical_url,
                    record.core_issue,
                    json.dumps(record.keywords),
                    record.summary,
                    record.final_summary,
                    searchable_text,
                    int(record.storeable),
                    json.dumps(record.jira_search_results),
                    json.dumps(record.confluence_search_results),
                    json.dumps(record.cross_reference_results),
                    record.iterations,
                    record.response_language,
                    record.session_id,
                ),
            )
            await db.commit()
        if record.storeable and searchable_text:
            self._upsert_vector(record, searchable_text)
        return record.analysis_id

    async def delete_analysis(self, analysis_id: str) -> None:
        logger.info("Deleting analysis: analysis_id=%s", analysis_id)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                DELETE FROM knowledge_analyses
                WHERE analysis_id = ?
                """,
                (analysis_id,),
            )
            await db.commit()
        if self._collection is not None:
            self._collection.delete(ids=[analysis_id])

    async def search_similar(
        self,
        query: str,
        k: int = 5,
        *,
        source: str | None = None,
        scope_key: str | None = None,
    ) -> list[dict]:
        logger.debug(
            "Searching: q=%s source=%s scope=%s k=%d",
            query[:60], source, scope_key, k,
        )
        like_query = f"%{query.lower()}%"
        exact_hits: dict[str, dict[str, Any]] = {}
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT analysis_id, ticket_key, source, scope_type, scope_key, actor,
                       canonical_url, core_issue, summary, final_summary, created_at
                FROM knowledge_analyses
                WHERE storeable = 1
                    AND (? IS NULL OR source = ?)
                    AND (? IS NULL OR scope_key = ?)
                    AND (
                        lower(core_issue) LIKE ?
                        OR lower(summary) LIKE ?
                        OR lower(final_summary) LIKE ?
                        OR lower(searchable_text) LIKE ?
                    )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (
                    source,
                    source,
                    scope_key,
                    scope_key,
                    like_query,
                    like_query,
                    like_query,
                    like_query,
                    k,
                ),
            )
            rows = await cursor.fetchall()
        for row in rows:
            exact_hits[row[0]] = {
                "analysis_id": row[0],
                "ticket_key": row[1],
                "source": row[2],
                "scope_type": row[3],
                "scope_key": row[4],
                "actor": row[5],
                "canonical_url": row[6],
                "core_issue": row[7],
                "summary": row[8],
                "final_summary": row[9],
                "created_at": row[10],
                "match_type": "exact",
                "score": 1.0,
            }
        vector_hits = self._query_vector(query, source=source, scope_key=scope_key, k=k)
        if not vector_hits:
            return list(exact_hits.values())[:k]

        hydrated = await self._fetch_by_analysis_ids(list(vector_hits))
        merged = exact_hits.copy()
        for analysis_id, hit in hydrated.items():
            vector_hit = vector_hits.get(analysis_id, {})
            existing = merged.get(analysis_id)
            score = vector_hit.get("score", 0.0)
            match_type = "exact+vector" if existing else "vector"
            payload = {
                **hit,
                "match_type": match_type,
                "score": max(existing["score"], score) if existing else score,
            }
            if existing:
                payload["score"] = max(existing["score"], score)
            merged[analysis_id] = payload
        return sorted(
            merged.values(),
            key=lambda item: (item.get("score", 0.0), item.get("created_at", "")),
            reverse=True,
        )[:k]

    async def _fetch_by_analysis_ids(
        self,
        analysis_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not analysis_ids:
            return {}
        placeholders = ",".join("?" for _ in analysis_ids)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT analysis_id, ticket_key, source, scope_type, scope_key, actor,
                       canonical_url, core_issue, summary, final_summary, created_at
                FROM knowledge_analyses
                WHERE
                    analysis_id IN ({placeholders})
                """,
                analysis_ids,
            )
            rows = await cursor.fetchall()
        return {
            row[0]: {
                "analysis_id": row[0],
                "ticket_key": row[1],
                "source": row[2],
                "scope_type": row[3],
                "scope_key": row[4],
                "actor": row[5],
                "canonical_url": row[6],
                "core_issue": row[7],
                "summary": row[8],
                "final_summary": row[9],
                "created_at": row[10],
            }
            for row in rows
        }

    async def get_recent(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT analysis_id, ticket_key, source, scope_key, summary,
                       final_summary, created_at
                FROM knowledge_analyses
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [
            {
                "analysis_id": row[0],
                "ticket_key": row[1],
                "source": row[2],
                "scope_key": row[3],
                "summary": row[4],
                "final_summary": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    async def get_stats(self) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            total_cursor = await db.execute(
                "SELECT COUNT(*), AVG(iterations) FROM knowledge_analyses"
            )
            total, avg_iterations = await total_cursor.fetchone()
            month_cursor = await db.execute(
                """
                SELECT strftime('%Y-%m', created_at) AS month, COUNT(*)
                FROM knowledge_analyses
                GROUP BY month
                ORDER BY month DESC
                LIMIT 6
                """
            )
            by_month = await month_cursor.fetchall()
        return {
            "total": total or 0,
            "avg_iterations": float(avg_iterations or 0),
            "by_month": [{"month": row[0], "count": row[1]} for row in by_month],
        }

    async def _ensure_column(
        self,
        db: aiosqlite.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        existing_columns = {row[1] for row in await cursor.fetchall()}
        if column not in existing_columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _upsert_vector(self, record: AnalysisRecord, searchable_text: str) -> None:
        if self._collection is None:
            return
        self._collection.upsert(
            ids=[record.analysis_id],
            documents=[searchable_text],
            embeddings=[self._embed_text(searchable_text)],
            metadatas=[
                {
                    "source": record.source.value if record.source else "",
                    "scope_key": record.scope_key or "",
                    "ticket_key": record.ticket_key,
                    "storeable": bool(record.storeable),
                }
            ],
        )

    def _query_vector(
        self,
        query: str,
        *,
        source: str | None,
        scope_key: str | None,
        k: int,
    ) -> dict[str, dict[str, Any]]:
        if self._collection is None:
            return {}
        if self._collection.count() == 0:
            return {}
        where = self._build_where(source, scope_key)
        result = self._collection.query(
            query_embeddings=[self._embed_text(query)],
            n_results=k,
            where=where,
            include=["distances", "metadatas"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        hits: dict[str, dict[str, Any]] = {}
        for analysis_id, distance in zip(ids, distances, strict=False):
            hits[analysis_id] = {"score": 1 / (1 + float(distance))}
        return hits

    def _build_where(
        self,
        source: str | None,
        scope_key: str | None,
    ) -> dict[str, Any] | None:
        clauses = []
        if source:
            clauses.append({"source": source})
        if scope_key:
            clauses.append({"scope_key": scope_key})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def _default_searchable_text(self, record: AnalysisRecord) -> str:
        return " ".join(
            part
            for part in [
                record.core_issue,
                record.summary,
                record.final_summary,
                " ".join(record.keywords),
            ]
            if part
        )[:2000]

    def _embed_text(self, text: str, dimensions: int = 96) -> list[float]:
        vector = [0.0] * dimensions
        for token in text.lower().split():
            slot = int(hashlib.sha256(token.encode()).hexdigest(), 16) % dimensions
            vector[slot] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]
