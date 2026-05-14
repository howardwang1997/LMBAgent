"""Chat page: AI-powered chatbot with tool calling and long-term memory."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.data.store import DataStore
from lmbagent.chat.memory import ChatMemory
from lmbagent.chat.engine import chat_turn


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
    memory = ChatMemory()

    st.header("💬 AI 聊天")

    _init_session_state(memory)

    col_sessions, col_chat = st.columns([1, 3])

    with col_sessions:
        _render_sidebar(memory)

    with col_chat:
        _render_chat_area(store, memory)


def _init_session_state(memory: ChatMemory):
    if "chat_current_session" not in st.session_state:
        sessions = memory.list_sessions()
        if sessions:
            st.session_state.chat_current_session = sessions[0]["session_id"]
        else:
            sid = memory.create_session("新对话")
            st.session_state.chat_current_session = sid

    if "chat_processing" not in st.session_state:
        st.session_state.chat_processing = False


def _render_sidebar(memory: ChatMemory):
    st.subheader("对话历史")

    if st.button("➕ 新建对话", use_container_width=True):
        sid = memory.create_session("新对话")
        st.session_state.chat_current_session = sid
        st.rerun()

    sessions = memory.list_sessions()
    for s in sessions:
        col1, col2 = st.columns([4, 1])
        is_active = s["session_id"] == st.session_state.chat_current_session
        with col1:
            label = f"{'👉 ' if is_active else ''}{s['title'][:20]}"
            if st.button(label, key=f"sel_{s['session_id']}", use_container_width=True):
                st.session_state.chat_current_session = s["session_id"]
                st.rerun()
        with col2:
            if st.button("🗑", key=f"del_{s['session_id']}"):
                memory.delete_session(s["session_id"])
                if is_active:
                    remaining = memory.list_sessions()
                    if remaining:
                        st.session_state.chat_current_session = remaining[0]["session_id"]
                    else:
                        st.session_state.chat_current_session = memory.create_session("新对话")
                st.rerun()

    st.divider()

    st.subheader("长期记忆")
    all_mem = memory.get_all_memory()
    if all_mem:
        for k, v in all_mem.items():
            st.markdown(f"**{k}**: {v}")
        if st.button("清除所有记忆"):
            memory.clear_memory()
            st.rerun()
    else:
        st.caption("暂无长期记忆")


def _render_chat_area(store: DataStore, memory: ChatMemory):
    session_id = st.session_state.chat_current_session

    messages = memory.get_session_messages(session_id)

    if not messages:
        st.info(
            "👋 你好！我是 LMBAgen AI 助手。\n\n"
            "你可以：\n"
            "- 📊 **分析数据**：加载文件、生成报告、对比实验\n"
            "- 💡 **讨论问题**：电池科学、实验设计、数据分析方法\n"
            "- 🧠 **记住信息**：告诉我你的研究课题和偏好，我会长期记住\n\n"
            "直接输入任何问题或指令即可开始！"
        )

    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        elif role == "assistant":
            with st.chat_message("assistant"):
                st.markdown(content)
        elif role == "tool":
            with st.chat_message("assistant"):
                with st.expander("🔧 工具调用结果", expanded=False):
                    st.code(content[:2000], language="text")

    active_dataset_id = st.session_state.get("active_dataset_id")
    num_datasets = len(store.list_ids())

    col_input = st.columns([6, 1])
    with col_input[0]:
        prompt = st.chat_input("输入消息...")

    if prompt and not st.session_state.chat_processing:
        st.session_state.chat_processing = True

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    response = _run_async(
                        chat_turn(
                            session_id=session_id,
                            user_message=prompt,
                            memory=memory,
                            active_dataset_id=active_dataset_id,
                            num_datasets=num_datasets,
                        )
                    )
                    st.markdown(response)
                except Exception as e:
                    response = f"抱歉，处理出错: {e}"
                    st.error(response)
                    memory.add_message(session_id, "assistant", response)

        if len(messages) == 0:
            title = prompt[:30] + ("..." if len(prompt) > 30 else "")
            memory.update_session_title(session_id, title)

        st.session_state.chat_processing = False
        st.rerun()

    st.divider()
    with st.expander("快捷指令"):
        quick_prompts = [
            "📊 列出所有已加载的数据集",
            "📈 分析当前选中数据集的性能",
            "⚖️ 对比所有实验的容量衰减",
            "🔍 当前数据集的退化模式分析",
            "💡 如何提高锂金属电池的循环寿命？",
            "🧠 记住：我正在研究60℃下LFP电池的电解液优化",
        ]
        cols = st.columns(3)
        for i, qp in enumerate(quick_prompts):
            with cols[i % 3]:
                if st.button(qp, key=f"quick_{i}", use_container_width=True):
                    clean_prompt = qp.split(" ", 1)[-1] if " " in qp else qp
                    st.session_state["_pending_prompt"] = clean_prompt
                    st.rerun()

    if "_pending_prompt" in st.session_state:
        pp = st.session_state.pop("_pending_prompt")
        st.session_state.chat_processing = True

        with st.chat_message("user"):
            st.markdown(pp)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    response = _run_async(
                        chat_turn(
                            session_id=session_id,
                            user_message=pp,
                            memory=memory,
                            active_dataset_id=active_dataset_id,
                            num_datasets=num_datasets,
                        )
                    )
                    st.markdown(response)
                except Exception as e:
                    response = f"抱歉，处理出错: {e}"
                    st.error(response)
                    memory.add_message(session_id, "assistant", response)

        existing = memory.get_session_messages(session_id)
        if len(existing) <= 2:
            title = pp[:30] + ("..." if len(pp) > 30 else "")
            memory.update_session_title(session_id, title)

        st.session_state.chat_processing = False
        st.rerun()
