from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from work_harness.domain.models import AnalysisRecord


class KnowledgeStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> bool:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id TEXT UNIQUE NOT NULL,
                    ticket_key TEXT NOT NULL,
                    core_issue TEXT,
                    keywords TEXT,
                    summary TEXT,
                    final_summary TEXT,
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
            await db.commit()
        return True

    async def store_analysis(self, record: AnalysisRecord) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO knowledge_analyses (
                    analysis_id, ticket_key, core_issue, keywords, summary, final_summary,
                    jira_search_results, confluence_search_results, cross_reference_results,
                    iterations, response_language, session_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    record.analysis_id,
                    record.ticket_key,
                    record.core_issue,
                    json.dumps(record.keywords),
                    record.summary,
                    record.final_summary,
                    json.dumps(record.jira_search_results),
                    json.dumps(record.confluence_search_results),
                    json.dumps(record.cross_reference_results),
                    record.iterations,
                    record.response_language,
                    record.session_id,
                ),
            )
            await db.commit()
        return record.analysis_id

    async def search_similar(self, query: str, k: int = 5) -> list[dict]:
        like_query = f"%{query.lower()}%"
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT analysis_id, ticket_key, core_issue, summary, final_summary
                FROM knowledge_analyses
                WHERE
                    lower(core_issue) LIKE ?
                    OR lower(summary) LIKE ?
                    OR lower(final_summary) LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (like_query, like_query, like_query, k),
            )
            rows = await cursor.fetchall()
        return [
            {
                "analysis_id": row[0],
                "ticket_key": row[1],
                "core_issue": row[2],
                "summary": row[3],
                "final_summary": row[4],
            }
            for row in rows
        ]

    async def get_recent(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                SELECT analysis_id, ticket_key, summary, final_summary, created_at
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
                "summary": row[2],
                "final_summary": row[3],
                "created_at": row[4],
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
