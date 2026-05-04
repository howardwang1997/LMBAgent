"""Chat page: AI-powered data analysis conversation. Direct core library."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.agent import TOOL_REGISTRY, HANDLER_MAP


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def render_chat_page():
    try:
        _render()
    except Exception as e:
        import streamlit as st
        st.error(f"页面渲染出错: {e}")


def _render():
    store = DataStore()

    st.header("AI 聊天")

    st.markdown("""
    与AI助手对话，使用自然语言分析电池数据。可用工具：
    """)

    with st.expander("可用工具列表"):
        for t in TOOL_REGISTRY:
            st.markdown(f"- **{t['name']}**: {t['description'][:80]}...")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown("**快速指令:**")
    quick_prompts = [
        "加载 data/examples/pec.csv 并分析",
        "列出所有已加载的实验",
        "对比所有实验的容量衰减",
    ]
    cols = st.columns(len(quick_prompts))
    for col, prompt in zip(cols, quick_prompts):
        if col.button(prompt, key=f"quick_{prompt}"):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            _process_prompt(prompt, store)
            st.rerun()

    if prompt := st.chat_input("输入分析指令..."):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        _process_prompt(prompt, store)
        st.rerun()


def _process_prompt(prompt: str, store: DataStore):
    import re

    prompt_lower = prompt.lower()
    tokens = prompt_lower.split()

    try:
        if "加载" in prompt_lower or "load" in prompt_lower:
            file_path = None
            for t in tokens:
                if t.endswith(".csv") or t.endswith(".xlsx") or t.endswith(".npy"):
                    file_path = t
                    break
            if not file_path:
                m = re.search(r'[\w/.]+\.(csv|xlsx|npy)', prompt)
                if m:
                    file_path = m.group(0)

            if file_path:
                handler = HANDLER_MAP["load_battery_data"]
                result = _run_async(handler({"file_path": file_path}))
                response = result["content"][0]["text"]
            else:
                response = "请指定文件路径，例如: 加载 data/examples/pec.csv"

        elif "列出" in prompt_lower or "list" in prompt_lower:
            ids = store.list_ids()
            if ids:
                table = store.list_as_table()
                response = f"已加载 {len(ids)} 个数据集:\n\n"
                for _, row in table.iterrows():
                    response += f"- `{row.get('data_id', '')}` — {row.get('cell_id', '')} ({row.get('cycles', '')} cycles)\n"
            else:
                response = "暂无数据集。请先加载数据。"

        elif "对比" in prompt_lower or "compare" in prompt_lower:
            ids = store.list_ids()
            if len(ids) < 2:
                response = "至少需要2个数据集才能对比。"
            else:
                handler = HANDLER_MAP["compare_experiments"]
                result = _run_async(handler({"data_ids": ",".join(ids)}))
                response = result["content"][0]["text"]

        elif "分析" in prompt_lower or "analyze" in prompt_lower:
            active = st.session_state.get("active_dataset_id")
            if not active:
                ids = store.list_ids()
                active = ids[0] if ids else None
            if active:
                handler = HANDLER_MAP["generate_report"]
                result = _run_async(handler({"data_id": active}))
                response = result["content"][0]["text"]
            else:
                response = "请先加载数据集。"

        elif "退化" in prompt_lower or "degradation" in prompt_lower:
            active = st.session_state.get("active_dataset_id")
            if not active:
                ids = store.list_ids()
                active = ids[0] if ids else None
            if active:
                handler = HANDLER_MAP["analyze_failure_modes"]
                result = _run_async(handler({"data_id": active}))
                response = result["content"][0]["text"]
            else:
                response = "请先加载数据集。"

        else:
            response = (
                f"收到指令: \"{prompt}\"\n\n"
                "我可以执行以下操作:\n"
                "- 加载 <文件路径> — 加载数据\n"
                "- 列出 — 列出所有数据集\n"
                "- 对比 — 对比所有实验\n"
                "- 分析 — 生成分析报告\n"
                "- 退化 — 退化模式分解\n"
            )
    except Exception as e:
        response = f"执行出错: {e}"

    st.session_state.chat_messages.append({"role": "assistant", "content": response})
