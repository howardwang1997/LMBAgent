"""API client for communicating with FastAPI backend."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import requests


API_BASE = "http://localhost:8000/api"


def list_datasets() -> list[dict]:
    """List all available datasets."""
    r = requests.get(f"{API_BASE}/datasets")
    r.raise_for_status()
    return r.json()


def upload_dataset(file, data_id: str | None = None) -> dict:
    """Upload a CSV file as a new dataset."""
    files = {"file": file}
    params = {}
    if data_id:
        params["data_id"] = data_id

    r = requests.post(f"{API_BASE}/datasets/upload", files=files, params=params)
    r.raise_for_status()
    return r.json()


def get_dataset(data_id: str) -> dict:
    """Get detailed information about a dataset."""
    r = requests.get(f"{API_BASE}/datasets/{data_id}")
    r.raise_for_status()
    return r.json()


def delete_dataset(data_id: str) -> None:
    """Delete a dataset."""
    r = requests.delete(f"{API_BASE}/datasets/{data_id}")
    r.raise_for_status()


def get_plot(data_id: str, plot_type: str, **params) -> dict:
    """Generate a plot for a dataset."""
    r = requests.get(f"{API_BASE}/plots/{data_id}/{plot_type}", params=params)
    r.raise_for_status()
    return r.json()


def list_plots(data_id: str) -> list[dict]:
    """List all available plots for a dataset."""
    r = requests.get(f"{API_BASE}/plots/{data_id}")
    r.raise_for_status()
    return r.json()


def generate_report(data_id: str, format: str, analysis_notes: str | None = None) -> dict:
    """Generate a report for a dataset."""
    payload = {"dataset_id": data_id, "format": format}
    if analysis_notes:
        payload["analysis_notes"] = analysis_notes

    r = requests.post(f"{API_BASE}/reports", json=payload)
    r.raise_for_status()
    return r.json()


def download_report(data_id: str, format: str) -> bytes:
    """Download a generated report."""
    r = requests.get(f"{API_BASE}/reports/download/{data_id}/{format}")
    r.raise_for_status()
    return r.content


def decode_base64_image(base64_str: str) -> BytesIO:
    """Convert base64 string to BytesIO object for Streamlit."""
    image_data = base64.b64decode(base64_str)
    return BytesIO(image_data)


def chat_message(message: str, dataset_id: str | None = None, model: str = "grok-4-1-fast-reasoning") -> dict:
    """Send a chat message (non-streaming)."""
    payload = {
        "message": message,
        "dataset_id": dataset_id,
        "model": model,
    }
    r = requests.post(f"{API_BASE}/chat/message", json=payload)
    r.raise_for_status()
    return r.json()


def chat_stream_iter(message: str, dataset_id: str | None = None, model: str = "grok-4-1-fast-reasoning"):
    """Iterate over chat stream responses."""
    params = {
        "message": message,
        "model": model,
    }
    if dataset_id:
        params["dataset_id"] = dataset_id

    r = requests.get(
        f"{API_BASE}/chat/stream",
        params=params,
        stream=True,
    )
    r.raise_for_status()

    for line in r.iter_lines():
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                import json
                try:
                    yield json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
