"""Streamlit page: DOE analysis."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.degradation.doe_checker import check_doe_coverage, analyze_design_impact


def render_doe_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    st.header("DOE 分析")

    store = DataStore()
    all_ids = store.list_ids()

    if len(all_ids) < 2:
        st.warning("至少需要2个实验才能进行DOE分析。")
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

    selected = st.multiselect("选择实验（至少2个）", options, default=options[:min(3, len(options))])

    if len(selected) < 2:
        st.info("请选择至少2个实验。")
        return

    selected_datasets = [all_datasets[i] for i, opt in enumerate(options) if opt in selected]

    tab_coverage, tab_impact = st.tabs(["DOE覆盖度", "设计因子影响"])

    with tab_coverage:
        if st.button("分析DOE覆盖度"):
            result = check_doe_coverage(selected_datasets)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("实验数量", result["n_experiments"])
            with col2:
                st.metric("覆盖度得分", f"{result['coverage_score']:.1%}")

            st.subheader("已测试的设计因子")
            if result["factors_tested"]:
                for f in result["factors_tested"]:
                    st.markdown(f"  - `{f}`")
            else:
                st.info("没有发现变化的因子。")

            st.subheader("未变化/缺失的因子")
            if result["factors_constant"]:
                for f in result["factors_constant"]:
                    st.markdown(f"  - `{f}`")
            else:
                st.success("所有因子都有变化。")

            if result["missing_combinations"]:
                st.subheader("缺失的组合")
                for combo in result["missing_combinations"][:10]:
                    st.markdown(f"  - {combo}")

            if result["recommendations"]:
                st.subheader("推荐补充实验")
                for rec in result["recommendations"]:
                    color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "")
                    st.markdown(f"  {color} {rec['description']}")

    with tab_impact:
        focus = st.text_input("聚焦因子（可选，如 positive_electrode.thickness_um）", key="doe_focus")
        if st.button("分析设计因子影响"):
            with st.spinner("正在分析..."):
                result = analyze_design_impact(
                    selected_datasets,
                    focus_factor=focus if focus else None,
                )

                if "error" in result:
                    st.error(result["error"])
                    return

                for factor, info in result.get("factor_analysis", {}).items():
                    with st.expander(f"**{factor}**"):
                        if "interpretation" in info:
                            st.markdown(info["interpretation"])
                        if "correlation_with_fade" in info:
                            st.metric("与容量衰减的相关系数", f"{info['correlation_with_fade']:.3f}")
                        if "groups" in info:
                            st.markdown("**分组统计:**")
                            for val, stats in info["groups"].items():
                                st.markdown(f"  - `{val}`: 平均衰减 {stats['mean_fade']}% (n={stats['n']})")
