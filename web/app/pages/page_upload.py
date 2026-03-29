"""Upload page: upload CSV battery data files."""

from __future__ import annotations

import streamlit as st
from web.app.utils.api_client import upload_dataset


def render_upload_page():
    """Render the file upload page."""
    st.header("📤 上传电池数据")

    st.markdown("""
    上传电池循环数据 CSV 文件进行分析。支持：
    - **PEC CSV 格式** (cellpy 格式)
    - 通用 CSV 格式
    """)

    uploaded_file = st.file_uploader(
        "选择 CSV 文件",
        type=["csv"],
        help="支持 PEC CSV 和通用 CSV 格式",
        label_visibility="visible",
    )

    if uploaded_file:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("文件信息")
            st.write(f"**文件名:** {uploaded_file.name}")
            st.write(f"**大小:** {uploaded_file.size / 1024:.1f} KB")

        with col2:
            st.subheader("数据集选项")
            data_id = st.text_input(
                "数据集 ID (可选)",
                value=uploaded_file.name.replace(".csv", ""),
                help="留空则自动生成",
            )

        st.divider()

        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("📋 点击下方按钮上传并分析数据")
        with col2:
            if st.button("上传并分析", type="primary", use_container_width=True):
                with st.spinner("上传中..."):
                    try:
                        result = upload_dataset(uploaded_file, data_id if data_id else None)
                        st.session_state.active_dataset_id = result["data_id"]

                        st.success(f"✅ 上传成功! 数据集 ID: `{result['data_id']}`")

                        with st.expander("查看详情", expanded=True):
                            st.json(result)

                        # Suggest next actions
                        st.divider()
                        st.subheader("下一步")
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("📊 查看数据集", key="goto_datasets"):
                                st.switch_page("page_datasets.py")
                        with c2:
                            if st.button("📈 生成可视化", key="goto_viz"):
                                st.switch_page("page_visualization.py")

                    except Exception as e:
                        st.error(f"❌ 上传失败: {str(e)}")

    else:
        st.info("👆 请上传一个 CSV 文件开始分析")

        # Show example
        with st.expander("示例数据格式"):
            st.markdown("""
            **PEC CSV 格式示例:**

            ```csv
            # DataPoint,Cycle,Step,Test_Time,Step_Time,Voltage,Current,...
            0,0,0,0,0,3.5,0,...
            1,0,0,1,1,3.6,0,...
            ...
            ```

            **必需列:**
            - `Voltage` (V)
            - `Current` (A)
            - `Charge_Capacity` (Ah)
            - `Discharge_Capacity` (Ah)
            """)
