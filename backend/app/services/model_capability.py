"""P1-Model-Failover: Agent 能力画像.

定义每类 Agent 需要什么能力, 用于自动选模评分.
"""
from __future__ import annotations

# Agent 能力画像: 每个角色对模型的需求
AGENT_CAPABILITY_PROFILE: dict[str, dict] = {
    "planner": {
        "needs_json": True,
        "needs_long_context": True,
        "needs_creativity": 0.5,
        "needs_reasoning": 0.9,
        "max_latency_weight": 0.3,
        "cost_sensitivity": 0.4,
        "preferred_tags": ["reasoning", "json", "outline"],
    },
    "drafter": {
        "needs_json": False,
        "needs_long_output": True,
        "needs_style": 0.95,
        "needs_creativity": 0.9,
        "max_latency_weight": 0.2,
        "cost_sensitivity": 0.3,
        "preferred_tags": ["longform", "creative", "style"],
    },
    "critic": {
        "needs_json": True,
        "needs_reasoning": 0.95,
        "needs_consistency": 0.9,
        "cost_sensitivity": 0.5,
        "preferred_tags": ["json", "logic", "critique"],
    },
    "rewriter": {
        "needs_json": False,
        "needs_long_output": True,
        "needs_style": 0.9,
        "needs_creativity": 0.8,
        "max_latency_weight": 0.2,
        "cost_sensitivity": 0.4,
        "preferred_tags": ["longform", "creative", "rewrite"],
    },
    "continuity": {
        "needs_json": True,
        "needs_reasoning": 0.85,
        "needs_consistency": 0.95,
        "cost_sensitivity": 0.5,
        "preferred_tags": ["json", "consistency", "logic"],
    },
    "memory_update": {
        "needs_json": True,
        "needs_long_context": True,
        "cost_sensitivity": 0.7,
        "preferred_tags": ["json", "extraction", "cheap"],
    },
    "chief": {
        "needs_json": True,
        "needs_reasoning": 0.8,
        "cost_sensitivity": 0.3,
        "preferred_tags": ["json", "planning"],
    },
    "learner": {
        "needs_json": True,
        "cost_sensitivity": 0.8,
        "preferred_tags": ["json", "extraction", "cheap"],
    },
    "reader_hook": {
        "needs_json": True,
        "needs_speed": 0.8,
        "cost_sensitivity": 0.8,
        "preferred_tags": ["fast", "review", "cheap"],
    },
    "comment_triage": {
        "needs_json": True,
        "needs_speed": 0.7,
        "cost_sensitivity": 0.8,
        "preferred_tags": ["json", "fast", "cheap"],
    },
    "discussion": {
        "needs_json": True,
        "needs_creativity": 0.6,
        "cost_sensitivity": 0.5,
        "preferred_tags": ["creative", "roleplay", "json"],
    },
    "study": {
        "needs_json": True,
        "needs_long_context": True,
        "cost_sensitivity": 0.5,
        "preferred_tags": ["analysis", "json", "longform"],
    },
}

# 旧角色名 → 新 AgentRole key 映射
LEGACY_ROLE_TO_AGENT_KEY: dict[str, str] = {
    "Chief": "chief",
    "ChiefAgent": "chief",
    "Planner": "planner",
    "Draft": "drafter",
    "Drafter": "drafter",
    "Critic": "critic",
    "Rewrite": "rewriter",
    "Rewriter": "rewriter",
    "Continuity": "continuity",
    "MemoryUpdate": "memory_update",
    "Learning": "learner",
}

# 策略权重
STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "quality_first": {
        "capability": 0.35, "health": 0.25, "success": 0.18,
        "latency": 0.07, "cost": 0.05, "json": 0.07, "context": 0.03,
    },
    "cost_first": {
        "capability": 0.25, "health": 0.20, "success": 0.15,
        "latency": 0.08, "cost": 0.22, "json": 0.07, "context": 0.03,
    },
    "speed_first": {
        "capability": 0.22, "health": 0.20, "success": 0.15,
        "latency": 0.28, "cost": 0.08, "json": 0.05, "context": 0.02,
    },
    "long_context_first": {
        "capability": 0.26, "health": 0.18, "success": 0.15,
        "latency": 0.06, "cost": 0.06, "json": 0.06, "context": 0.23,
    },
    "json_stable_first": {
        "capability": 0.25, "health": 0.18, "success": 0.17,
        "latency": 0.06, "cost": 0.06, "json": 0.25, "context": 0.03,
    },
}
