"""Study agents — 拆书 (deconstruction) helpers.

P15 / P0-STUDY-1: replaces the previous regex-stub character
extractor with real LLM-backed agents. Two agents ship today:

  - ``StudyCharacterAgent``  — takes a chapter and returns a JSON
                              list of characters (name / aliases /
                              role / tags / base_profile).
  - ``StudyEventAgent``      — extracts plot-significant events
                              (伏笔 / hooks) from a chapter. Returns
                              a JSON list of {name, summary,
                              planted_chapter, related_characters,
                              importance}.

Both agents share the same plumbing as the chapter-pipeline agents
(``BaseAgent`` → ``LLMRouter`` → ``PromptEngine``) so they get the
same model-role bindings, retries, prompt-versioning and AgentStep
audit trail. The ``uses_json_output=True`` flag is on for both
because the prompt library ships a strict JSON schema.

A third agent, ``StudyBehaviorPatternAgent``, is sketched in this
file with a "not yet implemented" stub — it requires the planner
agent's scene graph and is queued for the Round E
(Behavior/Graph pages) work.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class StudyCharacterAgent(BaseAgent):
    """P15 / P0-STUDY-1: extract characters from a chapter.

    The prompt (see ``app/prompts/default/library.py::study_character``)
    asks the model to return a JSON envelope ``{"characters": [...]}``
    where each entry has ``name``, ``aliases``, ``role``, ``tags`` and
    ``base_profile`` (age / faction / abilities / items / summary).
    The route that owns the call (``POST /api/study/materials/{id}/study``)
    persists the result into ``study_characters``.

    Temperature is forced to 0 so the model doesn't get creative about
    the JSON shape — step-3.7-flash otherwise invents prose preambles
    that the picker then has to clean up.
    """
    name = "StudyCharacterAgent"
    role = "StudyAgent"
    prompt_key = "study_character"
    step_name = "study_character"
    extra_temperature = 0.0
    extra_max_tokens = 2500

    # If the model returns prose instead of JSON we want a graceful
    # degradation — the regex fallback in the route is *better* than
    # a 400 because at least the user sees *some* names. So we
    # flip ``allow_json_fallback=True`` and synthesise a stub here
    # that says "extraction degraded, no characters found this time".
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        # Shape mirrors the prompt's expected schema. The route will
        # see ``characters=[]`` and the UI can decide whether to also
        # show the raw_preview as a "raw" view to the user.
        return {
            "characters": [],
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "StudyCharacterAgent JSON 解析失败，已回退为空结果。",
        }


class StudyEventAgent(BaseAgent):
    """P15 / P0-STUDY-1: extract plot-significant events from a chapter.

    Returns a JSON envelope ``{"events": [...]}`` where each entry
    represents a 伏笔 / hook / 转折点 / 升级契机.  This is the input
    to the future foreshadow auto-crystaliser (R12) and the
    Behavior/Graph page (Round E).

    For now the route does NOT call this — we only ship the
    character extraction path. The agent class is here so the
    Round E wiring doesn't have to re-invent the schema and the
    role bindings.
    """
    name = "StudyEventAgent"
    role = "StudyAgent"
    prompt_key = "study_event"  # not yet seeded in default library
    step_name = "study_event"
    extra_temperature = 0.0
    extra_max_tokens = 2500
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        return {
            "events": [],
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "StudyEventAgent JSON 解析失败，已回退为空结果。",
        }


# Sketched for Round E (Behavior/Graph pages).  Not wired into any
# route yet — keeping the import surface clean so the agent registry
# stays discoverable.
class StudyBehaviorPatternAgent(BaseAgent):
    """P15 / P0-STUDY-1 + Round E: extract reusable behavior patterns.

    Reads an entire material (chapters + extracted characters) and
    returns a JSON list of behavior_patterns shaped like the rows in
    the ``behavior_patterns`` table:
      {
        "name": "主角被公开羞辱",
        "character_tags": ["主角", "热血", "隐忍"],
        "situation_tags": ["公开羞辱", "师门内斗"],
        "typical_behavior": [...],
        "dialogue_style": [...],
        "scene_function": [...],
        "risks": [...],
        "recommended_plot_followup": [...],
      }
    The route (not yet implemented — see Round E plan) will merge
    these into the existing ``behavior_patterns`` table so the
    Planner can later pull them as scene hints.
    """
    name = "StudyBehaviorPatternAgent"
    role = "StudyAgent"
    prompt_key = "study_behavior_pattern"  # not yet seeded
    step_name = "study_behavior_pattern"
    extra_temperature = 0.0
    extra_max_tokens = 4000
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        return {
            "patterns": [],
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "StudyBehaviorPatternAgent JSON 解析失败。",
        }


# R24: 真实关系抽取 (跟前面 R22 的纯 co-occurrence 不同 — 这次用
# LLM 看章节正文, 给出 师父/对手/恋人/朋友/家人/仇人/师徒/同门
# 等语义标签, 而不是「同章节出现」这种纯共现)。
# 用户反馈 (R23): 「相互的联系不要之说出现在同一章节啊」—
# 之前 R22 的 relationships 端点只数两人是否同章, 标签全默认
# 「同章节出现」, 看起来没意义。
class StudyRelationshipExtractionAgent(BaseAgent):
    """R24: 给一对 (char_a, char_b) + 章节正文, 让 LLM 抽取
    关系类型。

    输入是路由拼好的 prompt: 列出两个角色名 + 共同出现的章节摘要
    (前 1500 字) + 我们从同章出现推导出的最相关章节标题。
    输出 JSON envelope: ``{"relations": [{"relation", "evidence",
    "confidence"}], "summary": "..."}``。

    关系类型限制在以下枚举, 路由会照此在 UI 里配色:
      师父 / 弟子 / 师徒
      对手 / 仇人
      恋人 / 夫妻
      朋友 / 同门
      家人 / 兄弟 / 姐妹 / 父子 / 母子
      主仆 / 势力
      同盟 / 合作
      敌人
      同章节出现   (兜底 — 如果 LLM 判不出更具体的)
    """
    name = "StudyRelationshipExtractionAgent"
    role = "StudyAgent"
    prompt_key = "study_relationship"  # 后面 seed.py 会加
    step_name = "study_relationship"
    extra_temperature = 0.0
    extra_max_tokens = 1500
    allow_json_fallback = True

    def _build_json_fallback(self, raw: str) -> dict[str, Any]:
        return {
            "relations": [],
            "parse_failed": True,
            "fallback": True,
            "raw_preview": (raw or "")[:1000],
            "summary": "StudyRelationshipExtractionAgent JSON 解析失败。",
        }
