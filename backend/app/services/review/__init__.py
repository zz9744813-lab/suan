"""P6 review services — AgentRoleRunner / ReaderReviewService / WeightService /
CommentTriageService / DiscussionBridge / CommentCleanupService (P4)
/ ReviewQueueService (P4) / CommentDiscussionRunner (P4).

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

  CommentCleanupService (P4)
                   - 删除 7 天前过期的 review_comments, 跳过 immortal
                      (chief_agent reply / system) 跟 discussing
                      中的评论 (讨论结束后再清).

  ReviewQueueService (P4)
                   - 把 reader_review / comment_triage /
                      comment_discussion / comment_cleanup 任务写到
                      agent_tasks. Idempotent — 已有 pending 任务
                      时跳过. 走 auto_* 开关跟 ReviewSettings 配合.

  CommentDiscussionRunner (P4)
                   - worker 拉起 comment_discussion 任务时, 跑
                      DiscussionSession 的 5 个 participant turn + 1
                      个 chief_synthesis turn. P4 stub 模式 (写
                      [P4 stub] 占位), P4.1 真接 LLM.

Worker integration (P4) is wired up in ``app/workers/worker.py``.
"""
from __future__ import annotations

from app.services.review.agent_role_runner import (
    AgentRoleRunResult,
    AgentRoleRunner,
    get_agent_role_runner,
)
from app.services.review.comment_cleanup_service import (
    CleanupOutcome,
    CommentCleanupService,
    IMMORTAL_AUTHOR_TYPES,
    get_comment_cleanup_service,
)
from app.services.review.comment_discussion_runner import (
    CommentDiscussionRunner,
    DEFAULT_PARTICIPANTS,
    DiscussionRunOutcome,
    get_comment_discussion_runner,
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
from app.services.review.queue_service import (
    ENQUEUE_SOURCE_AUTO_COMMENT,
    ENQUEUE_SOURCE_AUTO_PIPELINE,
    ENQUEUE_SOURCE_MANUAL_API,
    ENQUEUE_SOURCE_WORKER_START,
    EnqueueResult,
    ReviewQueueService,
    get_review_queue,
)
from app.services.review.reader_review_service import (
    ReaderReviewOutcome,
    ReaderReviewService,
    get_reader_review_service,
)
from app.services.review.weight_service import WeightService, get_weight_service


__all__ = [
    # §4.1
    "AgentRoleRunner",
    "AgentRoleRunResult",
    "get_agent_role_runner",
    # §4.2
    "ReaderReviewService",
    "ReaderReviewOutcome",
    "get_reader_review_service",
    # §4.3
    "CommentTriageService",
    "TriageOutcome",
    "TriageItemOutcome",
    "get_comment_triage_service",
    # §4.4
    "DiscussionBridge",
    "get_discussion_bridge",
    "CommentDiscussionRunner",
    "DiscussionRunOutcome",
    "DEFAULT_PARTICIPANTS",
    "get_comment_discussion_runner",
    # §4.5
    "WeightService",
    "get_weight_service",
    # §4.6
    "CommentCleanupService",
    "CleanupOutcome",
    "IMMORTAL_AUTHOR_TYPES",
    "get_comment_cleanup_service",
    # §5
    "ReviewQueueService",
    "EnqueueResult",
    "get_review_queue",
    "ENQUEUE_SOURCE_AUTO_PIPELINE",
    "ENQUEUE_SOURCE_AUTO_COMMENT",
    "ENQUEUE_SOURCE_WORKER_START",
    "ENQUEUE_SOURCE_MANUAL_API",
]
