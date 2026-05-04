"""Datasets page: manage and view loaded datasets. Direct core library usage."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.data.transformer import compute_insights

PAGE_SIZE = 10


def render_datasets_page():
    store = DataStore()
    all_ids = store.list_ids()

    st.header("数据集管理")

    if not all_ids:
        st.warning("暂无数据集。请先在\"上传数据\"页面加载数据。")
        return

    table = store.list_as_table()
    if not table.empty:
        st.dataframe(table, width="stretch", hide_index=True)

    st.divider()

    # Pagination
    total = len(all_ids)
    if "ds_page" not in st.session_state:
        st.session_state.ds_page = 0
    max_page = max(0, (total - 1) // PAGE_SIZE)
    page = min(st.session_state.ds_page, max_page)

    col_prev, col_info, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("上一页", disabled=(page == 0)):
            st.session_state.ds_page = page - 1
            st.rerun()
    with col_info:
        start = page * PAGE_SIZE + 1
        end = min((page + 1) * PAGE_SIZE, total)
        st.markdown(f"**第 {start}-{end} / {total} 个数据集**")
    with col_next:
        if st.button("下一页", disabled=(page >= max_page)):
            st.session_state.ds_page = page + 1
            st.rerun()

    page_ids = all_ids[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    for data_id in page_ids:
        try:
            ds = store.get(data_id)
            if ds is None:
                continue

            label = f"`{data_id}` — {ds.cell_id or 'N/A'}"
            if ds.chemistry:
                label += f" ({ds.chemistry})"

            with st.expander(label):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("循环数", ds.num_cycles)
                col2.metric("数据点", f"{ds.num_data_points:,}")
                col3.metric("来源", ds.source_file.split("/")[-1] if ds.source_file else "N/A")
                col4.metric("设计元数据", "有" if ds.experiment_design else "无")

                if not ds.cycle_summary.empty and ds.num_cycles <= 200:
                    try:
                        insights = compute_insights(ds)
                        if insights:
                            st.markdown("**关键指标:**")
                            cols = st.columns(4)
                            metrics = [
                                ("初始容量", f"{float(insights.get('initial_discharge_cap', 0)):.4f} Ah"),
                                ("衰减", f"{float(insights.get('capacity_fade_pct', 0)):.1f}%"),
                                ("平均CE", f"{float(insights.get('ce_mean', 0)):.2f}%"),
                                ("保持率", f"{float(insights.get('final_retention_pct', 0)):.1f}%"),
                            ]
                            for c, (name, val) in zip(cols, metrics):
                                c.metric(name, val)
                        if insights.get("health_assessments"):
                            for a in insights["health_assessments"]:
                                st.markdown(f"- {a}")
                    except Exception:
                        pass
                elif ds.num_cycles > 200:
                    st.info(f"数据集含 {ds.num_cycles} 个循环，跳过自动指标计算以提升性能。")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("选择为当前数据集", key=f"select_{data_id}"):
                        st.session_state.active_dataset_id = data_id
                        st.success(f"已选择: {data_id}")
                with col2:
                    if st.button("删除", key=f"del_{data_id}"):
                        store.remove(data_id)
                        st.success(f"已删除: {data_id}")
                        st.rerun()
        except Exception as e:
            st.warning(f"数据集 `{data_id}` 渲染出错: {e}")
