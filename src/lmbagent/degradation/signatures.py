"""Degradation signature matrix for mode decomposition.

Defines 7 canonical degradation modes and their expected voltage signatures.
Two modes of operation:
1. Model-based: signatures computed from simulation (autobattery FNO/PINN).
2. Rule-based: approximate signatures derived from physical knowledge.

The rule-based approach uses normalized discharge time as the x-axis
and describes each mode's characteristic ΔV shape.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


DEGRADATION_MODES = [
    "SEI_growth",
    "lithium_plating",
    "LAM_positive",
    "LAM_negative",
    "resistance_growth",
    "diffusion_degradation",
    "electrolyte_depletion",
]

MODE_DESCRIPTIONS = {
    "SEI_growth": "SEI layer thickening — increases impedance, reduces cyclable lithium",
    "lithium_plating": "Lithium metal plating on anode — capacity loss, safety risk",
    "LAM_positive": "Loss of active material (positive electrode) — capacity fade",
    "LAM_negative": "Loss of active material (negative electrode) — capacity fade",
    "resistance_growth": "Ohmic resistance increase — polarization, voltage drop",
    "diffusion_degradation": "Diffusion coefficient degradation — kinetic limitation at high rates",
    "electrolyte_depletion": "Electrolyte consumption/drying — transport limitation",
}


def _make_rule_based_signatures(n_points: int = 100) -> np.ndarray:
    """Generate approximate degradation signatures based on physical intuition.

    Each signature describes how ΔV(t) looks when only that mode is active,
    over a normalized discharge time [0, 1].

    Returns:
        signatures: shape (7, n_points)
    """
    t = np.linspace(0, 1, n_points)

    sigs = np.zeros((7, n_points))

    # SEI growth: gradual voltage shift, strongest at end of discharge
    sigs[0] = t ** 1.5 * 0.05

    # Li plating: early-discharge voltage depression (low overpotential region)
    sigs[1] = np.exp(-((t - 0.15) ** 2) / (2 * 0.08 ** 2)) * 0.03

    # LAM positive: uniform capacity loss → voltage drops uniformly, slightly more at end
    sigs[2] = (0.3 + 0.7 * t) * 0.04

    # LAM negative: voltage drop concentrated in mid-to-end discharge
    sigs[3] = t ** 2 * 0.03

    # Resistance growth: uniform voltage offset (IR drop)
    sigs[4] = np.ones(n_points) * 0.04

    # Diffusion degradation: end-of-discharge voltage roll-off
    sigs[5] = t ** 3 * 0.06

    # Electrolyte depletion: mid-discharge voltage sag
    sigs[6] = np.exp(-((t - 0.5) ** 2) / (2 * 0.15 ** 2)) * 0.035

    return sigs


@dataclass
class SignatureMatrix:
    """Container for degradation signature matrix."""

    signatures: np.ndarray
    mode_names: list[str]
    n_points: int
    method: str

    @property
    def n_modes(self) -> int:
        return len(self.mode_names)


def load_signatures(
    method: str = "rule_based",
    n_points: int = 100,
    model_path: str | None = None,
) -> SignatureMatrix:
    """Load or compute degradation signature matrix.

    Args:
        method: 'rule_based' for approximate physics-based signatures,
                'model' for simulation-derived signatures.
        n_points: Number of time points for signature discretization.
        model_path: Path to saved signature file (for 'model' method).

    Returns:
        SignatureMatrix with signatures shape (n_modes, n_points).
    """
    if method == "rule_based":
        sigs = _make_rule_based_signatures(n_points)
        return SignatureMatrix(
            signatures=sigs,
            mode_names=list(DEGRADATION_MODES),
            n_points=n_points,
            method=method,
        )

    if method == "model":
        if model_path is None:
            raise ValueError("model_path required for method='model'")
        data = np.load(model_path)
        sigs = data["signatures"]
        names = list(data.get("mode_names", DEGRADATION_MODES))
        return SignatureMatrix(
            signatures=sigs,
            mode_names=names,
            n_points=sigs.shape[1],
            method=method,
        )

    raise ValueError(f"Unknown method '{method}'. Use 'rule_based' or 'model'.")
