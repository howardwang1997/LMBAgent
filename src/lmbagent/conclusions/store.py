"""Conclusion CRUD operations using the existing SQLite 'conclusions' table."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from lmbagent.conclusions.models import Conclusion, ConclusionStatus
from lmbagent.data.store import DataStore


class ConclusionStore:
    """CRUD for conclusions, backed by the shared SQLite database."""

    _instance: ConclusionStore | None = None

    def __new__(cls, store: DataStore | None = None) -> ConclusionStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, store: DataStore | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._store = store or DataStore()
        self._conn: sqlite3.Connection = self._store._conn

    def add(self, conclusion: Conclusion) -> None:
        """Insert a new conclusion."""
        self._conn.execute(
            """INSERT OR REPLACE INTO conclusions
               (conclusion_id, statement, scope, evidence_ids_json,
                confidence, status, created_at, updated_at, challenged_by_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                conclusion.conclusion_id,
                conclusion.statement,
                conclusion.scope,
                json.dumps(conclusion.evidence_ids),
                conclusion.confidence,
                conclusion.status.value,
                conclusion.created_at,
                conclusion.updated_at,
                json.dumps(conclusion.challenged_by),
            ),
        )
        self._conn.commit()

    def get(self, conclusion_id: str) -> Conclusion | None:
        """Get a conclusion by ID."""
        row = self._conn.execute(
            "SELECT * FROM conclusions WHERE conclusion_id = ?",
            (conclusion_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_conclusion(row)

    def list_all(self, status: str | None = None) -> list[Conclusion]:
        """List all conclusions, optionally filtered by status."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM conclusions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM conclusions ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_conclusion(r) for r in rows]

    def update(
        self,
        conclusion_id: str,
        statement: str | None = None,
        status: str | None = None,
        confidence: str | None = None,
        evidence_ids: list[str] | None = None,
        challenged_by: list[str] | None = None,
        notes: str | None = None,
    ) -> Conclusion | None:
        """Update a conclusion's fields."""
        c = self.get(conclusion_id)
        if c is None:
            return None

        if statement is not None:
            c.statement = statement
        if status is not None:
            c.status = ConclusionStatus(status)
        if confidence is not None:
            c.confidence = confidence
        if evidence_ids is not None:
            c.evidence_ids = evidence_ids
        if challenged_by is not None:
            c.challenged_by = challenged_by

        c.updated_at = datetime.now().isoformat()
        self.add(c)
        return c

    def remove(self, conclusion_id: str) -> bool:
        """Delete a conclusion."""
        cursor = self._conn.execute(
            "DELETE FROM conclusions WHERE conclusion_id = ?",
            (conclusion_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_conclusion(self, row: sqlite3.Row) -> Conclusion:
        return Conclusion(
            conclusion_id=row["conclusion_id"],
            statement=row["statement"],
            scope=row["scope"] or "",
            evidence_ids=json.loads(row["evidence_ids_json"]) if row["evidence_ids_json"] else [],
            confidence=row["confidence"] or "medium",
            status=ConclusionStatus(row["status"]) if row["status"] else ConclusionStatus.ACTIVE,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            challenged_by=json.loads(row["challenged_by_json"]) if row["challenged_by_json"] else [],
        )

    @classmethod
    def reset(cls) -> None:
        cls._instance = None
