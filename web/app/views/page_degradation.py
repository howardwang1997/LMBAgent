"""Streamlit page: degradation analysis."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.data.transformer import add_cycle_summary
from lmbagent.degradation.decomposition import (
    decompose_degradation_modes,
    plot_decomposition,
    format_decomposition_summary,
)
from lmbagent.degradation.signatures import MODE_DESCRIPTIONS


def render_degradation_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    st.header("退化分析")

    store = DataStore()
    all_ids = store.list_ids()

    if not all_ids:
        st.warning("请先加载数据。")
        return

    options = []
    for did in all_ids:
        ds = store.get(did)
        label = f"{ds.cell_id or ds.data_id}"
        if ds.chemistry:
            label += f" ({ds.chemistry})"
        label += f" — {ds.num_cycles} cycles"
        options.append(label)

    all_datasets = [store.get(did) for did in all_ids]
    selected = st.selectbox("选择实验", options, key="deg_select")

    if not selected:
        return

    ds = all_datasets[options.index(selected)]
    if ds.cycle_summary.empty:
        ds = add_cycle_summary(ds)
        store.put(ds)

    if st.button("运行退化模式分解"):
        with st.spinner("正在分解退化模式..."):
            result = decompose_degradation_modes(ds)

            if "error" in result:
                st.error(result["error"])
                return

            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                path = plot_decomposition(result, output_path=Path(tmpdir) / "decomp.png")
                st.image(path, width="stretch")

            summary = format_decomposition_summary(result)
            st.markdown(f"```\n{summary}\n```")

            st.subheader("退化模式贡献占比")
            contribs = result["mode_contributions"]
            sorted_contribs = sorted(contribs.items(), key=lambda x: -x[1])
            for name, pct in sorted_contribs:
                desc = MODE_DESCRIPTIONS.get(name, "")
                st.progress(min(pct / 100, 1.0), text=f"**{name}**: {pct:.1f}% — {desc}")
