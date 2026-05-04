"""Report page: generate reports. Direct core library."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.report.generator import generate_report


def render_report_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()
    all_ids = store.list_ids()

    st.header("报告生成")

    if not all_ids:
        st.warning("暂无数据集。请先加载数据。")
        return

    options = [f"{did} ({store.get(did).num_cycles} cycles)" for did in all_ids]
    selected = st.selectbox("选择数据集", options)
    data_id = all_ids[options.index(selected)]

    fmt = st.selectbox("报告格式", ["markdown", "html"])

    if st.button("生成报告", type="primary"):
        ds = store.get(data_id)
        if ds is None:
            st.error("数据集不存在")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            with st.spinner("生成中..."):
                path = generate_report(ds, output_format=fmt, output_dir=Path(tmpdir))
                st.success(f"报告已生成: {path}")

            report_path = Path(path)
            if report_path.exists():
                content = report_path.read_text(encoding="utf-8")
                if fmt == "markdown":
                    st.markdown(content)
                else:
                    st.components.v1.html(content, height=800, scrolling=True)

                st.download_button(
                    "下载报告",
                    data=content,
                    file_name=report_path.name,
                    mime="text/markdown" if fmt == "markdown" else "text/html",
                )
