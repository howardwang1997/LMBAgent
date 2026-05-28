"""Development coding agent with tool-calling loop.

Implements an opencode-inspired agent loop:
  while step < MAX_STEPS:
    1. Build messages + system prompt (with workspace file listing)
    2. Call LLM (minimax-m2.7 via HKRI)
    3. If no tool_calls -> return text response, break
    4. Execute each tool_call within sandbox
    5. Append tool results to messages
    6. step++

Uses raw requests.post() for LLM calls (same pattern as llm_loader.py).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from lmbagent.config import get_model_config

DEV_MODEL = "minimax-m2.7"
from lmbagent.dev.sandbox import SANDBOX_ROOT, ensure_dirs, workspace_tree
from lmbagent.dev.tools import TOOL_DEFINITIONS, TOOL_HANDLER_MAP

logger = logging.getLogger(__name__)

MAX_STEPS = 20
LLM_TIMEOUT = 120

_DB_PATH = Path.home() / ".lmbagent" / "lmbagent.db"

SYSTEM_PROMPT_TEMPLATE = """You are a sharp, experienced senior Python developer. You work inside the LMBAgent development workspace. You have zero patience for vague instructions and you're not afraid to say so.

## Your Environment
- Working directory: `workspace/` (inside the LMBAgent project)
- You can `import lmbagent` to use the battery data analysis library
- You can read/write files, run commands, and search code
- Uploaded files are in `workspace/uploads/`

## Current Workspace Files
{workspace_tree}

## Personality — NON-NEGOTIABLE

### Be brutally honest
1. **You are the expert.** The user came to you. Lead the conversation, don't follow.
2. **Challenge everything.** If the user's approach is wrong, say "这个方案有问题，因为..." and propose a better one. Don't sugarcoat.
3. **Call out vague requirements.** When a user gives you unclear instructions, do NOT guess and do NOT silently make assumptions. Instead, say: "你的需求不够清楚，我需要你回答以下问题：" then list specific questions.
4. **Never apologize for asking questions.** If the user can't articulate what they want, that's THEIR problem, not yours. Make this clear: "在我开始工作之前，你需要更清楚地告诉我你想要什么。"
5. **Push back on bad ideas.** If the user wants to do something the hard way, say "我不建议这样做。更好的方式是..." and explain why.

### Ask before you act
6. **ALWAYS ask 2-3 clarifying questions before any non-trivial task.** Examples:
   - "你期望的输出是什么格式？"
   - "这个脚本是只用一次还是要复用？"
   - "你有没有考虑过用 X 方法代替？效果更好。"
   - "你的数据量大概多大？这影响我选的实现方案。"
7. **If the requirement is ambiguous, STOP and ask.** Don't proceed with assumptions.
8. **After asking, wait for the user's response.** Don't answer your own questions.

### Direct communication style
9. **No flattery.** Don't say "好的！" "没问题！" "很好的想法！" unless you genuinely mean it.
10. **Say what you think.** If a task is trivial, just do it. If it's complex, explain your plan first.
11. **Be concise but thorough.** Don't write essays, but don't skip important details either.

## Technical Rules
1. **Always write code to files** — don't just describe it. Use `write_file` or `edit_file`.
2. **Test your code** — use `run_command` to execute scripts and verify they work.
3. **Fix errors iteratively** — if a script fails, read the error, edit the file, and try again.
4. **Only use `ask_user` tool** when you are truly stuck after multiple attempts. For normal questions, just include them in your response.
5. **Be concise** — write clean, well-structured code. No unnecessary comments.
6. **Use lmbagent** — when analyzing battery data, use `from lmbagent.data.store import DataStore` etc.
7. **Respect the sandbox** — you can only work within `workspace/`. Don't try to access files outside it.
8. **Respond in the user's language** — Chinese or English as appropriate.

## Workflow
- For new scripts: ASK clarifying questions → wait for answers → `write_file` → `run_command` → iterate
- For debugging: ASK about expected behavior → `read_file` → `edit_file` → `run_command` → iterate
- For data analysis: ASK what metrics/comparisons → `list_files` → write script → run it
- When truly stuck: `ask_user` with specific question and context
"""


def extract_thinking(content: str) -> tuple[str, str]:
    """Separate model thinking from actual response content.

    minimax-m2.7 uses format: <think\n...thinking...\n</think\n\n...response...

    Returns (thinking_text, clean_content).
    """
    if not content:
        return "", ""

    m = re.match(r"<think\b(.*?)</think\b(.*)", content, re.DOTALL)
    if m:
        thinking = m.group(1).strip()
        clean = m.group(2).strip()
        return thinking, clean

    return "", content


def _get_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dev_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            context TEXT DEFAULT '',
            answer TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            resolved_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dev_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dev_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT DEFAULT '',
            thinking TEXT DEFAULT '',
            tool_calls TEXT DEFAULT '',
            tool_call_id TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (session_id) REFERENCES dev_sessions(id)
        )
    """)
    conn.commit()
    return conn


def log_requirement(question: str, context: str = "") -> int:
    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO dev_requirements (question, context, status) VALUES (?, ?, 'pending')",
        (question, context),
    )
    conn.commit()
    req_id = cur.lastrowid
    conn.close()
    return req_id


def update_requirement(req_id: int, answer: str, status: str = "answered") -> None:
    conn = _get_db()
    conn.execute(
        "UPDATE dev_requirements SET answer=?, status=?, resolved_at=datetime('now','localtime') WHERE id=?",
        (answer, status, req_id),
    )
    conn.commit()
    conn.close()


def list_requirements(status: Optional[str] = None) -> list[dict]:
    conn = _get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM dev_requirements WHERE status=? ORDER BY id DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM dev_requirements ORDER BY id DESC",
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_session(title: str = "新对话") -> int:
    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO dev_sessions (title) VALUES (?)", (title,)
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def list_sessions() -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM dev_sessions ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_session(session_id: int) -> None:
    conn = _get_db()
    conn.execute("DELETE FROM dev_messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM dev_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()


def save_messages(session_id: int, messages: list[dict]) -> None:
    conn = _get_db()
    conn.execute("DELETE FROM dev_messages WHERE session_id=?", (session_id,))
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        thinking = msg.get("thinking", "")
        tc_json = json.dumps(msg.get("tool_calls", []), ensure_ascii=False) if msg.get("tool_calls") else ""
        tc_id = msg.get("tool_call_id", "")
        conn.execute(
            "INSERT INTO dev_messages (session_id, role, content, thinking, tool_calls, tool_call_id) VALUES (?,?,?,?,?,?)",
            (session_id, role, content, thinking, tc_json, tc_id),
        )
    conn.execute(
        "UPDATE dev_sessions SET updated_at=datetime('now','localtime') WHERE id=?",
        (session_id,),
    )
    conn.commit()
    conn.close()


def load_messages(session_id: int) -> list[dict]:
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM dev_messages WHERE session_id=? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    messages = []
    for r in rows:
        msg = {"role": r["role"], "content": r["content"]}
        if r["thinking"]:
            msg["thinking"] = r["thinking"]
        if r["tool_calls"]:
            try:
                msg["tool_calls"] = json.loads(r["tool_calls"])
            except json.JSONDecodeError:
                pass
        if r["tool_call_id"]:
            msg["tool_call_id"] = r["tool_call_id"]
        messages.append(msg)
    return messages


def update_session_title(session_id: int, title: str) -> None:
    conn = _get_db()
    conn.execute("UPDATE dev_sessions SET title=? WHERE id=?", (title, session_id))
    conn.commit()
    conn.close()


def _call_llm(messages: list[dict], tools: list[dict]) -> dict:
    config = get_model_config(DEV_MODEL)
    base_url = config.get("base_url", "").rstrip("/")
    api_key = config.get("api_key")

    payload = {
        "model": DEV_MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    resp = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _build_system_prompt() -> str:
    ensure_dirs()
    tree = workspace_tree()
    return SYSTEM_PROMPT_TEMPLATE.format(workspace_tree=tree)


def run_dev_agent(
    user_message: str,
    history: Optional[list[dict]] = None,
    uploaded_files: Optional[list[str]] = None,
) -> dict:
    """Run the development agent loop.

    Args:
        user_message: The user's request.
        history: Previous conversation messages.
        uploaded_files: List of uploaded file names in workspace/uploads/.

    Returns:
        Dict with:
        - 'response': final text response
        - 'messages': full message history (for next turn)
        - 'ask_user': dict with question/context if agent asked user, else None
        - 'steps': number of tool-calling steps used
    """
    ensure_dirs()

    messages = list(history) if history else []

    user_content = user_message
    if uploaded_files:
        files_str = ", ".join(f"uploads/{f}" for f in uploaded_files)
        user_content += f"\n\n[已上传文件: {files_str}]"

    messages.append({"role": "user", "content": user_content})

    system_prompt = _build_system_prompt()

    full_messages = [{"role": "system", "content": system_prompt}] + messages
    ask_user_result = None

    for step in range(MAX_STEPS):
        try:
            result = _call_llm(full_messages, TOOL_DEFINITIONS)
        except requests.exceptions.Timeout:
            return {
                "response": "LLM 请求超时，请稍后重试。",
                "messages": messages,
                "ask_user": None,
                "steps": step,
            }
        except Exception as e:
            return {
                "response": f"LLM 调用出错: {e}",
                "messages": messages,
                "ask_user": None,
                "steps": step,
            }

        choice = result["choices"][0]
        msg = choice["message"]
        finish_reason = choice.get("finish_reason", "")

        if "tool_calls" not in msg or not msg["tool_calls"]:
            raw_text = msg.get("content", "")
            thinking, clean_text = extract_thinking(raw_text)
            stored = {"role": "assistant", "content": clean_text}
            if thinking:
                stored["thinking"] = thinking
            messages.append(stored)
            return {
                "response": clean_text,
                "thinking": thinking,
                "messages": messages,
                "ask_user": ask_user_result,
                "steps": step + 1,
            }

        tool_calls = msg["tool_calls"]
        raw_content = msg.get("content", "")
        thinking, clean_content = extract_thinking(raw_content)
        assistant_msg = {"role": "assistant", "content": clean_content}
        if thinking:
            assistant_msg["thinking"] = thinking
        assistant_msg["tool_calls"] = []
        for tc in tool_calls:
            assistant_msg["tool_calls"].append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                },
            })
        messages.append(assistant_msg)
        full_messages.append(assistant_msg)

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            func_args_str = tc["function"]["arguments"]
            tool_call_id = tc["id"]

            try:
                func_args = json.loads(func_args_str)
            except json.JSONDecodeError:
                func_args = {}

            handler = TOOL_HANDLER_MAP.get(func_name)
            if handler is None:
                tool_result = f"Unknown tool: {func_name}"
            else:
                try:
                    tool_result = handler(func_args)
                except ValueError as e:
                    tool_result = f"ValidationError: {e}"
                except Exception as e:
                    tool_result = f"Error: {type(e).__name__}: {e}"

            if func_name == "ask_user":
                try:
                    parsed = json.loads(tool_result)
                    if parsed.get("action") == "ask_user":
                        log_requirement(parsed["question"], parsed.get("context", ""))
                        ask_user_result = {
                            "question": parsed["question"],
                            "context": parsed.get("context", ""),
                            "tool_call_id": tool_call_id,
                        }
                except (json.JSONDecodeError, KeyError):
                    pass

            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result,
            }
            messages.append(tool_msg)
            full_messages.append(tool_msg)

    return {
        "response": f"达到最大步骤数 ({MAX_STEPS})，任务可能未完成。请继续描述你的需求。",
        "thinking": "",
        "messages": messages,
        "ask_user": ask_user_result,
        "steps": MAX_STEPS,
    }
