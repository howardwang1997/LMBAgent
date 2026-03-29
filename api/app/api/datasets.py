"""Dataset API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.app.models import DatasetDetail, DatasetSummary, UploadResponse
from api.app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])
service = DatasetService()


@router.get("", response_model=list[DatasetSummary])
async def list_datasets():
    """List all available datasets."""
    return service.list_datasets()


@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    data_id: str | None = None,
):
    """Upload a CSV file and load it as a dataset."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()

    try:
        result = service.load_from_upload(content, file.filename, data_id)
        return UploadResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{data_id}", response_model=DatasetDetail)
async def get_dataset(data_id: str):
    """Get detailed information about a specific dataset."""
    try:
        return service.get_dataset(data_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{data_id}")
async def delete_dataset(data_id: str):
    """Delete a dataset."""
    service.delete_dataset(data_id)
    return {"message": f"Dataset {data_id} deleted"}
