"""Streamlit page: DOE analysis with rich visualizations."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lmbagent.data.cell_test_template import DOE_FACTOR_GROUPS, DOE_ALL_FACTORS
from lmbagent.data.store import DataStore
from lmbagent.degradation.doe_checker import check_doe_coverage, analyze_design_impact


_GROUP_COLORS = {
    "电芯信息": "#636EFA",
    "正极": "#EF553B",
    "负极": "#00CC96",
    "电解液": "#AB63FA",
    "隔膜": "#FFA15A",
    "阻抗": "#19D3F3",
    "测试条件": "#FF6692",
    "夹具与力学": "#B6E880",
    "工艺标记": "#FF97FF",
}


def _coverage_donut(score: float) -> go.Figure:
    fig = go.Figure(go.Pie(
        values=[score, 1 - score],
        labels=["已覆盖", "未覆盖"],
        hole=0.7,
        marker_colors=["#00CC96", "#E5E5E5"],
        textinfo="none",
        sort=False,
    ))
    fig.update_layout(
        height=300, margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        annotations=[dict(
            text=f"{score:.0%}", x=0.5, y=0.5,
            font_size=28, font_color="#333", showarrow=False,
        )],
        title=dict(text="覆盖度", font_size=14, x=0.5, xanchor="center"),
    )
    return fig


def _factor_status_pie(tested, constant, all_factors) -> go.Figure:
    missing = [f for f in all_factors if f not in tested and f not in constant]
    fig = go.Figure(go.Pie(
        labels=["已变化", "固定", "无数据"],
        values=[len(tested), len(constant), len(missing)],
        hole=0.45,
        marker_colors=["#636EFA", "#B6E880", "#E5E5E5"],
        textinfo="label+value",
        textposition="outside",
    ))
    fig.update_layout(
        height=350, margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        title=dict(text="因子状态分布", font_size=14, x=0.5, xanchor="center"),
    )
    return fig


def _factor_group_bar(factor_summary, tested, constant, doe_groups) -> go.Figure:
    records = []
    for group_name, gf in doe_groups.items():
        all_f = gf.get("categorical", []) + gf.get("numeric", [])
        n_tested = sum(1 for f in all_f if f in tested)
        n_const = sum(1 for f in all_f if f in constant)
        n_miss = len(all_f) - n_tested - n_const
        if all_f:
            records.append(dict(group=group_name, 已变化=n_tested, 固定=n_const, 无数据=n_miss, total=len(all_f)))
    if not records:
        return go.Figure()
    df = pd.DataFrame(records)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["group"], x=df["已变化"], name="已变化", orientation="h", marker_color="#636EFA"))
    fig.add_trace(go.Bar(y=df["group"], x=df["固定"], name="固定", orientation="h", marker_color="#B6E880"))
    fig.add_trace(go.Bar(y=df["group"], x=df["无数据"], name="无数据", orientation="h", marker_color="#E5E5E5"))
    fig.update_layout(
        barmode="stack", height=max(300, len(records) * 40 + 80),
        margin=dict(l=100, r=20, t=30, b=30),
        xaxis_title="因子数量", yaxis_title="",
        title=dict(text="各类别因子覆盖情况", font_size=14, x=0.5, xanchor="center"),
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


def _combination_heatmap(factor_summary, table, tested) -> go.Figure:
    if len(tested) < 2:
        return go.Figure()
    tested_limited = tested[:10]
    n = len(tested_limited)
    coverage_matrix = np.full((n, n), np.nan)
    labels = tested_limited
    for i, f1 in enumerate(tested_limited):
        v1 = table[f1].dropna().unique() if f1 in table.columns else []
        for j, f2 in enumerate(tested_limited):
            if i == j:
                coverage_matrix[i, j] = 1.0
                continue
            v2 = table[f2].dropna().unique() if f2 in table.columns else []
            if len(v1) == 0 or len(v2) == 0:
                continue
            existing = set(zip(
                table[f1].fillna("__NA__").astype(str),
                table[f2].fillna("__NA__").astype(str),
            ))
            total = len(v1) * len(v2)
            covered = sum(1 for x in v1 for y in v2 if (str(x), str(y)) in existing)
            coverage_matrix[i, j] = covered / total if total > 0 else 0

    fig = go.Figure(go.Heatmap(
        z=coverage_matrix, x=labels, y=labels,
        colorscale=[[0, "#FF6692"], [0.5, "#FFA15A"], [1, "#00CC96"]],
        zmin=0, zmax=1,
        text=np.where(np.isnan(coverage_matrix), "", np.round(coverage_matrix * 100).astype(int).astype(str) + "%"),
        texttemplate="%{text}", textfont={"size": 10},
        hovertemplate="%{y} × %{x}: %{z:.0%}<extra></extra>",
    ))
    fig.update_layout(
        width=min(700, n * 65 + 120), height=min(700, n * 65 + 100),
        margin=dict(l=120, r=20, t=30, b=120),
        title=dict(text="因子组合覆盖热力图", font_size=14, x=0.5, xanchor="center"),
        xaxis_tickangle=-45,
    )
    return fig


def _categorical_distribution(factor_summary, tested, doe_groups) -> go.Figure:
    records = []
    for f in tested:
        info = factor_summary.get(f, {})
        n_unique = info.get("n_unique", 0)
        group_name = "其他"
        for gn, gf in doe_groups.items():
            if f in gf.get("categorical", []) + gf.get("numeric", []):
                group_name = gn
                break
        records.append(dict(factor=f, n_unique=n_unique, group=group_name))
    if not records:
        return go.Figure()
    df = pd.DataFrame(records)
    fig = px.bar(df, x="factor", y="n_unique", color="group",
                 color_discrete_map=_GROUP_COLORS,
                 labels={"factor": "因子", "n_unique": "不同取值数", "group": "类别"})
    fig.update_layout(
        height=400, margin=dict(l=50, r=20, t=30, b=120),
        title=dict(text="各因子取值数量", font_size=14, x=0.5, xanchor="center"),
        xaxis_tickangle=-45,
        showlegend=True,
    )
    return fig


def _fade_boxplot(merged_df, factor) -> go.Figure | None:
    if factor not in merged_df.columns or "fade_pct" not in merged_df.columns:
        return None
    sub = merged_df[[factor, "fade_pct"]].dropna()
    if len(sub) < 2:
        return None
    sub = sub.copy()
    sub[factor] = sub[factor].astype(str)
    fig = px.box(sub, x=factor, y="fade_pct", points="all",
                 color=factor, title=f"容量衰减率 按 {factor} 分组")
    fig.update_layout(
        height=400, margin=dict(l=50, r=20, t=50, b=60),
        showlegend=False,
        yaxis_title="容量衰减 (%)",
    )
    return fig


def _correlation_bar(merged_df, tested_factors) -> go.Figure:
    records = []
    for f in tested_factors:
        if f not in merged_df.columns or "fade_pct" not in merged_df.columns:
            continue
        sub = merged_df[[f, "fade_pct"]].dropna()
        try:
            vals = pd.to_numeric(sub[f], errors="coerce")
            valid = vals.notna() & sub["fade_pct"].notna()
            if valid.sum() >= 2:
                r = np.corrcoef(vals[valid], sub.loc[valid, "fade_pct"])[0, 1]
                records.append(dict(factor=f, correlation=r))
        except Exception:
            pass
    if not records:
        return go.Figure()
    df = pd.DataFrame(records).sort_values("correlation")
    colors = ["#EF553B" if abs(v) > 0.3 else "#636EFA" for v in df["correlation"]]
    fig = go.Figure(go.Bar(
        y=df["factor"], x=df["correlation"], orientation="h",
        marker_color=colors,
        text=df["correlation"].round(2).astype(str),
        textposition="auto",
    ))
    fig.update_layout(
        height=max(300, len(df) * 35 + 80),
        margin=dict(l=120, r=20, t=30, b=30),
        title=dict(text="因子与容量衰减的相关系数", font_size=14, x=0.5, xanchor="center"),
        xaxis_title="相关系数 (r)", xaxis_range=[-1, 1],
        shapes=[dict(type="line", x0=0, x1=0, y0=-0.5, y1=len(df) - 0.5,
                     line=dict(color="gray", width=1, dash="dash"))],
    )
    return fig


def _parallel_coordinates(merged_df, tested, selected_factors=None) -> go.Figure:
    display_factors = [f for f in tested if f in merged_df.columns]
    if selected_factors:
        display_factors = [f for f in selected_factors if f in display_factors]
    if len(display_factors) < 2:
        return go.Figure()

    cols = display_factors + ["fade_pct"]
    sub = merged_df[cols].copy()
    sub["fade_pct"] = pd.to_numeric(sub["fade_pct"], errors="coerce")
    sub = sub.dropna(subset=["fade_pct"])

    sub = sub.dropna(subset=display_factors)
    for f in display_factors:
        sub[f] = sub[f].astype(str)

    agg_df = sub.groupby(display_factors).agg(
        fade_mean=("fade_pct", "mean"),
        count=("fade_pct", "count"),
    ).reset_index()

    all_unique = []
    offsets = []
    cursor = 0
    for f in display_factors:
        vals = sorted(sub[f].unique(), key=str)
        all_unique.append(vals)
        offsets.append(cursor)
        cursor += len(vals)

    nodes = []
    node_labels = []
    for i, f in enumerate(display_factors):
        for v in all_unique[i]:
            nodes.append(dict(factor_idx=i, factor=f, value=v))
            node_labels.append(v)

    source = []
    target = []
    value = []
    link_colors = []

    fade_all = agg_df["fade_mean"]
    fmin, fmax = fade_all.min(), fade_all.max()
    frange = fmax - fmin if fmax - fmin > 1e-9 else 1.0

    def fade_to_rgba(fade_val):
        t = (fade_val - fmin) / frange
        t = max(0.0, min(1.0, t))
        if t < 0.25:
            r, g, b = 33, 150, 243
        elif t < 0.5:
            r, g, b = 76, 175, 80
        elif t < 0.75:
            r, g, b = 255, 235, 59
        else:
            r, g, b = 244, 67, 54
        return f"rgba({r},{g},{b},0.5)"

    for _, row in agg_df.iterrows():
        for i in range(len(display_factors) - 1):
            f1 = display_factors[i]
            f2 = display_factors[i + 1]
            idx1 = offsets[i] + all_unique[i].index(row[f1])
            idx2 = offsets[i + 1] + all_unique[i + 1].index(row[f2])
            source.append(idx1)
            target.append(idx2)
            value.append(int(row["count"]))
            link_colors.append(fade_to_rgba(row["fade_mean"]))

    node_colors = []
    palette = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
               "#19D3F3", "#FF6692", "#B6E880", "#FF97FF"]
    for i in range(len(display_factors)):
        c = palette[i % len(palette)]
        for _ in all_unique[i]:
            node_colors.append(c)

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=20,
            thickness=25,
            line=dict(color="white", width=2),
            label=node_labels,
            color=node_colors,
            hovertemplate="<b>%{label}</b><extra></extra>",
        ),
        link=dict(
            source=source,
            target=target,
            value=value,
            color=link_colors,
            hovertemplate="%{source.label} → %{target.label}<br>实验数: %{value}<extra></extra>",
        ),
        arrangement="snap",
        textfont=dict(size=15, color="#222"),
    ))
    fig.update_layout(
        height=600,
        margin=dict(l=30, r=30, t=60, b=30),
        font=dict(size=15, color="#222"),
        title=dict(
            text="多因子桑基图 (线宽=实验数, 连线颜色=容量衰减率: 蓝=低 红=高)",
            font_size=15, x=0.5, xanchor="center",
        ),
    )
    return fig


def _sunburst_factors(factor_summary, tested, constant, doe_groups) -> go.Figure:
    records = []
    for group_name, gf in doe_groups.items():
        all_f = gf.get("categorical", []) + gf.get("numeric", [])
        for f in all_f:
            status = "已变化" if f in tested else ("固定" if f in constant else "无数据")
            info = factor_summary.get(f, {})
            n = info.get("n_unique", 0)
            records.append(dict(group=group_name, factor=f, status=status, n_values=n))
    if not records:
        return go.Figure()

    child_values = [max(r["n_values"], 1) for r in records]

    group_sums = {}
    for r, v in zip(records, child_values):
        group_sums[r["group"]] = group_sums.get(r["group"], 0) + v
    total = sum(group_sums.values())

    all_ids = ["全部因子"]
    all_parents = [""]
    all_labels = ["全部因子"]
    all_values = [total]
    all_colors = ["#F5F5F5"]

    for g_name in doe_groups:
        all_ids.append(f"group::{g_name}")
        all_parents.append("全部因子")
        all_labels.append(g_name)
        all_values.append(group_sums.get(g_name, 1))
        all_colors.append(_GROUP_COLORS.get(g_name, "#CCC"))

    for r, v in zip(records, child_values):
        all_ids.append(f"factor::{r['factor']}")
        all_parents.append(f"group::{r['group']}")
        all_labels.append(r["factor"])
        all_values.append(v)
        status = r["status"]
        all_colors.append({"已变化": "#636EFA", "固定": "#B6E880", "无数据": "#E5E5E5"}.get(status, "#CCC"))

    fig = go.Figure(go.Sunburst(
        ids=all_ids,
        labels=all_labels,
        parents=all_parents,
        values=all_values,
        marker_colors=all_colors,
        branchvalues="total",
        textinfo="label",
        hovertemplate="<b>%{label}</b><br>取值数: %{value}<extra></extra>",
    ))
    fig.update_layout(
        height=450, margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="因子太阳树图", font_size=14, x=0.5, xanchor="center"),
    )
    return fig


def _collect_merged_table(datasets):
    from lmbagent.degradation.doe_checker import _collect_design_factors
    table = _collect_design_factors(datasets)
    outcomes = []
    for ds in datasets:
        fade = 0
        if not ds.cycle_summary.empty:
            cs = ds.cycle_summary
            valid = cs[cs["discharge_capacity"] > 0]
            if len(valid) >= 2:
                fade = (1 - valid.iloc[-1]["discharge_capacity"] / valid.iloc[0]["discharge_capacity"]) * 100
        outcomes.append({"data_id": ds.data_id, "fade_pct": fade})
    outcome_df = pd.DataFrame(outcomes)
    return table.merge(outcome_df, on="data_id", how="left")


def render_doe_page():
    try:
        _render()
    except Exception as e:
        import traceback
        st.error(f"页面渲染出错: {e}")
        with st.expander("详细错误"):
            st.code(traceback.format_exc())


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
        if ds.experiment_design:
            label += " ✓"
        options.append(label)

    selected = st.multiselect(
        "选择实验（至少2个）✓=有设计元数据",
        options,
        default=options,
    )

    if len(selected) < 2:
        st.info("请选择至少2个实验。")
        return

    selected_datasets = [all_datasets[i] for i, opt in enumerate(options) if opt in selected]

    if st.button("开始 DOE 分析", type="primary", use_container_width=True):
        with st.spinner("正在分析实验设计..."):
            result = check_doe_coverage(selected_datasets)
            merged_df = _collect_merged_table(selected_datasets)
            mode_label = "模板模式 (电芯挂测表)" if result.get("mode") == "template" else "通用模式"
            n_with_design = sum(1 for ds in selected_datasets if ds.experiment_design)

            st.session_state["doe_result"] = result
            st.session_state["doe_merged"] = merged_df
            st.session_state["doe_mode"] = mode_label
            st.session_state["doe_n_design"] = n_with_design
            st.session_state["doe_selected_datasets"] = selected_datasets

    if "doe_result" not in st.session_state:
        st.info("点击上方按钮开始分析。")
        return

    result = st.session_state["doe_result"]
    merged_df = st.session_state["doe_merged"]
    mode_label = st.session_state["doe_mode"]
    n_with_design = st.session_state["doe_n_design"]

    tested = result["factors_tested"]
    constant = result["factors_constant"]
    factor_summary = result.get("factor_summary", {})

    tab_overview, tab_factors, tab_heatmap, tab_impact, tab_missing, tab_detail = st.tabs(
        ["📊 总览仪表盘", "🔬 因子详情", "🔥 组合热力图", "📈 衰减影响", "🧩 缺失组合", "📋 详情列表"]
    )

    with tab_overview:
        col1, col2, col3 = st.columns(3)
        col1.metric("实验数量", result["n_experiments"])
        col2.metric("有设计元数据", f"{n_with_design}/{len(selected_datasets)}")
        col3.metric("缺失组合", len(result["missing_combinations"]))
        st.caption(f"分析模式: {mode_label}")

        try:
            st.plotly_chart(_coverage_donut(result["coverage_score"]), use_container_width=True)
        except Exception as e:
            st.error(f"覆盖度图错误: {e}")

        left, right = st.columns(2)
        with left:
            try:
                st.plotly_chart(_factor_status_pie(tested, constant, DOE_ALL_FACTORS), use_container_width=True)
            except Exception as e:
                st.error(f"饼图错误: {e}")
        with right:
            try:
                fig_sun = _sunburst_factors(factor_summary, tested, constant, DOE_FACTOR_GROUPS)
                if fig_sun.data:
                    st.plotly_chart(fig_sun, use_container_width=True)
                else:
                    st.warning("太阳树图无数据")
            except Exception as e:
                st.error(f"太阳树图错误: {e}")

        try:
            st.plotly_chart(_factor_group_bar(factor_summary, tested, constant, DOE_FACTOR_GROUPS), use_container_width=True)
        except Exception as e:
            st.error(f"分组柱状图错误: {e}")
        try:
            st.plotly_chart(_categorical_distribution(factor_summary, tested, DOE_FACTOR_GROUPS), use_container_width=True)
        except Exception as e:
            st.error(f"取值数量图错误: {e}")

    with tab_factors:
        st.subheader("因子详情 (按类别)")
        for group_name, group_factors in DOE_FACTOR_GROUPS.items():
            all_fields = group_factors.get("categorical", []) + group_factors.get("numeric", [])
            tested_in_group = [f for f in all_fields if f in tested]
            constant_in_group = [f for f in all_fields if f in constant]
            missing_in_group = [f for f in all_fields if f not in tested and f not in constant]

            if not all_fields:
                continue

            cols = st.columns(len(all_fields))
            for idx, f in enumerate(all_fields):
                with cols[idx]:
                    info = factor_summary.get(f, {})
                    n_unique = info.get("n_unique", 0)
                    vals = info.get("values", [])
                    if f in tested:
                        st.markdown(f"**✅ {f}**")
                        st.caption(f"{n_unique} 个不同值")
                        for v in vals[:5]:
                            st.markdown(f"`{v}`")
                    elif f in constant:
                        fixed_val = vals[0] if vals else "?"
                        st.markdown(f"**⚪ {f}**")
                        st.caption(f"固定 = `{fixed_val}`")
                    else:
                        st.markdown(f"**❌ {f}**")
                        st.caption("无数据")

        if result["recommendations"]:
            st.divider()
            st.subheader("推荐补充实验")
            for rec in result["recommendations"]:
                color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "")
                st.markdown(f"  {color} {rec['description']}")

    with tab_heatmap:
        from lmbagent.degradation.doe_checker import _collect_design_factors as _cdf
        raw_table = _cdf(selected_datasets)
        st.plotly_chart(_combination_heatmap(factor_summary, raw_table, tested), use_container_width=True)
        st.caption("颜色越绿表示该因子对组合覆盖越完整，越红表示缺失越多。")

    with tab_impact:
        focus_options = ["全部"] + tested
        focus_sel = st.selectbox("选择聚焦因子", focus_options, key="doe_focus_viz")
        focus = None if focus_sel == "全部" else focus_sel

        if st.button("分析因子对衰减的影响", key="doe_impact_btn"):
            with st.spinner("正在计算因子影响..."):
                impact_result = analyze_design_impact(selected_datasets, focus_factor=focus)
                st.session_state["doe_impact"] = impact_result

        if "doe_impact" in st.session_state:
            impact_result = st.session_state["doe_impact"]
            if "error" in impact_result:
                st.error(impact_result["error"])
            else:
                st.plotly_chart(_correlation_bar(merged_df, tested), use_container_width=True)

                parcats_factors = [f for f in tested if f in merged_df.columns and merged_df[f].nunique() > 1]
                selected_parcats = st.multiselect(
                    "选择展示的因子（建议3~6个）",
                    parcats_factors,
                    default=parcats_factors[:5],
                    key="parcats_factor_sel",
                )
                if len(selected_parcats) >= 2:
                    try:
                        fig_pc = _parallel_coordinates(merged_df, tested, selected_factors=selected_parcats)
                        st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e:
                        st.error(f"平行类别图错误: {e}")
                        import traceback
                        with st.expander("详细错误"):
                            st.code(traceback.format_exc())
                else:
                    st.info("请选择至少2个因子。")

                st.subheader("分组箱线图")
                factors_with_variation = [f for f in tested if f in merged_df.columns and merged_df[f].nunique() > 1]
                selected_factor = st.selectbox("选择因子查看衰减分布", factors_with_variation, key="box_factor")
                if selected_factor:
                    fig = _fade_boxplot(merged_df, selected_factor)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)

                for factor, info in impact_result.get("factor_analysis", {}).items():
                    with st.expander(f"**{factor}** 分析结果"):
                        if "interpretation" in info:
                            st.markdown(info["interpretation"])
                        if "groups" in info:
                            gdf = pd.DataFrame([
                                {"值": k, "平均衰减%": v["mean_fade"], "样本数": v["n"]}
                                for k, v in info["groups"].items()
                            ])
                            st.dataframe(gdf, use_container_width=True, hide_index=True)
    with tab_missing:
        combos = result["missing_combinations"]
        if not combos:
            st.success("所有因子组合均已覆盖！")
        else:
            st.subheader(f"缺失的因子组合 (共 {len(combos)} 个)")
            if len(combos) > 0:
                combo_df = pd.DataFrame(combos)
                st.dataframe(combo_df, use_container_width=True, hide_index=True)

            if result["recommendations"]:
                st.divider()
                st.subheader("推荐补充实验")
                rec_df = pd.DataFrame([
                    {"优先级": {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}.get(r["priority"], r["priority"]),
                     "类型": r["type"], "描述": r["description"]}
                    for r in result["recommendations"]
                ])
                st.dataframe(rec_df, use_container_width=True, hide_index=True)

    with tab_detail:
        st.subheader("实验设计矩阵")
        display_df = merged_df.copy()
        show_cols = [c for c in display_df.columns if c in DOE_ALL_FACTORS + ["data_id", "cell_id", "fade_pct"]]
        display_df = display_df[show_cols]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        csv = display_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("下载 CSV", csv, "doe_matrix.csv", "text/csv")
