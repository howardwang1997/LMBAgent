"""FastAPI backend for LMBAgent web frontend."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.api import datasets, plots, reports, chat, settings

app = FastAPI(
    title="LMBAgent API",
    description="Lithium Metal Battery Data Analysis API",
    version="0.1.0",
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(datasets.router, prefix="/api")
app.include_router(plots.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


@app.on_event("startup")
def load_demo_data():
    from api.app.services.dataset_service import DatasetService
    svc = DatasetService()
    examples_dir = Path(__file__).parent.parent.parent / "data" / "examples"
    for filename, data_id in [("pec.csv", "pec"), ("pec_100cycles.csv", "lmb100")]:
        csv_path = examples_dir / filename
        if csv_path.exists():
            try:
                svc.load_from_file(str(csv_path), data_id=data_id)
            except Exception:
                pass


@app.get("/")
async def root():
    return {"message": "LMBAgent API", "docs": "/docs", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
