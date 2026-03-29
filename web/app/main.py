"""Streamlit web frontend for LMBAgent."""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="LMBAgent",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state initialization
if "active_dataset_id" not in st.session_state:
    st.session_state.active_dataset_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar navigation
with st.sidebar:
    st.title("🔋 LMBAgent")
    st.caption("Lithium Metal Battery Data Analysis")

    st.divider()

    page = st.radio(
        "导航",
        ["📤 上传数据", "📊 数据集管理", "📈 可视化", "📄 报告生成", "🤖 AI 聊天"],
        label_visibility="collapsed",
    )

    st.divider()

    # Active dataset indicator
    if st.session_state.active_dataset_id:
        st.info(f"**当前数据集:** `{st.session_state.active_dataset_id}`")
        if st.button("清除选择"):
            st.session_state.active_dataset_id = None
            st.rerun()
    else:
        st.warning("未选择数据集")

    st.divider()

    # API status
    with st.expander("API 状态"):
        try:
            import requests
            r = requests.get("http://localhost:8000/health", timeout=2)
            if r.status_code == 200:
                st.success("🟢 API 连接正常")
            else:
                st.error("🔴 API 连接异常")
        except Exception:
            st.error("🔴 API 未启动")

# Page routing
if page == "📤 上传数据":
    from web.app.pages.page_upload import render_upload_page
    render_upload_page()

elif page == "📊 数据集管理":
    from web.app.pages.page_datasets import render_datasets_page
    render_datasets_page()

elif page == "📈 可视化":
    from web.app.pages.page_visualization import render_visualization_page
    render_visualization_page()

elif page == "📄 报告生成":
    from web.app.pages.page_report import render_report_page
    render_report_page()

elif page == "🤖 AI 聊天":
    from web.app.pages.page_chat import render_chat_page
    render_chat_page()
