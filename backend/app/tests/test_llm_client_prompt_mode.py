"""P0 Phase 1: LLMClient prompt mode separation tests."""
import pytest
from unittest.mock import MagicMock

from app.services.llm.client import LLMClient


@pytest.fixture
def client():
    return LLMClient()


# ── _prepare_payload is an instance method on LLMClient ──


def test_freeform_agent_does_not_inject_json_prompt(client):
    """Drafter/Rewriter 不应包含 JSON 系统提示."""
    payload = {"messages": [{"role": "user", "content": "写一段文字"}]}
    result = client._prepare_payload(
        payload, "gpt-4", "https://api.example.com", None,
    )
    messages = result.get("messages", [])
    system_msgs = [m for m in messages if m.get("role") == "system"]
    for msg in system_msgs:
        assert "只输出一个 JSON 对象" not in msg.get("content", "")


def test_json_agent_injects_strict_json_prompt(client):
    """Planner/Critic 应包含 JSON 系统提示 (response_format=json_object)."""
    payload = {
        "messages": [{"role": "user", "content": "分析大纲"}],
        "response_format": {"type": "json_object"},
    }
    result = client._prepare_payload(
        payload, "gpt-4", "https://api.example.com", None,
    )
    messages = result.get("messages", [])
    all_text = " ".join(m.get("content", "") for m in messages)
    assert "只输出一个 JSON 对象" in all_text or "JSON" in all_text


def test_json_tail_reminder_only_when_strict(client):
    """tail reminder 只在需要 JSON 输出时追加."""
    payload_json = {
        "messages": [{"role": "user", "content": "test"}],
        "response_format": {"type": "json_object"},
    }
    payload_free = {"messages": [{"role": "user", "content": "test"}]}

    result_strict = client._prepare_payload(
        payload_json, "gpt-4", "https://api.example.com", None,
    )
    result_free = client._prepare_payload(
        payload_free, "gpt-4", "https://api.example.com", None,
    )
    tail_strict = result_strict["messages"][-1].get("content", "")
    tail_free = result_free["messages"][-1].get("content", "")
    if "只输出一个 JSON 对象" in tail_strict:
        assert "只输出一个 JSON 对象" not in tail_free


def test_provider_extra_require_json_injects_prompt(client):
    """provider_extra.require_json=True 也应注入 JSON 系统提示."""
    payload = {"messages": [{"role": "user", "content": "test"}]}
    provider_extra = {"require_json": True}
    result = client._prepare_payload(
        payload, "gpt-4", "https://api.example.com", provider_extra,
    )
    all_text = " ".join(m.get("content", "") for m in result["messages"])
    assert "JSON" in all_text


def test_no_system_msg_added_for_freeform(client):
    """freeform 模式不应额外插入 system 消息."""
    original = [{"role": "user", "content": "hello"}]
    payload = {"messages": list(original)}
    result = client._prepare_payload(
        payload, "gpt-4", "https://api.example.com", None,
    )
    system_msgs = [m for m in result["messages"] if m.get("role") == "system"]
    assert len(system_msgs) == 0


def test_json_mode_injects_system_if_missing(client):
    """需要 JSON 但没有 system 消息时，应插入一条."""
    payload = {
        "messages": [{"role": "user", "content": "give json"}],
        "response_format": {"type": "json_object"},
    }
    result = client._prepare_payload(
        payload, "gpt-4", "https://api.example.com", None,
    )
    system_msgs = [m for m in result["messages"] if m.get("role") == "system"]
    assert len(system_msgs) >= 1
