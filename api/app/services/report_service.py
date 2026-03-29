"""Report service: generates analysis reports."""

from __future__ import annotations

from pathlib import Path

from lmbagent.data.store import DataStore
from lmbagent.output import get_output_dir
from lmbagent.report.generator import generate_report


class ReportService:
    """Service for generating battery analysis reports."""

    SUPPORTED_FORMATS = ["markdown", "html", "pdf"]

    def __init__(self):
        self._store = DataStore()

    def generate(
        self, data_id: str, output_format: str = "markdown", analysis_notes: str | None = None
    ) -> dict:
        """Generate a report for the specified dataset."""
        if output_format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {output_format}")

        dataset = self._store.get(data_id)
        if dataset is None:
            raise ValueError(f"Dataset {data_id} not found")

        output_dir = get_output_dir(data_id)

        report_path = generate_report(
            dataset,
            output_format=output_format,
            output_dir=output_dir,
            analysis_notes=analysis_notes,
        )

        return {
            "report_path": str(report_path),
            "format": output_format,
            "download_url": f"/api/reports/download/{data_id}/{output_format}",
        }

    def get_report_path(self, data_id: str, output_format: str) -> Path:
        """Get the path to an existing report."""
        dataset = self._store.get(data_id)
        if dataset is None:
            raise ValueError(f"Dataset {data_id} not found")

        output_dir = get_output_dir(data_id)
        report_path = output_dir / f"report_{data_id}.{output_format}"

        if not report_path.exists():
            raise FileNotFoundError(f"Report not found: {report_path}")

        return report_path
