"""Pydantic models for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class DatasetSummary(BaseModel):
    """Summary of a dataset for list views."""

    data_id: str
    source_file: str
    test_name: Optional[str] = None
    num_cycles: int
    num_data_points: int
    voltage_min: float
    voltage_max: float
    current_min: float
    current_max: float
    created_at: Optional[str] = None


class DatasetDetail(DatasetSummary):
    """Full dataset details including cycle summary and insights."""

    cycle_summary: list[dict]
    insights: dict


class UploadResponse(BaseModel):
    """Response after file upload."""

    data_id: str
    test_name: Optional[str] = None
    metadata: dict
    num_data_points: int
    message: str


class PlotRequest(BaseModel):
    """Request for plot generation."""

    normalize: bool = False
    cycles: Optional[str] = None  # comma-separated for voltage curves
    y_range: Optional[str] = None  # "min-max" format


class PlotResponse(BaseModel):
    """Response with base64-encoded plot image."""

    image: str  # base64 encoded PNG
    plot_type: str
    data_id: str


class ReportRequest(BaseModel):
    """Request for report generation."""

    dataset_id: str
    format: str = Field(default="markdown", pattern="^(markdown|html|pdf)$")
    analysis_notes: Optional[str] = None
    include_plots: bool = True


class ReportResponse(BaseModel):
    """Response after report generation."""

    report_path: str
    format: str
    download_url: str


class ChatRequest(BaseModel):
    """Request for LLM chat."""

    message: str
    dataset_id: Optional[str] = None
    model: str = "grok-4-1-fast-reasoning"


class ChatChunk(BaseModel):
    """Single chunk in SSE stream."""

    type: str  # "content", "tool", "tool_result", "done", "error"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    error: Optional[str] = None
