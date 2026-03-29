"""Report API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.app.models import ReportRequest, ReportResponse
from api.app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])
service = ReportService()


@router.post("", response_model=ReportResponse)
async def generate_report(request: ReportRequest):
    """Generate a report for the specified dataset."""
    try:
        result = service.generate(
            data_id=request.dataset_id,
            output_format=request.format,
            analysis_notes=request.analysis_notes,
        )
        return ReportResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{data_id}/{format}")
async def download_report(data_id: str, format: str):
    """Download a generated report."""
    try:
        report_path = service.get_report_path(data_id, format)

        # Determine media type
        media_type = {
            "pdf": "application/pdf",
            "html": "text/html",
            "markdown": "text/markdown",
        }.get(format, "text/plain")

        return FileResponse(
            report_path,
            media_type=media_type,
            filename=report_path.name,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
