"""Persistent data store for battery datasets.

SQLite-backed store that replaces the original in-memory DataStore.
Maintains the same interface (put/get/list_ids/remove/clear) plus
persistence across sessions.

Tables:
  - experiments: metadata + design factors
  - cycle_summaries: per-cycle aggregated metrics
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from lmbagent.data.models import BatteryDataset


_DEFAULT_DB_PATH = Path.home() / ".lmbagent" / "lmbagent.db"


class DataStore:
    """Persistent store backed by SQLite.

    Keeps an in-memory cache of full BatteryDataset objects (with raw_data DataFrames)
    for fast access during a session, while persisting metadata and cycle summaries
    to SQLite for cross-session durability.
    """

    _instance: DataStore | None = None

    def __new__(cls, db_path: str | Path | None = None) -> DataStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | Path | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._cache: dict[str, BatteryDataset] = {}

        if db_path is None:
            db_path = _DEFAULT_DB_PATH
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

        self._load_cache_from_db()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                data_id TEXT PRIMARY KEY,
                cell_id TEXT,
                chemistry TEXT,
                test_name TEXT,
                source_file TEXT NOT NULL,
                start_datetime TEXT,
                design_json TEXT,
                metadata_json TEXT,
                loaded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cycle_summaries (
                data_id TEXT NOT NULL,
                cycle_index INTEGER NOT NULL,
                charge_capacity REAL,
                discharge_capacity REAL,
                coulombic_efficiency REAL,
                charge_energy REAL,
                discharge_energy REAL,
                energy_efficiency REAL,
                ir_charge REAL,
                ir_discharge REAL,
                capacity_retention REAL,
                end_voltage_charge REAL,
                end_voltage_discharge REAL,
                PRIMARY KEY (data_id, cycle_index),
                FOREIGN KEY (data_id) REFERENCES experiments(data_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS failure_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_id TEXT NOT NULL,
                method TEXT NOT NULL,
                modes_json TEXT,
                summary_text TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (data_id) REFERENCES experiments(data_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS conclusions (
                conclusion_id TEXT PRIMARY KEY,
                statement TEXT NOT NULL,
                scope TEXT,
                evidence_ids_json TEXT,
                confidence TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                challenged_by_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_experiments_chemistry
                ON experiments(chemistry);
            CREATE INDEX IF NOT EXISTS idx_experiments_cell_id
                ON experiments(cell_id);
        """)
        self._conn.commit()

    def _load_cache_from_db(self) -> None:
        """Load lightweight metadata into cache (without raw_data)."""
        rows = self._conn.execute(
            "SELECT data_id, cell_id, chemistry, test_name, source_file, "
            "start_datetime, design_json, metadata_json FROM experiments"
        ).fetchall()
        for row in rows:
            design = None
            if row["design_json"]:
                from lmbagent.data.schema import ExperimentDesign
                design = ExperimentDesign.model_validate_json(row["design_json"])
            meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            ds = BatteryDataset(
                data_id=row["data_id"],
                source_file=row["source_file"],
                cell_id=row["cell_id"],
                test_name=row["test_name"],
                start_datetime=row["start_datetime"]
                if row["start_datetime"]
                else None,
                metadata=meta,
                experiment_design=design,
            )
            cs_rows = self._conn.execute(
                "SELECT * FROM cycle_summaries WHERE data_id = ? ORDER BY cycle_index",
                (row["data_id"],),
            ).fetchall()
            if cs_rows:
                ds.cycle_summary = pd.DataFrame(
                    [dict(r) for r in cs_rows]
                ).drop(columns=["data_id"])
            self._cache[ds.data_id] = ds

    def put(self, dataset: BatteryDataset) -> None:
        """Insert or update a dataset in both cache and SQLite."""
        data_id = dataset.data_id
        self._cache[data_id] = dataset

        design_json = (
            dataset.experiment_design.model_dump_json()
            if dataset.experiment_design
            else None
        )
        meta_json = json.dumps(dataset.metadata) if dataset.metadata else None

        self._conn.execute(
            """INSERT OR REPLACE INTO experiments
               (data_id, cell_id, chemistry, test_name, source_file,
                start_datetime, design_json, metadata_json, loaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data_id,
                dataset.cell_id,
                dataset.chemistry,
                dataset.test_name,
                dataset.source_file,
                str(dataset.start_datetime) if dataset.start_datetime else None,
                design_json,
                meta_json,
                datetime.now().isoformat(),
            ),
        )

        self._conn.execute(
            "DELETE FROM cycle_summaries WHERE data_id = ?", (data_id,)
        )
        if not dataset.cycle_summary.empty:
            rows = []
            for _, row in dataset.cycle_summary.iterrows():
                r = {"data_id": data_id}
                for col in (
                    "cycle_index",
                    "charge_capacity",
                    "discharge_capacity",
                    "coulombic_efficiency",
                    "charge_energy",
                    "discharge_energy",
                    "energy_efficiency",
                    "ir_charge",
                    "ir_discharge",
                    "capacity_retention",
                    "end_voltage_charge",
                    "end_voltage_discharge",
                ):
                    r[col] = row.get(col)
                rows.append(r)
            self._conn.executemany(
                """INSERT INTO cycle_summaries
                   (data_id, cycle_index, charge_capacity, discharge_capacity,
                    coulombic_efficiency, charge_energy, discharge_energy,
                    energy_efficiency, ir_charge, ir_discharge,
                    capacity_retention, end_voltage_charge, end_voltage_discharge)
                   VALUES (:data_id, :cycle_index, :charge_capacity, :discharge_capacity,
                    :coulombic_efficiency, :charge_energy, :discharge_energy,
                    :energy_efficiency, :ir_charge, :ir_discharge,
                    :capacity_retention, :end_voltage_charge, :end_voltage_discharge)""",
                rows,
            )

        self._conn.commit()

    def get(self, data_id: str) -> BatteryDataset | None:
        return self._cache.get(data_id)

    def list_ids(self) -> list[str]:
        return list(self._cache.keys())

    def remove(self, data_id: str) -> bool:
        if data_id not in self._cache:
            return False
        del self._cache[data_id]
        self._conn.execute("DELETE FROM experiments WHERE data_id = ?", (data_id,))
        self._conn.commit()
        return True

    def clear(self) -> None:
        self._cache.clear()
        self._conn.executescript(
            "DELETE FROM cycle_summaries; DELETE FROM experiments; "
            "DELETE FROM failure_analyses;"
        )
        self._conn.commit()

    def query(
        self,
        chemistry: str | None = None,
        cell_id: str | None = None,
    ) -> list[BatteryDataset]:
        """Query experiments by metadata filters."""
        results = list(self._cache.values())
        if chemistry:
            results = [
                ds for ds in results if ds.chemistry and chemistry in ds.chemistry
            ]
        if cell_id:
            results = [ds for ds in results if ds.cell_id == cell_id]
        return results

    def list_as_table(self) -> pd.DataFrame:
        """Return a summary table of all experiments."""
        if not self._cache:
            return pd.DataFrame()
        rows = []
        for ds in self._cache.values():
            row: dict[str, Any] = {
                "data_id": ds.data_id,
                "cell_id": ds.cell_id,
                "chemistry": ds.chemistry,
                "test_name": ds.test_name,
                "source_file": ds.source_file,
                "cycles": ds.num_cycles,
            }
            if ds.experiment_design:
                flat = ds.experiment_design.to_flat_dict()
                for k, v in flat.items():
                    if k not in row:
                        row[f"design.{k}"] = v
            rows.append(row)
        return pd.DataFrame(rows)

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        if cls._instance is not None:
            try:
                cls._instance._conn.close()
            except Exception:
                pass
        cls._instance = None
