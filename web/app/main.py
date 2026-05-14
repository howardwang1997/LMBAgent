"""Streamlit web frontend for LMBAgent."""

from __future__ import annotations

import traceback
import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

st.set_page_config(
    page_title="LMBAgent",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    html, body, .stApp {
        height: auto !important;
        overflow: auto !important;
        overflow-y: scroll !important;
    }
    .stAppViewMainContent, .main .block-container {
        max-width: 100% !important;
        height: auto !important;
        overflow: visible !important;
        padding-top: 2rem !important;
        padding-bottom: 6rem !important;
    }
    .stAppViewBlockContainer {
        height: auto !important;
        overflow: visible !important;
    }
    .element-container {
        height: auto !important;
        overflow: visible !important;
    }
    section[data-testid="stImage"] img {
        max-width: 100% !important;
        height: auto !important;
    }
    .stDataFrame {
        min-height: 200px !important;
    }
    /* Force scrollable parent containers */
    [data-testid="stAppViewContainer"], 
    [data-testid="stSidebar"],
    [data-testid="stSidebarContent"] {
        height: auto !important;
        overflow: visible !important;
    }
    [data-testid="stBaseButton-secondary"] {
        margin-bottom: 1rem;
    }
</style>
<script>
    // Force scrollable: override any parent iframe restrictions
    document.documentElement.style.overflow = 'auto';
    document.body.style.overflow = 'auto';
    document.documentElement.style.height = 'auto';
    document.body.style.height = 'auto';
    // Try to tell parent iframe to allow scrolling
    try {
        if (window.parent !== window) {
            var iframes = window.parent.document.querySelectorAll('iframe');
            iframes.forEach(function(f) {
                f.style.height = 'auto';
                f.style.minHeight = '100vh';
                f.scrolling = 'yes';
                f.setAttribute('scrolling', 'yes');
            });
        }
    } catch(e) {}
</script>
""", unsafe_allow_html=True)

if "active_dataset_id" not in st.session_state:
    st.session_state.active_dataset_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("🔋 LMBAgent")
    st.caption("Lithium Metal Battery Data Analysis")

    st.divider()

    page = st.radio(
        "导航",
        ["📤 上传数据", "📊 数据集管理", "📈 可视化", "⚖️ 实验对比", "🔬 退化分析", "📐 DOE分析", "🔍 历史检索", "📝 结论管理", "📄 报告生成", "💬 AI 聊天"],
        label_visibility="collapsed",
    )

    st.divider()

    if st.session_state.active_dataset_id:
        st.info(f"**当前数据集:** `{st.session_state.active_dataset_id}`")
        if st.button("清除选择"):
            st.session_state.active_dataset_id = None
            st.rerun()
    else:
        st.warning("未选择数据集")

    st.divider()

    if st.button("🗑️ 重置数据库"):
        from lmbagent.data.store import DataStore
        DataStore().clear()
        st.success("已清空")
        st.rerun()

    st.divider()

    st.markdown(
        '<a href="http://27.54.45.156:8080/" target="_blank" '
        'style="display:inline-block;width:100%;padding:0.5rem 1rem;'
        'background:linear-gradient(135deg,#667eea,#764ba2);color:white;'
        'text-align:center;border-radius:8px;text-decoration:none;'
        'font-weight:600;font-size:0.9rem;">'
        '🔎 Deep Research</a>',
        unsafe_allow_html=True,
    )

    if st.button("📊 项目汇报", use_container_width=True):
        st.session_state.show_presentation = not st.session_state.get("show_presentation", False)

PAGE_MAP = {
    "📤 上传数据": ("web.app.views.page_upload", "render_upload_page"),
    "📊 数据集管理": ("web.app.views.page_datasets", "render_datasets_page"),
    "📈 可视化": ("web.app.views.page_visualization", "render_visualization_page"),
    "⚖️ 实验对比": ("web.app.views.page_comparison", "render_comparison_page"),
    "🔬 退化分析": ("web.app.views.page_degradation", "render_degradation_page"),
    "📐 DOE分析": ("web.app.views.page_doe", "render_doe_page"),
    "🔍 历史检索": ("web.app.views.page_search", "render_search_page"),
    "📝 结论管理": ("web.app.views.page_conclusions", "render_conclusions_page"),
    "📄 报告生成": ("web.app.views.page_report", "render_report_page"),
    "💬 AI 聊天": ("web.app.views.page_chat", "render_chat_page"),
}

st.markdown("""
<script>
if (!window._staticServerStarted) {
    window._staticServerStarted = true;
    fetch('/_stcore/health').then(() => {});
}
</script>
""", unsafe_allow_html=True)

module_name, func_name = PAGE_MAP[page]

if st.session_state.get("show_presentation"):
    pres_path = Path(__file__).parent.parent / "static" / "presentation.html"
    if pres_path.exists():
        with open(pres_path, "r", encoding="utf-8") as f:
            pres_html = f.read()
        st.components.v1.html(pres_html, height=800, scrolling=True)
        st.info("点击侧边栏「📊 项目汇报」按钮关闭演示")
    else:
        st.warning("演示文件不存在")
else:
    mod = __import__(module_name, fromlist=[func_name])
    render_fn = getattr(mod, func_name)

    try:
        render_fn()
    except Exception as e:
        st.error(f"页面渲染出错: {e}")
        with st.expander("详细错误信息"):
            st.code(traceback.format_exc())
        st.info("请刷新页面重试，或切换到其他页面。")
