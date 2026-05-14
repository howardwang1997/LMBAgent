"""Tests for chat memory and engine."""

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def memory(tmp_path):
    from lmbagent.chat.memory import ChatMemory
    ChatMemory._instance = None
    db_path = tmp_path / "test_chat.db"
    m = ChatMemory(db_path=str(db_path))
    yield m
    m._conn.close()
    ChatMemory._instance = None


class TestChatMemory:
    def test_create_session(self, memory):
        sid = memory.create_session("Test Chat")
        sessions = memory.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == sid
        assert sessions[0]["title"] == "Test Chat"

    def test_add_and_get_messages(self, memory):
        sid = memory.create_session("Chat")
        memory.add_message(sid, "user", "Hello")
        memory.add_message(sid, "assistant", "Hi there!")

        msgs = memory.get_session_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi there!"

    def test_delete_session(self, memory):
        sid = memory.create_session("Delete Me")
        memory.add_message(sid, "user", "test")
        memory.delete_session(sid)
        assert memory.list_sessions() == []
        assert memory.get_session_messages(sid) == []

    def test_update_session_title(self, memory):
        sid = memory.create_session("Old Title")
        memory.update_session_title(sid, "New Title")
        sessions = memory.list_sessions()
        assert sessions[0]["title"] == "New Title"

    def test_long_term_memory(self, memory):
        memory.set_memory("user_topic", "LMB electrolyte optimization")
        assert memory.get_memory("user_topic") == "LMB electrolyte optimization"
        assert memory.get_memory("nonexistent") is None

    def test_get_all_memory(self, memory):
        memory.set_memory("key1", "val1")
        memory.set_memory("key2", "val2")
        all_mem = memory.get_all_memory()
        assert all_mem == {"key1": "val1", "key2": "val2"}

    def test_clear_memory(self, memory):
        memory.set_memory("k", "v")
        memory.clear_memory()
        assert memory.get_all_memory() == {}

    def test_clear_all(self, memory):
        sid = memory.create_session("S")
        memory.add_message(sid, "user", "msg")
        memory.set_memory("k", "v")
        memory.clear_all()
        assert memory.list_sessions() == []
        assert memory.get_all_memory() == {}

    def test_multiple_sessions_ordered(self, memory):
        s1 = memory.create_session("First")
        s2 = memory.create_session("Second")
        sessions = memory.list_sessions()
        assert sessions[0]["session_id"] == s2
        assert sessions[1]["session_id"] == s1

    def test_message_with_tool_calls(self, memory):
        sid = memory.create_session("Tools")
        memory.add_message(sid, "assistant", "Let me check", tool_calls='[{"id":"tc1"}]')
        msgs = memory.get_session_messages(sid)
        assert msgs[0]["tool_calls"] == '[{"id":"tc1"}]'

    def test_message_with_tool_call_id(self, memory):
        sid = memory.create_session("Tools")
        memory.add_message(sid, "tool", "result data", tool_call_id="tc_123")
        msgs = memory.get_session_messages(sid)
        assert msgs[0]["tool_call_id"] == "tc_123"

    def test_overwrite_memory(self, memory):
        memory.set_memory("topic", "old")
        memory.set_memory("topic", "new")
        assert memory.get_memory("topic") == "new"


class TestNeedsMemoryExtraction:
    def test_detects_memory_keywords(self):
        from lmbagent.chat.engine import _needs_memory_extraction
        assert _needs_memory_extraction("记住我的实验温度是60℃")
        assert _needs_memory_extraction("我们实验室通常用LFP电池")
        assert _needs_memory_extraction("我喜欢用Arbin设备")

    def test_no_memory_keywords(self):
        from lmbagent.chat.engine import _needs_memory_extraction
        assert not _needs_memory_extraction("帮我分析这个数据集")
        assert not _needs_memory_extraction("什么是库伦效率？")


class TestBuildToolDescriptions:
    def test_generates_descriptions(self):
        from lmbagent.chat.engine import _build_tool_descriptions
        desc = _build_tool_descriptions()
        assert "load_battery_data" in desc
        assert "list_experiments" in desc
        assert len(desc) > 100
