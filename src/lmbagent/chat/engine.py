"""Chat engine: LLM-powered conversation with optional tool calling.

This engine:
1. Maintains conversation history per session
2. Injects long-term memory into the system prompt
3. Sends messages to the LLM with available tools
4. If the LLM decides to call a tool, executes it and continues the loop
5. Returns the final response to display
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Optional

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

import litellm

from lmbagent.agent import TOOL_REGISTRY, HANDLER_MAP
from lmbagent.chat.memory import ChatMemory
from lmbagent.config import get_model_config, DEFAULT_MODEL


SYSTEM_PROMPT_BASE = """\
你是 LMBAgent 的 AI 助手，一个锂电池数据分析专家。你可以：
- 与用户进行自然对话，回答电池、材料、实验相关的问题
- 当需要分析数据时，自动调用工具来加载、分析、对比、可视化数据
- 记住用户告诉你的偏好和重要信息

## 核心能力
1. **日常对话**: 回答电池科学、实验设计、数据分析相关的问题
2. **工具调用**: 当用户的请求涉及具体数据操作时，使用可用工具完成任务
3. **长期记忆**: 你可以记住用户提到的关键信息（实验条件、偏好、研究目标等）

## 可用工具
{tool_descriptions}

## 当前环境
- 已加载数据集数量: {num_datasets}
- 当前选中数据集: {active_dataset}

## 长期记忆
{long_term_memory}

## 工具调用指南
- 只有当用户明确请求数据操作时才调用工具
- 简单的知识问答、讨论、建议等直接回答即可
- 调用工具前，简要说明你将要做什么
- 调用工具后，用自然语言解释结果
- 如果缺少必要信息（如文件路径、数据集ID），先询问用户

## 回答风格
- 使用中文回答（用户使用英文时用英文）
- 专业但易懂，必要时给出具体数值和解释
- 适当使用 Markdown 格式化（表格、列表、加粗等）
"""


def _build_tool_descriptions() -> str:
    lines = []
    for t in TOOL_REGISTRY:
        params_desc = ", ".join(
            f"{k}" for k in t.get("parameters", {}).get("properties", {})
        )
        lines.append(f"- **{t['name']}**({params_desc}): {t['description'][:120]}")
    return "\n".join(lines)


def _to_openai_tool(tool_def: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "parameters": tool_def["parameters"],
        },
    }


def _result_to_text(result: dict[str, Any]) -> str:
    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts) if parts else str(result)


def _needs_memory_extraction(content: str) -> bool:
    memory_keywords = [
        "我的", "我喜欢", "我偏好", "我通常", "我们实验室",
        "记住", "备忘", "别忘了", "我的项目", "我的研究",
        "我们组", "课题组", "我的课题",
    ]
    return any(kw in content for kw in memory_keywords)


def _extract_memory_with_llm(
    user_message: str,
    assistant_response: str,
    model: str,
    config: dict,
) -> dict[str, str] | None:
    prompt = f"""分析以下对话，提取用户提到的值得长期记住的信息。
只提取明确的事实和偏好，不要推测。

用户: {user_message}
助手: {assistant_response}

请以JSON格式返回，每个键值对代表一条记忆。例如:
{{"user_research_topic": "锂金属电池电解液优化", "preferred_temperature": "60℃"}}

如果没有值得记住的信息，返回: {{"_none": true}}
只返回JSON，不要其他文字。"""

    try:
        litellm_model = model
        if config["provider"] in ("GROK", "DEEPSEEK", "HKRI") and config.get("base_url"):
            litellm_model = f"openai/{model}"

        kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": [{"role": "user", "content": prompt}],
            "api_key": config.get("api_key"),
            "timeout": 15,
        }
        if config.get("base_url"):
            kwargs["api_base"] = config["base_url"]

        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content.strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]

        result = json.loads(text)
        if result.get("_none"):
            return None
        result.pop("_none", None)
        return result if result else None
    except Exception:
        return None


async def chat_turn(
    session_id: str,
    user_message: str,
    memory: ChatMemory,
    model: str | None = None,
    active_dataset_id: str | None = None,
    num_datasets: int = 0,
    max_tool_turns: int = 10,
) -> str:
    """Process one user message and return assistant response.

    This function:
    1. Saves user message to memory
    2. Builds system prompt with long-term memory and context
    3. Sends full conversation history to LLM
    4. Handles tool calls in a loop if LLM decides to use tools
    5. Extracts and saves new long-term memories
    6. Saves assistant response to memory
    """
    if model is None:
        model = DEFAULT_MODEL

    config = get_model_config(model)
    litellm_model = model
    if config["provider"] in ("GROK", "DEEPSEEK", "HKRI") and config.get("base_url"):
        litellm_model = f"openai/{model}"

    memory.add_message(session_id, "user", user_message)

    all_memory = memory.get_all_memory()
    memory_text = ""
    if all_memory:
        lines = [f"- **{k}**: {v}" for k, v in all_memory.items()]
        memory_text = "\n".join(lines)
    else:
        memory_text = "（暂无）"

    active_ds = active_dataset_id or "（未选择）"
    tool_descs = _build_tool_descriptions()

    system_prompt = SYSTEM_PROMPT_BASE.format(
        tool_descriptions=tool_descs,
        num_datasets=num_datasets,
        active_dataset=active_ds,
        long_term_memory=memory_text,
    )

    db_messages = memory.get_session_messages(session_id)
    llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in db_messages:
        role = msg["role"]
        if role == "user":
            llm_messages.append({"role": "user", "content": msg["content"]})
        elif role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": msg["content"]}
            if msg["tool_calls"]:
                try:
                    entry["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    pass
            llm_messages.append(entry)
        elif role == "tool":
            llm_messages.append({
                "role": "tool",
                "tool_call_id": msg["tool_call_id"] or "",
                "content": msg["content"],
            })

    tools = [_to_openai_tool(t) for t in TOOL_REGISTRY]

    completion_kwargs: dict[str, Any] = {
        "model": litellm_model,
        "messages": llm_messages,
        "tools": tools,
        "api_key": config.get("api_key"),
        "timeout": 60,
    }
    if config.get("base_url"):
        completion_kwargs["api_base"] = config["base_url"]

    for _ in range(max_tool_turns):
        response = await litellm.acompletion(**completion_kwargs)
        msg = response.choices[0].message

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            tc_list = []
            for tc in msg.tool_calls:
                tc_list.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            assistant_msg["tool_calls"] = tc_list

        llm_messages.append(assistant_msg)
        memory.add_message(
            session_id,
            "assistant",
            msg.content or "",
            tool_calls=json.dumps(assistant_msg.get("tool_calls")) if msg.tool_calls else None,
        )

        if not msg.tool_calls:
            final_response = msg.content or ""

            if _needs_memory_extraction(user_message):
                extracted = _extract_memory_with_llm(
                    user_message, final_response, model, config
                )
                if extracted:
                    for k, v in extracted.items():
                        memory.set_memory(k, v)

            return final_response

        for tc in msg.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            handler = HANDLER_MAP.get(func_name)
            if handler is None:
                tool_result = f"Error: Unknown tool '{func_name}'"
            else:
                result = await handler(func_args)
                tool_result = _result_to_text(result)

            llm_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result,
            })
            memory.add_message(
                session_id, "tool", tool_result, tool_call_id=tc.id
            )

        completion_kwargs["messages"] = llm_messages

    return "抱歉，工具调用次数超出限制，请简化你的请求。"
