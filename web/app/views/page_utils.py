"""Utility functions for Streamlit pages."""

from __future__ import annotations

import streamlit as st


def check_dataset_selected() -> str | None:
    """Check if a dataset is selected, show warning if not.

    Returns:
        The selected dataset ID, or None if none selected.
    """
    data_id = st.session_state.get("active_dataset_id")
    if not data_id:
        st.warning("⚠️ 请先选择一个数据集")
        st.info("前往「数据集管理」页面查看可用数据集，或上传新数据。")
        return None
    return data_id


def format_number(value: float, precision: int = 2) -> str:
    """Format a number with specified precision."""
    return f"{value:.{precision}f}"


def format_percentage(value: float, precision: int = 2) -> str:
    """Format a value as a percentage."""
    return f"{value:.{precision}f}%"


def render_insights_cards(insights: dict):
    """Render insights as metric cards."""
    if not insights:
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if "capacity_fade_pct" in insights:
            st.metric(
                "容量衰减",
                format_percentage(insights["capacity_fade_pct"]),
                help=f"初始: {insights.get('initial_discharge_cap', 0):.4f} Ah -> 最终: {insights.get('final_discharge_cap', 0):.4f} Ah"
            )

    with col2:
        if "ce_mean" in insights:
            st.metric(
                "平均库仑效率",
                format_percentage(insights["ce_mean"]),
                delta=f"±{format_number(insights.get('ce_std', 0))}%"
            )

    with col3:
        if "avg_hysteresis" in insights:
            st.metric(
                "电压滞后",
                format_number(insights["avg_hysteresis"], 3) + " V",
                help="充电平均电压 - 放电平均电压"
            )

    with col4:
        if "ir_mean" in insights:
            st.metric(
                "平均内阻",
                format_number(insights["ir_mean"], 4) + " Ω",
            )
