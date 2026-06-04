"""P6 review services — AgentRoleRunner / ReaderReviewService / WeightService.

Lives next to ``services/llm/`` and ``services/pipeline`` so the rest
of the codebase can ``from app.services.review import ...``.

Public surface:

  AgentRoleRunner   - run any AgentRole (key → provider → model → prompt
                      → LLMClient.chat). Writes AgentRun + AgentRunEvent.
                      Fully independent from the old ``LLMRouter`` (which
                      only knows about legacy ``ModelRoleAssignment.role``
                      strings like "Chief" / "Draft"). Per spec §4.1,
                      the 5 reader Agents must NOT go through the old
                      router path — they get their own binding tables.

  ReaderReviewService
                   - the per-chapter entry point used by worker (P4)
                      and by manual tests. Reads the latest
                      ChapterVersion, fans out to 5 reader AgentRoles,
                      writes one ReviewComment per reader, and updates
                      ReaderReviewRun totals.

  WeightService    - bumps ReaderAgentProfile.weight based on whether
                      the chief moderator accepted / rejected the
                      originating comment.

Worker integration (P4) is intentionally NOT wired up here — the
services are designed to be called from a fresh ``session_scope()``
so the caller (worker tick / API endpoint / manual test script) owns
the transaction boundaries.
"""
from __future__ import annotations

from app.services.review.agent_role_runner import (
    AgentRoleRunResult,
    AgentRoleRunner,
    get_agent_role_runner,
)
from app.services.review.reader_review_service import (
    ReaderReviewService,
    get_reader_review_service,
)
from app.services.review.weight_service import WeightService, get_weight_service

__all__ = [
    "AgentRoleRunResult",
    "AgentRoleRunner",
    "ReaderReviewService",
    "WeightService",
    "get_agent_role_runner",
    "get_reader_review_service",
    "get_weight_service",
]
