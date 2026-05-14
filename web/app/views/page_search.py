"""Historical search page: find similar/contrastive experiments. Direct core library."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.search.engine import SearchEngine


def render_search_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()
    all_ids = store.list_ids()

    st.header("历史检索")

    if not all_ids:
        st.warning("暂无数据集。请先加载数据。")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        options = [f"{did} ({store.get(did).num_cycles} cycles)" for did in all_ids]
        selected = st.selectbox("查询数据集", options)
        query_id = all_ids[options.index(selected)]
    with col2:
        mode = st.selectbox("搜索模式", ["相似搜索", "对比搜索"])
        top_k = st.slider("返回数量", 1, 10, 5)

    search_mode = "similar" if mode == "相似搜索" else "contrast"

    if st.button("搜索", type="primary"):
        engine = SearchEngine(store)
        results = engine.search_similar(query_id, mode=search_mode, top_k=top_k)

        if not results:
            st.info("未找到匹配结果。")
            return

        for i, r in enumerate(results):
            ds = store.get(r.data_id)
            label = f"#{i+1} `{r.data_id}`"
            if ds:
                label += f" — {ds.cell_id or ''} ({ds.num_cycles} cycles)"

            with st.expander(label, expanded=(i == 0)):
                col_a, col_b = st.columns(2)
                col_a.metric("综合得分", f"{r.score:.3f}")
                if r.design_similarity > 0.001:
                    col_b.metric("设计相似度", f"{r.design_similarity:.2f}")
                else:
                    col_b.metric("设计相似度", "—")

                if r.degradation_similarity > 0.001:
                    st.metric("退化相似度", f"{r.degradation_similarity:.2f}")

                st.markdown(f"**原因:** {r.reason}")

                if ds and not ds.cycle_summary.empty:
                    with st.expander("查看数据集详情"):
                        st.dataframe(ds.cycle_summary.describe(), width="stretch")

    st.divider()
    st.subheader("关键词搜索")
    keyword = st.text_input("输入关键词 (如 chemistry, cell_id)")
    if keyword:
        engine = SearchEngine(store)
        results = engine.search_by_description(keyword, top_k=10)
        if results:
            for r in results:
                st.markdown(f"- `{r.data_id}` — {r.reason}")
        else:
            st.info("未找到匹配数据集。")
