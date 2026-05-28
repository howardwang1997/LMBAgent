"""Development workspace page: coding agent with sandbox, file upload, and requirements tracking."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_project_root = str(Path(__file__).parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import streamlit as st

from lmbagent.dev.agent import (
    run_dev_agent,
    list_requirements,
    update_requirement,
    create_session,
    list_sessions,
    delete_session,
    save_messages,
    load_messages,
    update_session_title,
)
from lmbagent.dev.sandbox import (
    SANDBOX_ROOT,
    UPLOAD_DIR,
    ensure_dirs,
    workspace_tree,
    validate_file_size,
)
from lmbagent.dev.scheduler import manual_commit_push


def render_dev_page():
    try:
        _render()
    except Exception as e:
        st.error(f"页面渲染出错: {e}")


def _render():
    ensure_dirs()

    if "dev_processing" not in st.session_state:
        st.session_state.dev_processing = False
    if "dev_uploads" not in st.session_state:
        st.session_state.dev_uploads = []
    if "dev_uploaded_names" not in st.session_state:
        st.session_state.dev_uploaded_names = set()

    _init_session()

    st.header("🛠️ 开发工作台")

    tab_chat, tab_files, tab_reqs = st.tabs(["💬 对话", "📁 文件管理", "📋 需求记录"])

    with tab_chat:
        _render_chat()

    with tab_files:
        _render_files()

    with tab_reqs:
        _render_requirements()


def _init_session():
    if "dev_session_id" not in st.session_state:
        sessions = list_sessions()
        if sessions:
            st.session_state.dev_session_id = sessions[0]["id"]
        else:
            st.session_state.dev_session_id = create_session("新对话")

    if "dev_messages" not in st.session_state:
        st.session_state.dev_messages = load_messages(st.session_state.dev_session_id)


def _render_chat():
    col_chat, col_side = st.columns([3, 1])

    with col_side:
        st.subheader("📎 上传文件")
        uploaded = st.file_uploader(
            "上传文件到 workspace/uploads/",
            accept_multiple_files=True,
            key="dev_file_upload",
        )
        if uploaded:
            new_count = 0
            for f in uploaded:
                if f.name not in st.session_state.dev_uploaded_names:
                    validate_file_size(f.size)
                    dest = UPLOAD_DIR / f.name
                    dest.write_bytes(f.getbuffer())
                    st.session_state.dev_uploads.append(f.name)
                    st.session_state.dev_uploaded_names.add(f.name)
                    new_count += 1
            if new_count > 0:
                st.success(f"新增 {new_count} 个文件")
            else:
                st.caption("所有文件已上传过")

        if st.session_state.dev_uploaded_names:
            with st.expander(f"已上传 {len(st.session_state.dev_uploaded_names)} 个文件"):
                for name in sorted(st.session_state.dev_uploaded_names):
                    st.text(name)

        st.divider()

        st.subheader("💾 对话")
        if st.button("➕ 新建对话", use_container_width=True):
            sid = create_session("新对话")
            st.session_state.dev_session_id = sid
            st.session_state.dev_messages = []
            st.rerun()

        sessions = list_sessions()
        for s in sessions[:10]:
            is_active = s["id"] == st.session_state.dev_session_id
            col1, col2 = st.columns([4, 1])
            with col1:
                label = f"{'👉 ' if is_active else ''}{s['title'][:18]}"
                if st.button(label, key=f"sel_{s['id']}", use_container_width=True):
                    st.session_state.dev_session_id = s["id"]
                    st.session_state.dev_messages = load_messages(s["id"])
                    st.rerun()
            with col2:
                if st.button("🗑", key=f"del_s_{s['id']}"):
                    delete_session(s["id"])
                    if is_active:
                        remaining = list_sessions()
                        if remaining:
                            st.session_state.dev_session_id = remaining[0]["id"]
                            st.session_state.dev_messages = load_messages(remaining[0]["id"])
                        else:
                            st.session_state.dev_session_id = create_session("新对话")
                            st.session_state.dev_messages = []
                    st.rerun()

        st.divider()

        if st.button("🔄 刷新 Workspace", use_container_width=True):
            st.rerun()

        if st.button("📤 Git Commit & Push", use_container_width=True):
            with st.spinner("提交中..."):
                result = manual_commit_push()
            st.info(result)

        st.divider()
        st.subheader("Workspace")
        tree = workspace_tree()
        st.code(tree, language="")

        st.divider()
        quick_actions = [
            ("🐍 创建分析脚本", "创建一个 Python 脚本来分析电池循环数据。"),
            ("📊 数据可视化", "创建可视化脚本，画出容量衰减曲线。"),
            ("🧪 运行测试", "列出 workspace 中所有 .py 文件并逐一运行。"),
            ("📦 安装依赖", "安装需要的 Python 包。"),
        ]
        for label, prompt in quick_actions:
            if st.button(label, key=f"qk_{label}", use_container_width=True):
                st.session_state["_dev_pending"] = prompt
                st.rerun()

    with col_chat:
        messages = st.session_state.dev_messages

        if not messages:
            st.info(
                "👋 这是开发工作台，AI 助手可以帮你：\n\n"
                "- 📝 **编写脚本** — 数据分析、可视化、自动化\n"
                "- 🔧 **调试代码** — 读取错误、修复、重新运行\n"
                "- 📦 **管理文件** — 上传数据、组织工作目录\n"
                "- ❓ **提问求助** — 遇到难题时描述需求\n\n"
                "直接输入你的需求开始！"
            )

        _render_messages(messages)

        prompt = st.chat_input("描述你的需求...")

        if prompt and not st.session_state.dev_processing:
            _handle_user_message(prompt)
        elif st.session_state.get("_dev_pending"):
            prompt = st.session_state.pop("_dev_pending")
            _handle_user_message(prompt)


def _render_messages(messages: list[dict]):
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        thinking = msg.get("thinking", "")
        if not content and not thinking:
            continue
        if role == "user":
            with st.chat_message("user"):
                st.markdown(content)
        elif role == "assistant":
            with st.chat_message("assistant"):
                if thinking:
                    with st.expander("💭 思考过程", expanded=False):
                        st.markdown(thinking)
                if content:
                    st.markdown(content)
        elif role == "tool":
            with st.chat_message("assistant"):
                with st.expander("🔧 工具执行结果", expanded=False):
                    st.code(content[:3000], language="text")


def _handle_user_message(prompt: str):
    st.session_state.dev_processing = True

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("🤖 正在工作..."):
            t0 = time.time()
            try:
                result = run_dev_agent(
                    user_message=prompt,
                    history=st.session_state.dev_messages,
                    uploaded_files=st.session_state.get("dev_uploads", []),
                )
                elapsed = time.time() - t0

                st.session_state.dev_messages = result["messages"]
                st.session_state.dev_uploads = []

                save_messages(st.session_state.dev_session_id, result["messages"])

                existing = load_messages(st.session_state.dev_session_id)
                if len(existing) <= 4:
                    title = prompt[:30] + ("..." if len(prompt) > 30 else "")
                    update_session_title(st.session_state.dev_session_id, title)

                if result.get("ask_user"):
                    q = result["ask_user"]["question"]
                    ctx = result["ask_user"].get("context", "")
                    st.warning(f"**Agent 需要你的帮助:** {q}")
                    if ctx:
                        st.caption(f"上下文: {ctx}")

                if result.get("thinking"):
                    with st.expander("💭 思考过程", expanded=False):
                        st.markdown(result["thinking"])

                st.markdown(result["response"])
                st.caption(f"⏱ {elapsed:.1f}s | {result['steps']} 步")

            except Exception as e:
                st.error(f"Agent 出错: {e}")
                st.session_state.dev_messages.append(
                    {"role": "assistant", "content": f"抱歉，处理出错: {e}"}
                )
                save_messages(st.session_state.dev_session_id, st.session_state.dev_messages)

    st.session_state.dev_processing = False
    st.rerun()


def _render_files():
    col_upload, col_tree = st.columns(2)

    with col_upload:
        st.subheader("上传文件")
        uploaded = st.file_uploader(
            "选择文件（最大 20MB）",
            accept_multiple_files=True,
            key="dev_file_upload_2",
        )
        if uploaded:
            new_count = 0
            for f in uploaded:
                if f.name not in st.session_state.dev_uploaded_names:
                    validate_file_size(f.size)
                    dest = UPLOAD_DIR / f.name
                    dest.write_bytes(f.getbuffer())
                    st.session_state.dev_uploaded_names.add(f.name)
                    new_count += 1
            if new_count > 0:
                st.success(f"新增 {new_count} 个文件到 workspace/uploads/")
                st.rerun()
            else:
                st.caption("所有文件已上传过")

    with col_tree:
        st.subheader("Workspace 目录")
        tree = workspace_tree()
        st.code(tree, language="")

    st.divider()
    st.subheader("文件浏览")

    import pandas as pd
    from lmbagent.dev.sandbox import list_workspace_files

    files = list_workspace_files()
    if files:
        df = pd.DataFrame(files)
        df["size_kb"] = df["size"].apply(lambda x: f"{x / 1024:.1f} KB")
        df["modified"] = df["modified"].apply(lambda x: time.strftime("%Y-%m-%d %H:%M", time.localtime(x)))
        df = df.rename(columns={"path": "文件路径", "size_kb": "大小", "modified": "修改时间"})
        st.dataframe(df[["文件路径", "大小", "修改时间"]], hide_index=True, use_container_width=True)

        selected = st.selectbox("预览文件", [""] + [f["path"] for f in files])
        if selected:
            from lmbagent.dev.sandbox import validate_path

            fpath = validate_path(selected, must_exist=True)
            size = fpath.stat().st_size
            if size > 100_000:
                st.warning(f"文件较大 ({size / 1024:.1f} KB)，仅显示前 200 行")
                text = fpath.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()[:200]
                st.code("\n".join(lines), language="python")
            else:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                suffix = fpath.suffix.lower()
                lang = {
                    ".py": "python",
                    ".js": "javascript",
                    ".json": "json",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                    ".md": "markdown",
                    ".csv": "csv",
                    ".html": "html",
                    ".css": "css",
                    ".sql": "sql",
                    ".sh": "bash",
                }.get(suffix, "text")
                st.code(text, language=lang)
    else:
        st.info("Workspace 为空。上传文件或让 Agent 创建脚本。")


def _render_requirements():
    st.subheader("📋 需求记录")

    st.markdown(
        "当 Coding Agent 遇到无法自动解决的问题时，会将需求记录在此，等待人工处理。"
    )

    reqs = list_requirements()
    if not reqs:
        st.success("暂无待处理需求")
        return

    for req in reqs:
        status = req["status"]
        status_icon = {"pending": "🟡", "answered": "🟢", "escalated": "🔴"}.get(status, "⚪")

        with st.expander(f"{status_icon} [{status.upper()}] #{req['id']} — {req['question'][:60]}"):
            st.markdown(f"**问题:** {req['question']}")
            if req["context"]:
                st.markdown(f"**上下文:** {req['context']}")
            st.caption(f"创建时间: {req['created_at']}")

            if req["answer"]:
                st.markdown(f"**回答:** {req['answer']}")
                if req["resolved_at"]:
                    st.caption(f"解决时间: {req['resolved_at']}")

            if status == "pending":
                col1, col2 = st.columns(2)
                with col1:
                    answer = st.text_input("回答", key=f"ans_{req['id']}")
                    if st.button("提交回答", key=f"submit_{req['id']}"):
                        if answer:
                            update_requirement(req["id"], answer, "answered")
                            st.success("已提交")
                            st.rerun()
                        else:
                            st.warning("请输入回答")
                with col2:
                    if st.button("标记需人工处理", key=f"escalate_{req['id']}"):
                        update_requirement(req["id"], "", "escalated")
                        st.warning("已标记为需人工处理")
                        st.rerun()

            elif status == "escalated":
                answer = st.text_input("人工回答", key=f"manual_{req['id']}")
                if st.button("解决", key=f"resolve_{req['id']}"):
                    if answer:
                        update_requirement(req["id"], answer, "answered")
                        st.success("已解决")
                        st.rerun()
