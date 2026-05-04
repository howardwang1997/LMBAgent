"""Conclusion management page: create, view, verify conclusions. Direct core library."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.conclusions.models import Conclusion, ConclusionStatus
from lmbagent.conclusions.store import ConclusionStore
from lmbagent.conclusions.verifier import verify_conclusion, verify_all


def render_conclusions_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()
    cs = ConclusionStore(store)

    st.header("结论管理")

    tab_list, tab_add, tab_verify = st.tabs(["结论列表", "新增结论", "验证结论"])

    with tab_list:
        status_filter = st.selectbox(
            "状态筛选",
            ["全部", "active", "supported", "challenged", "superseded", "retracted"],
        )
        filter_status = None if status_filter == "全部" else status_filter
        conclusions = cs.list_all(status=filter_status)

        if not conclusions:
            st.info("暂无结论。")
        else:
            st.caption(f"共 {len(conclusions)} 条结论")
            for c in conclusions:
                icon = {
                    "active": "🟢", "supported": "✅", "challenged": "🔴",
                    "superseded": "⏭️", "retracted": "❌",
                }.get(c.status.value, "?")

                label = f"{icon} [{c.conclusion_id}] {c.statement[:60]}{'...' if len(c.statement) > 60 else ''}"
                with st.expander(label):
                    st.markdown(f"**陈述:** {c.statement}")
                    st.markdown(f"**状态:** {c.status.value} | **置信度:** {c.confidence}")
                    if c.scope:
                        st.markdown(f"**范围:** {c.scope}")
                    if c.evidence_ids:
                        st.markdown(f"**证据:** {', '.join(c.evidence_ids)}")
                    if c.challenged_by:
                        st.markdown(f"**被挑战:** {', '.join(c.challenged_by)}")
                    st.caption(f"创建: {c.created_at} | 更新: {c.updated_at or 'N/A'}")

                    col1, col2 = st.columns(2)
                    with col1:
                        new_status = st.selectbox(
                            "更新状态",
                            [s.value for s in ConclusionStatus],
                            index=[s.value for s in ConclusionStatus].index(c.status.value),
                            key=f"status_{c.conclusion_id}",
                        )
                    with col2:
                        new_conf = st.selectbox(
                            "更新置信度",
                            ["low", "medium", "high"],
                            index=["low", "medium", "high"].index(c.confidence),
                            key=f"conf_{c.conclusion_id}",
                        )

                    if st.button("保存更新", key=f"save_{c.conclusion_id}"):
                        cs.update(c.conclusion_id, status=new_status, confidence=new_conf)
                        st.success("已更新")
                        st.rerun()

                    if st.button("删除", key=f"del_{c.conclusion_id}"):
                        cs.remove(c.conclusion_id)
                        st.success("已删除")
                        st.rerun()

    with tab_add:
        st.subheader("新增结论")
        cid = st.text_input("结论ID (留空自动生成)")
        statement = st.text_area("结论陈述", height=100)
        scope = st.text_input("范围 (如 NMC811|2C|25C)")
        evidence_str = st.text_input("证据数据集ID (逗号分隔)")
        confidence = st.selectbox("置信度", ["low", "medium", "high"], index=1)

        if st.button("添加结论", type="primary"):
            if not statement.strip():
                st.error("请输入结论陈述")
            else:
                from datetime import datetime
                conclusion_id = cid.strip() or f"C-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                conclusion = Conclusion(
                    conclusion_id=conclusion_id,
                    statement=statement.strip(),
                    scope=scope.strip(),
                    evidence_ids=[e.strip() for e in evidence_str.split(",") if e.strip()],
                    confidence=confidence,
                )
                cs.add(conclusion)
                st.success(f"结论已添加: {conclusion_id}")
                st.rerun()

    with tab_verify:
        st.subheader("用新数据验证结论")
        all_ids = store.list_ids()
        if not all_ids:
            st.warning("暂无数据集。")
            return

        options = [f"{did} ({store.get(did).num_cycles} cycles)" for did in all_ids]
        selected = st.selectbox("选择新数据集", options, key="verify_ds")
        data_id = all_ids[options.index(selected)]

        if st.button("验证所有结论", type="primary"):
            results = verify_all(data_id, store=store)
            if not results:
                st.info("无活跃结论需要验证。")
            else:
                for r in results:
                    icon = {"supported": "✅", "challenged": "🔴", "inconclusive": "❓"}.get(r.verdict, "?")
                    st.markdown(f"{icon} **{r.conclusion_id}** → **{r.verdict.upper()}**")
                    st.markdown(f"   {r.evidence_summary}")
                    if r.details:
                        st.caption(f"   {r.details}")
                    st.caption(f"   置信度变化: {r.confidence_change}")
                    st.divider()
