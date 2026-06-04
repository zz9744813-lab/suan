"""P6 review services — AgentRoleRunner / ReaderReviewService / WeightService /
CommentTriageService / DiscussionBridge.

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

  CommentTriageService
                   - the P3 chief-moderator intake path. Pulls all
                      status='new' comments, asks chief_comment_moderator
                      for triage (reply / group / discuss / ignore), then
                      writes chief_agent replies, builds comment groups,
                      and triggers discussions for high-severity groups.

  DiscussionBridge  - the P3 bridge from ReviewCommentGroup to
                      DiscussionSession. Selects participants by
                      severity + tags, renders the P6 spec topic
                      format, creates the session, and enqueues a
                      'comment_discussion' task for the P4 worker.

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
from app.services.review.comment_triage_service import (
    CommentTriageService,
    TriageItemOutcome,
    TriageOutcome,
    get_comment_triage_service,
)
from app.services.review.discussion_bridge import (
    DiscussionBridge,
    get_discussion_bridge,
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
    "CommentTriageService",
    "TriageItemOutcome",
    "TriageOutcome",
    "DiscussionBridge",
    "WeightService",
    "get_agent_role_runner",
    "get_reader_review_service",
    "get_comment_triage_service",
    "get_discussion_bridge",
    "get_weight_service",
]
