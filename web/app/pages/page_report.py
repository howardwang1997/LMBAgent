"""Report page: generate and download analysis reports."""

from __future__ import annotations

import streamlit as st
from pathlib import Path
from web.app.utils.api_client import generate_report, download_report
from web.app.pages.page_utils import check_dataset_selected, render_insights_cards
from web.app.pages.page_datasets import list_datasets


def render_report_page():
    """Render the report generation page."""
    st.header("📄 报告生成")

    # Check dataset selection
    data_id = check_dataset_selected()
    if not data_id:
        return

    # Get dataset info for insights preview
    try:
        datasets = list_datasets()
        dataset_info = next((d for d in datasets if d["data_id"] == data_id), None)
        if dataset_info:
            st.caption(f"数据集: `{data_id}` | {dataset_info.get('num_cycles', 0)} 循环 | {dataset_info.get('num_data_points', 0):,} 数据点")
    except:
        pass

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        output_format = st.selectbox(
            "报告格式",
            options=["markdown", "html", "pdf"],
            format_func=lambda x: x.upper(),
            help="Markdown: 纯文本格式\nHTML: 网页格式\nPDF: 可打印文档",
        )

    with col2:
        include_plots = st.checkbox("包含图表", value=True, help="报告中包含所有 4 种可视化图表")

    analysis_notes = st.text_area(
        "分析备注 (可选)",
        placeholder="添加自定义分析备注...",
        help="这些备注将包含在报告的分析备注部分",
        height=100,
    )

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        generate = st.button("📝 生成报告", type="primary", use_container_width=True)

    with col2:
        preview = st.checkbox("预览内容", value=False)

    st.divider()

    if generate:
        with st.spinner("生成中..."):
            try:
                result = generate_report(data_id, output_format, analysis_notes if analysis_notes else None)
                st.success(f"✅ 报告已生成!")

                # Show report info
                col1, col2, col3 = st.columns(3)
                col1.write(f"**格式:** {output_format.upper()}")
                col2.write(f"**路径:** `{result['report_path']}`")

                # Download button
                report_content = download_report(data_id, output_format)
                mime_type = {
                    "pdf": "application/pdf",
                    "html": "text/html",
                    "markdown": "text/markdown",
                }.get(output_format, "text/plain")

                st.download_button(
                    "⬇️ 下载报告",
                    report_content,
                    f"report_{data_id}.{output_format}",
                    mime_type,
                    use_container_width=True,
                )

                # Preview
                if preview and output_format in ["markdown", "html"]:
                    st.divider()
                    st.subheader("预览")

                    if output_format == "markdown":
                        st.markdown(report_content.decode("utf-8"))
                    else:
                        st.components.v1.html(
                            report_content.decode("utf-8"),
                            height=600,
                            scrolling=True,
                        )

            except Exception as e:
                st.error(f"❌ 生成失败: {e}")

    else:
        st.info("👆 选择报告格式并点击「生成报告」")

        # Show what will be included
        st.divider()
        st.subheader("报告内容预览")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
            **报告将包含以下内容:**

            - 📋 数据集摘要
            - 📊 循环性能表
            - 📈 容量衰减分析
            - ⚡ 库仑效率分析
            - 🔋 电压分析
            - 📉 内阻分析
            """)

        with col2:
            if include_plots:
                st.markdown("""
                **图表 (4 张):**

                - 容量衰减图
                - 库仑效率图
                - 电压曲线图
                - 内阻变化图
                """)
