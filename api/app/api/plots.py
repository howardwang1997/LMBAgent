"""Plot API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.app.models import PlotResponse
from api.app.services.plot_service import PlotService

router = APIRouter(prefix="/plots", tags=["plots"])
service = PlotService()


@router.get("/{data_id}/{plot_type}", response_model=PlotResponse)
async def get_plot(
    data_id: str,
    plot_type: str,
    normalize: bool = Query(False, description="Normalize capacity to first cycle"),
    cycles: str | None = Query(None, description="Comma-separated cycle numbers for voltage curves"),
    y_range: str | None = Query(None, description="Y-axis range as 'min-max'"),
):
    """Generate a plot for the specified dataset."""
    try:
        kwargs = {"normalize": normalize}
        if cycles:
            kwargs["cycles"] = [int(c.strip()) for c in cycles.split(",")]
        if y_range:
            kwargs["y_range"] = y_range

        result = service.generate_plot(data_id, plot_type, **kwargs)
        return PlotResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{data_id}")
async def list_plots(data_id: str):
    """List all available plots for a dataset."""
    try:
        return service.list_plots(data_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
