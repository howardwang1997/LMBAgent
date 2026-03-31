"""Chat page: AI-powered battery data analysis assistant."""

from __future__ import annotations

import streamlit as st
from web.app.utils.api_client import chat_message, chat_stream_iter


def render_chat_page():
    """Render the AI chat interface."""
    st.header("🤖 AI 分析助手")

    # Dataset selection
    data_id = st.session_state.get("active_dataset_id")

    col1, col2 = st.columns([3, 1])

    with col1:
        st.caption("与电池数据分析助手对话，支持自然语言查询")

    with col2:
        if data_id:
            st.info(f"数据集: `{data_id}`")
        else:
            st.warning("未选择数据集")

    st.divider()

    # Chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                # Show tool usage if any
                if msg.get("tools_used"):
                    st.caption(f"🔧 使用工具: {', '.join(msg['tools_used'])}")
            st.markdown(msg["content"])

    # Suggested prompts
    if not st.session_state.messages:
        st.subheader("💡 试试这些问题")

        suggestions = [
            "分析容量衰减趋势",
            "库仑效率如何变化？",
            "生成所有图表",
            "这个电池的健康状况如何？",
            "对比前 5 个循环的性能",
        ]

        for suggestion in suggestions:
            if st.button(suggestion, key=f"suggest_{suggestion}"):
                st.session_state.prompt_input = suggestion
                st.rerun()

    # Chat input
    if prompt := st.chat_input("输入您的问题...") or st.session_state.pop("prompt_input", None):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get assistant response
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    # Use streaming for better UX
                    response_placeholder = st.empty()
                    full_response = ""
                    tools_used = []

                    for chunk in chat_stream_iter(prompt, data_id):
                        chunk_type = chunk.get("type")

                        if chunk_type == "content":
                            content = chunk.get("content", "")
                            full_response += content
                            response_placeholder.markdown(full_response)

                        elif chunk_type == "tool":
                            tool_name = chunk.get("tool_name")
                            tools_used.append(tool_name)
                            st.caption(f"🔧 执行: {tool_name}")

                        elif chunk_type == "error":
                            response_placeholder.error(chunk.get("error", "Unknown error"))
                            full_response = f"❌ 错误: {chunk.get('error', 'Unknown error')}"

                        elif chunk_type == "done":
                            break

                    # Add assistant message to history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "tools_used": tools_used,
                    })

                except Exception as e:
                    error_msg = f"❌ 发生错误: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg,
                    })

    # Clear history button
    if st.session_state.messages:
        st.divider()
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if st.button("🗑️ 清空对话", use_container_width=True):
                st.session_state.messages = []
                st.rerun()
        with col2:
            if st.button("📥 导出对话", use_container_width=True):
                import json
                st.download_button(
                    "下载 JSON",
                    json.dumps(st.session_state.messages, ensure_ascii=False, indent=2),
                    "chat_history.json",
                    "application/json",
                )
