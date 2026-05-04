"""Data models for experimental conclusions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConclusionStatus(str, Enum):
    ACTIVE = "active"
    SUPPORTED = "supported"
    CHALLENGED = "challenged"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class Conclusion(BaseModel):
    """A scientific conclusion drawn from experimental data."""

    conclusion_id: str
    statement: str
    scope: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    status: ConclusionStatus = ConclusionStatus.ACTIVE
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    challenged_by: list[str] = Field(default_factory=list)
    notes: str = ""
    tags: list[str] = Field(default_factory=list)

    def to_flat_dict(self) -> dict[str, Any]:
        return {
            "conclusion_id": self.conclusion_id,
            "statement": self.statement,
            "scope": self.scope,
            "evidence_ids": ",".join(self.evidence_ids),
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at,
            "tags": ",".join(self.tags),
        }
