"""Shared matplotlib styling for battery data plots."""

import matplotlib.pyplot as plt

COLORS = {
    "charge": "#2196F3",
    "discharge": "#F44336",
    "efficiency": "#4CAF50",
    "impedance": "#FF9800",
    "cycle_cmap": "viridis",
}

FIGURE_SIZE = (10, 6)
DPI = 150


def apply_style():
    """Apply consistent matplotlib style."""
    plt.rcParams.update({
        "figure.figsize": FIGURE_SIZE,
        "figure.dpi": DPI,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 12,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "legend.fontsize": 10,
        "lines.linewidth": 1.5,
    })
