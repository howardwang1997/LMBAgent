"""Visualization page: generate and view battery data plots."""

from __future__ import annotations

import streamlit as st
from web.app.utils.api_client import get_plot, decode_base64_image
from web.app.views.page_utils import check_dataset_selected


def render_visualization_page():
    """Render the visualization page."""
    st.header("📈 数据可视化")

    # Check dataset selection
    data_id = check_dataset_selected()
    if not data_id:
        return

    # Plot type selection
    plot_types = {
        "capacity_fade": "容量衰减 (Capacity Fade)",
        "coulombic_efficiency": "库仑效率 (Coulombic Efficiency)",
        "voltage_curves": "电压曲线 (Voltage Curves)",
        "impedance": "内阻 (Internal Resistance)",
    }

    col1, col2 = st.columns([1, 2])
    with col1:
        plot_type_key = st.selectbox(
            "选择图表类型",
            options=list(plot_types.keys()),
            format_func=lambda x: plot_types[x],
            label_visibility="visible",
        )

    with col2:
        st.write(f"**{plot_types[plot_type_key]}**")

    st.divider()

    # Plot parameters
    with st.expander("🎛️ 图表参数", expanded=False):
        params = {}

        if plot_type_key == "capacity_fade":
            normalize = st.checkbox("归一化显示 (Normalize)", value=True, help="相对于首次循环的容量百分比")
            params["normalize"] = normalize

        elif plot_type_key == "coulombic_efficiency":
            y_range = st.text_input("Y 轴范围", placeholder="例如: 95-101", help="留空使用自动范围")
            if y_range:
                params["y_range"] = y_range

        elif plot_type_key == "voltage_curves":
            cycles = st.text_input("循环编号", value="1,2,3", help="逗号分隔，例如: 1,2,3")
            if cycles:
                try:
                    params["cycles"] = cycles
                except ValueError:
                    st.error("循环编号格式错误")

    # Generate button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        generate = st.button("🔄 生成图表", type="primary", use_container_width=True)

    with col2:
        auto_generate = st.checkbox("自动生成", value=True)

    if generate or (auto_generate and "last_plot_type" not in st.session_state):
        st.session_state.last_plot_type = plot_type_key

    # Display plot
    if "last_plot_type" in st.session_state and st.session_state.last_plot_type == plot_type_key:
        with st.spinner("生成中..."):
            try:
                result = get_plot(data_id, plot_type_key, **params)

                # Decode and display image
                image_bytes = decode_base64_image(result["image"])
                st.image(image_bytes, use_container_width=True)

                # Download button
                import base64
                st.download_button(
                    "⬇️ 下载图表",
                    base64.b64decode(result["image"]),
                    f"{plot_type_key}.png",
                    "image/png",
                    use_container_width=True,
                )

            except Exception as e:
                st.error(f"生成失败: {e}")

    else:
        st.info("👆 点击「生成图表」开始")

    # Quick actions
    st.divider()
    st.subheader("快捷操作")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("容量衰减", key="quick_cap"):
            st.session_state.last_plot_type = "capacity_fade"
            st.rerun()

    with col2:
        if st.button("库仑效率", key="quick_ce"):
            st.session_state.last_plot_type = "coulombic_efficiency"
            st.rerun()

    with col3:
        if st.button("电压曲线", key="quick_volt"):
            st.session_state.last_plot_type = "voltage_curves"
            st.rerun()

    with col4:
        if st.button("内阻", key="quick_ir"):
            st.session_state.last_plot_type = "impedance"
            st.rerun()
