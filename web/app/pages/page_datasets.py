"""Datasets page: manage and view loaded datasets."""

from __future__ import annotations

import streamlit as st
from web.app.utils.api_client import list_datasets, get_dataset, delete_dataset


def render_dataset_card(dataset: dict):
    """Render a single dataset card."""
    data_id = dataset["data_id"]

    with st.expander(f"🔋 `{data_id}` — {dataset.get('test_name', 'N/A')}", expanded=False):
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("循环数", dataset["num_cycles"])
        col2.metric("数据点", f"{dataset['num_data_points']:,}")
        col3.metric("电压范围", f"{dataset['voltage_min']:.2f}V")
        col4.metric("电流范围", f"±{abs(dataset['current_max']):.2f}A")

        # Actions row
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("📊 详情", key=f"detail_{data_id}", use_container_width=True):
                st.session_state.active_dataset_id = data_id
                with st.spinner("加载中..."):
                    try:
                        detail = get_dataset(data_id)
                        st.json(detail)
                    except Exception as e:
                        st.error(f"加载失败: {e}")

        with col2:
            if st.button("📈 可视化", key=f"viz_{data_id}", use_container_width=True):
                st.session_state.active_dataset_id = data_id
                st.switch_page("page_visualization.py")

        with col3:
            if st.button("📄 报告", key=f"report_{data_id}", use_container_width=True):
                st.session_state.active_dataset_id = data_id
                st.switch_page("page_report.py")

        with col4:
            if st.button("🗑️ 删除", key=f"delete_{data_id}", use_container_width=True, type="secondary"):
                if st.session_state.get(f"confirm_delete_{data_id}"):
                    try:
                        delete_dataset(data_id)
                        st.success(f"已删除: {data_id}")
                        st.session_state.pop(f"confirm_delete_{data_id}", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除失败: {e}")
                else:
                    st.session_state[f"confirm_delete_{data_id}"] = True
                    st.warning("再次点击确认删除")
                    st.rerun()


def render_datasets_page():
    """Render the datasets management page."""
    st.header("📊 数据集管理")

    # Refresh button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # Load datasets
    with st.spinner("加载中..."):
        try:
            datasets = list_datasets()
        except Exception as e:
            st.error(f"加载失败: {e}")
            st.info("请确保 FastAPI 后端正在运行 (http://localhost:8000)")
            return

    if not datasets:
        st.info("暂无数据集。请先上传数据。")
        if st.button("📤 上传数据", type="primary"):
            st.switch_page("page_upload.py")
        return

    # Summary
    st.markdown(f"**共 {len(datasets)} 个数据集**")

    # Filter/search
    search = st.text_input("🔍 搜索", placeholder="输入数据集 ID 或测试名称...")

    # Filter datasets
    if search:
        search_lower = search.lower()
        datasets = [
            d for d in datasets
            if search_lower in d["data_id"].lower()
            or (d.get("test_name") and search_lower in d["test_name"].lower())
        ]

    # Sort by created_at (newest first)
    datasets.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    st.divider()

    # Render dataset cards
    for dataset in datasets:
        render_dataset_card(dataset)
