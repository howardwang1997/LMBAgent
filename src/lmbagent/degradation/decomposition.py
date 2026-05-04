"""NNLS degradation mode decomposition.

Decomposes observed ΔV(t) into a linear combination of degradation mode
signatures using non-negative least squares (NNLS), following the method
from autobattery scripts/28_degradation_modes.py.

Pipeline:
  1. Extract discharge curves per cycle
  2. Compute reference curve V_ref (average of first few cycles)
  3. Compute ΔV(t) = V_cycle(t) - V_ref(t) for each cycle
  4. Interpolate ΔV onto the same grid as signatures
  5. Solve: ΔV ≈ Σ_j c_j * signature_j via NNLS
  6. Track c_j evolution across cycles → degradation mode attribution
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import nnls

from lmbagent.data.models import BatteryDataset
from lmbagent.degradation.features import extract_discharge_curves
from lmbagent.degradation.signatures import (
    DEGRADATION_MODES,
    MODE_DESCRIPTIONS,
    SignatureMatrix,
    load_signatures,
)
from lmbagent.visualization.styles import apply_style


def _interpolate_to_grid(voltage: np.ndarray, n_points: int) -> np.ndarray:
    """Interpolate a voltage curve onto a uniform grid of n_points."""
    return np.interp(
        np.linspace(0, 1, n_points),
        np.linspace(0, 1, len(voltage)),
        voltage,
    )


def decompose_degradation_modes(
    dataset: BatteryDataset,
    signatures: SignatureMatrix | None = None,
    ref_cycles: int = 3,
    smooth_sigma: float = 3.0,
) -> dict:
    """Decompose degradation modes from cycling data.

    Args:
        dataset: BatteryDataset with raw_data.
        signatures: SignatureMatrix (uses rule-based if None).
        ref_cycles: Number of initial cycles to average for reference curve.
        smooth_sigma: Gaussian smoothing width for ΔV.

    Returns:
        Dict with:
          'cycles': list of cycle numbers
          'capacities': list of discharge capacities
          'coefficients': np.ndarray shape (n_cycles, n_modes)
          'rmse_mV': list of fit RMSE per cycle
          'mode_names': list of mode names
          'mode_contributions': dict mode_name -> total absolute weight
          'dominant_mode': str
          'reference_cycle_range': tuple
    """
    if signatures is None:
        signatures = load_signatures("rule_based")

    curves = extract_discharge_curves(dataset)
    if len(curves) < ref_cycles + 1:
        return {
            "error": f"Need at least {ref_cycles + 1} discharge curves, got {len(curves)}",
            "cycles": [], "capacities": [], "coefficients": np.array([]),
            "rmse_mV": [], "mode_names": signatures.mode_names,
            "mode_contributions": {}, "dominant_mode": None,
            "reference_cycle_range": (0, 0),
        }

    n_points = signatures.n_points

    v_refs = []
    for cc in curves[:ref_cycles]:
        v_refs.append(_interpolate_to_grid(cc["voltage"], n_points))
    V_ref = np.mean(v_refs, axis=0)

    A = signatures.signatures.T  # (n_points, n_modes)
    n_sigs = signatures.n_modes

    results = []
    for cc in curves:
        v_exp = _interpolate_to_grid(cc["voltage"], n_points)
        dV = v_exp - V_ref
        dV_smooth = gaussian_filter1d(dV, sigma=smooth_sigma)

        A_aug = np.vstack([A, np.eye(n_sigs) * 0.01])
        b_aug = np.concatenate([dV_smooth, np.zeros(n_sigs)])

        coeffs, _ = nnls(A_aug, b_aug)
        c_net = coeffs[:n_sigs]

        dV_recon = A @ c_net
        rmse = np.sqrt(np.mean((dV_recon - dV_smooth) ** 2)) * 1000

        results.append({
            "cycle": cc["cycle"],
            "capacity": cc["capacity"].max() if len(cc["capacity"]) > 0 else 0,
            "coeffs": c_net,
            "rmse_mV": rmse,
        })

    cycles = [r["cycle"] for r in results]
    capacities = [r["capacity"] for r in results]
    coeff_matrix = np.array([r["coeffs"] for r in results])
    rmses = [r["rmse_mV"] for r in results]

    abs_coeffs = np.abs(coeff_matrix)
    total_activity = abs_coeffs.sum(axis=0)
    total_sum = total_activity.sum() + 1e-12
    contributions = {
        name: float(total_activity[j] / total_sum * 100)
        for j, name in enumerate(signatures.mode_names)
    }
    dominant_idx = int(np.argmax(total_activity))

    return {
        "cycles": cycles,
        "capacities": capacities,
        "coefficients": coeff_matrix,
        "rmse_mV": rmses,
        "mode_names": signatures.mode_names,
        "mode_contributions": contributions,
        "dominant_mode": signatures.mode_names[dominant_idx],
        "reference_cycle_range": (curves[0]["cycle"], curves[ref_cycles - 1]["cycle"]),
    }


def plot_decomposition(
    result: dict,
    output_path: str | Path | None = None,
) -> str:
    """Plot degradation mode decomposition results.

    Generates a figure with:
    - Top-left: capacity fade
    - Other panels: each mode coefficient vs cycle
    - Annotations: correlation with capacity fade, dominant mode
    """
    if "error" in result:
        return result["error"]

    apply_style()
    mode_names = result["mode_names"]
    n_modes = len(mode_names)
    cycles = np.array(result["cycles"])
    caps = np.array(result["capacities"])
    coeffs = result["coefficients"]

    n_cols = min(4, n_modes + 1)
    n_rows = (n_modes + n_cols) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 3.5 * n_rows))
    if n_rows == 1:
        axes = [axes]
    axes_flat = [ax for row in axes for ax in (row if hasattr(row, '__iter__') else [row])]

    ax = axes_flat[0]
    ax.plot(cycles, caps * 1000, "b-", linewidth=1.5)
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity (mAh)")
    ax.set_title("Capacity Fade")
    ax.grid(True, alpha=0.3)

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]
    for j in range(min(n_modes, len(axes_flat) - 1)):
        ax = axes_flat[j + 1]
        c_smooth = gaussian_filter1d(coeffs[:, j], sigma=3) if len(coeffs[:, j]) > 5 else coeffs[:, j]
        ax.plot(cycles, c_smooth, color=colors[j % len(colors)], linewidth=1.5)
        if len(c_smooth) > 10 and len(caps) > 10:
            r = np.corrcoef(c_smooth[len(c_smooth) // 10:], caps[len(caps) // 10:])[0, 1]
            ax.set_title(f"{mode_names[j]} (r={r:.2f})")
        else:
            ax.set_title(mode_names[j])
        ax.set_xlabel("Cycle")
        ax.grid(True, alpha=0.3)

    for idx in range(n_modes + 1, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(f"Dominant: {result['dominant_mode']}", fontsize=13)
    fig.tight_layout()

    if output_path is None:
        output_path = Path("output") / "decomposition.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def format_decomposition_summary(result: dict) -> str:
    """Format decomposition results as a human-readable text summary."""
    if "error" in result:
        return f"Error: {result['error']}"

    lines = [f"Degradation Mode Decomposition ({len(result['cycles'])} cycles)"]
    lines.append(f"Reference cycles: {result['reference_cycle_range']}")
    lines.append(f"Mean fit RMSE: {np.mean(result['rmse_mV']):.1f} mV")
    lines.append("")
    lines.append("Mode contributions (sorted):")
    contribs = sorted(result["mode_contributions"].items(), key=lambda x: -x[1])
    for name, pct in contribs:
        desc = MODE_DESCRIPTIONS.get(name, "")
        lines.append(f"  {name:25s}: {pct:5.1f}%  — {desc}")
    lines.append("")
    lines.append(f"Dominant mode: {result['dominant_mode']}")
    return "\n".join(lines)
