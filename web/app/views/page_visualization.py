"""Visualization page: generate plots for active dataset. Direct core library."""

from __future__ import annotations

import sys
import tempfile
import shutil
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.visualization.capacity_plot import plot_capacity_fade
from lmbagent.visualization.efficiency_plot import plot_coulombic_efficiency
from lmbagent.visualization.voltage_plot import plot_voltage_curves
from lmbagent.visualization.impedance_plot import plot_impedance

_PLOT_DIR = Path(tempfile.gettempdir()) / "lmbagent_plots"


def _safe_plot(plot_fn, ds, **kwargs):
    _PLOT_DIR.mkdir(parents=True, exist_ok=True)
    out = _PLOT_DIR / f"{plot_fn.__name__}_{ds.data_id}.png"
    try:
        result = plot_fn(ds, output_path=out, **kwargs)
        if Path(result).exists():
            img_bytes = Path(result).read_bytes()
            st.image(img_bytes, width="stretch")
        else:
            st.error("图表文件未生成")
    except Exception as e:
        st.error(f"生成图表失败: {e}")


def render_visualization_page():
    try:
        _render()
    except Exception as e:
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()
    all_ids = store.list_ids()

    st.header("可视化")

    if not all_ids:
        st.warning("暂无数据集。请先加载数据。")
        return

    options = [f"{did} ({store.get(did).num_cycles} cycles)" for did in all_ids]
    selected = st.selectbox("选择数据集", options, key="viz_select")
    data_id = all_ids[options.index(selected)]

    ds = store.get(data_id)
    if ds is None:
        st.error("数据集不存在")
        return
    if ds.cycle_summary.empty:
        try:
            ds = add_cycle_summary(ds)
            store.put(ds)
        except Exception as e:
            st.error(f"计算循环摘要失败: {e}")
            return

    st.markdown(f"**数据集:** `{data_id}` | {ds.num_cycles} cycles | {ds.num_data_points:,} points")

    plot_type = st.selectbox("图表类型", ["容量衰减", "库仑效率", "电压曲线", "内阻抗"], key="viz_type")

    st.divider()

    if plot_type == "容量衰减":
        normalize = st.checkbox("归一化 (%)", value=False, key="viz_norm")
        if st.button("生成图表", key="viz_btn_cap"):
            _safe_plot(plot_capacity_fade, ds, normalize=normalize)

    elif plot_type == "库仑效率":
        y_range_str = st.text_input("Y轴范围 (如 95-101)", value="", key="viz_yrange")
        y_range = None
        if y_range_str:
            try:
                parts = y_range_str.split("-")
                y_range = (float(parts[0]), float(parts[1]))
            except Exception:
                st.warning("Y轴范围格式错误，请使用如 95-101 的格式")
        if st.button("生成图表", key="viz_btn_ce"):
            _safe_plot(plot_coulombic_efficiency, ds, y_range=y_range)

    elif plot_type == "电压曲线":
        cycles_str = st.text_input("循环号 (逗号分隔)", value="0,1,2", key="viz_cycles")
        if st.button("生成图表", key="viz_btn_volt"):
            try:
                cycle_nums = [int(c.strip()) for c in cycles_str.split(",") if c.strip()]
            except ValueError:
                st.error("循环号格式错误")
                return
            _safe_plot(plot_voltage_curves, ds, cycle_numbers=cycle_nums)

    elif plot_type == "内阻抗":
        if st.button("生成图表", key="viz_btn_imp"):
            _safe_plot(plot_impedance, ds)
