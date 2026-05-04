"""Streamlit page: experiment comparison."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st
import pandas as pd

from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.comparison.overlay import (
    overlay_capacity_fade,
    overlay_coulombic_efficiency,
    overlay_voltage_curves,
)
from lmbagent.comparison.delta import plot_delta_v
from lmbagent.comparison.metrics import build_comparison_table, summarize_differences


def render_comparison_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    st.header("实验对比")

    store = DataStore()
    all_ids = store.list_ids()

    if len(all_ids) < 2:
        st.warning("至少需要加载2个数据集才能进行对比。请先在\"上传数据\"页面加载数据。")
        return

    all_datasets = [store.get(did) for did in all_ids]
    all_datasets = [ds for ds in all_datasets if ds is not None]

    options = []
    for ds in all_datasets:
        label = f"{ds.cell_id or ds.data_id}"
        if ds.chemistry:
            label += f" ({ds.chemistry})"
        label += f" — {ds.num_cycles} cycles"
        options.append(label)

    selected = st.multiselect(
        "选择要对比的实验（至少2个）",
        options=options,
        format_func=lambda x: x,
    )

    if len(selected) < 2:
        st.info("请选择至少2个实验进行对比。")
        return

    selected_datasets = [all_datasets[i] for i, opt in enumerate(options) if opt in selected]

    for ds in selected_datasets:
        if ds.cycle_summary.empty:
            ds = add_cycle_summary(ds)
            store.put(ds)

    tab_metrics, tab_overlay, tab_delta = st.tabs(["指标对比", "叠加图", "差异分析"])

    with tab_metrics:
        st.subheader("跨实验指标对比表")
        table = build_comparison_table(selected_datasets)
        st.dataframe(table, width="stretch", hide_index=True)

        summary = summarize_differences(selected_datasets)
        if summary["differing_design_factors"]:
            st.markdown("**变化的实验设计因子:**")
            for factor in summary["differing_design_factors"]:
                st.markdown(f"  - `{factor}`")
        else:
            st.info("所有实验的设计因子相同（或未填写设计元数据）。")

        col1, col2 = st.columns(2)
        with col1:
            if summary["best_retention"]:
                st.metric("最佳容量保持率", summary["best_retention"])
        with col2:
            if summary["worst_fade"]:
                st.metric("最大容量衰减", summary["worst_fade"])

    with tab_overlay:
        st.subheader("叠加对比图")
        plot_type = st.selectbox(
            "图表类型",
            ["容量衰减", "库仑效率", "电压曲线"],
            key="overlay_type",
        )

        if st.button("生成叠加图"):
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                if plot_type == "容量衰减":
                    path = overlay_capacity_fade(
                        selected_datasets, output_path=Path(tmpdir) / "overlay_cap.png"
                    )
                elif plot_type == "库仑效率":
                    path = overlay_coulombic_efficiency(
                        selected_datasets, output_path=Path(tmpdir) / "overlay_ce.png"
                    )
                else:
                    cycle_num = st.session_state.get("voltage_cycle", 0)
                    path = overlay_voltage_curves(
                        selected_datasets, cycle_number=cycle_num,
                        output_path=Path(tmpdir) / "overlay_v.png"
                    )
                st.image(path, width="stretch")

        if plot_type == "电压曲线":
            cycle_num = st.number_input("选择循环号", min_value=0, value=0, step=1,
                                         key="voltage_cycle")

    with tab_delta:
        st.subheader("电压差异分析 (ΔV)")
        col_a, col_b = st.columns(2)
        delta_options = [ds.cell_id or ds.data_id for ds in selected_datasets]
        with col_a:
            sel_a = st.selectbox("实验 A", delta_options, key="delta_a")
        with col_b:
            sel_b = st.selectbox("实验 B", delta_options, index=1, key="delta_b")

        delta_cycle = st.number_input("循环号", min_value=0, value=0, step=1, key="delta_cycle")

        if st.button("生成差异图") and sel_a != sel_b:
            ds_a = next(ds for ds in selected_datasets if (ds.cell_id or ds.data_id) == sel_a)
            ds_b = next(ds for ds in selected_datasets if (ds.cell_id or ds.data_id) == sel_b)
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                path = plot_delta_v(
                    ds_a, ds_b, cycle_number=delta_cycle,
                    output_path=Path(tmpdir) / "delta.png"
                )
                st.image(path, width="stretch")
        elif sel_a == sel_b:
            st.warning("请选择两个不同的实验。")
