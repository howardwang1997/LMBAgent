"""Experiment design metadata schema.

Defines the structured metadata for battery experiment design factors,
loaded from YAML files alongside cycling data.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class ElectrodeDesign(BaseModel):
    thickness_um: Optional[float] = None
    porosity: Optional[float] = None
    particle_radius_um: Optional[float] = None
    active_material: Optional[str] = None
    loading_mg_cm2: Optional[float] = None
    conductivity_s_m: Optional[float] = None
    np_ratio: Optional[float] = None
    type: Optional[str] = None


class ElectrolyteDesign(BaseModel):
    salt: Optional[str] = None
    concentration_mol_l: Optional[float] = None
    solvent: Optional[str] = None
    additives: Optional[str] = None
    volume_ml: Optional[float] = None


class SeparatorDesign(BaseModel):
    type: Optional[str] = None
    thickness_um: Optional[float] = None


class FormationProtocol(BaseModel):
    c_rates: Optional[list[float]] = None
    temperature_c: Optional[float] = None
    cycles: Optional[int] = None
    voltage_range: Optional[tuple[float, float]] = None
    rest_time_s: Optional[float] = None


class TestConditions(BaseModel):
    c_rates: Optional[list[float]] = None
    temperature_c: Optional[float] = None
    num_cycles: Optional[int] = None
    protocol: Optional[str] = None
    cv_cutoff_current_a: Optional[float] = None


class ExperimentDesign(BaseModel):
    """Structured metadata for a battery experiment's design factors."""

    cell_id: str
    chemistry: str
    form_factor: Optional[str] = None
    design_capacity_ah: Optional[float] = None
    voltage_range: Optional[tuple[float, float]] = None

    positive_electrode: ElectrodeDesign = Field(default_factory=ElectrodeDesign)
    negative_electrode: ElectrodeDesign = Field(default_factory=ElectrodeDesign)
    electrolyte: ElectrolyteDesign = Field(default_factory=ElectrolyteDesign)
    separator: SeparatorDesign = Field(default_factory=SeparatorDesign)

    formation: FormationProtocol = Field(default_factory=FormationProtocol)
    test: TestConditions = Field(default_factory=TestConditions)

    notes: Optional[str] = None
    experimenter: Optional[str] = None
    date: Optional[date_type] = None

    custom: dict[str, Any] = Field(default_factory=dict)

    def to_flat_dict(self) -> dict[str, Any]:
        """Flatten nested fields to a single-level dict for comparison/tabulation.

        Keys use dot notation, e.g. 'positive_electrode.thickness_um'.
        """
        flat: dict[str, Any] = {}
        flat["cell_id"] = self.cell_id
        flat["chemistry"] = self.chemistry
        flat["form_factor"] = self.form_factor
        flat["design_capacity_ah"] = self.design_capacity_ah
        flat["voltage_range"] = self.voltage_range

        for section_name in (
            "positive_electrode",
            "negative_electrode",
            "electrolyte",
            "separator",
            "formation",
            "test",
        ):
            section = getattr(self, section_name)
            if section is None:
                continue
            for field_name, value in section.model_dump().items():
                if value is not None:
                    flat[f"{section_name}.{field_name}"] = value

        if self.custom:
            flat.update(self.custom)

        return flat

    def diff(self, other: ExperimentDesign) -> dict[str, tuple[Any, Any]]:
        """Compare two designs and return fields that differ.

        Returns:
            Dict mapping field name -> (self_value, other_value) for differing fields.
        """
        self_flat = self.to_flat_dict()
        other_flat = other.to_flat_dict()
        all_keys = set(self_flat) | set(other_flat)
        diffs: dict[str, tuple[Any, Any]] = {}
        for k in sorted(all_keys):
            v1 = self_flat.get(k)
            v2 = other_flat.get(k)
            if v1 != v2:
                diffs[k] = (v1, v2)
        return diffs


def load_experiment_design(yaml_path: str) -> ExperimentDesign:
    """Load an ExperimentDesign from a YAML file."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return ExperimentDesign(**data)


def find_design_file(data_path: str) -> str | None:
    """Find a design YAML file matching a data file.

    Looks for: <base>_design.yaml, <base>.design.yaml in the same directory.
    """
    from pathlib import Path

    p = Path(data_path)
    candidates = [
        p.with_name(p.stem + "_design.yaml"),
        p.with_name(p.stem + "_design.yml"),
        p.with_name(p.stem + ".design.yaml"),
        p.with_name(p.stem + ".design.yml"),
        p.with_suffix(".yaml"),
        p.with_suffix(".yml"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None
