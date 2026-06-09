"""ORM models package.

Each submodule defines a coherent group of tables from the spec. All models
inherit from `Base` defined in app.core.database. Importing this package has
the side-effect of registering every model with SQLAlchemy's metadata.
"""
from app.models.project import Bible, Chapter, ChapterVersion, Outline, Project
from app.models.task import (
    AgentEvent,
    AgentStep,
    AgentTask,
    WorkerPolicy,
    WorkerStatus,
)
from app.models.model_provider import ModelProvider, ModelRoleAssignment
from app.models.model_health import ModelHealthSnapshot, ModelRouteEvent
from app.models.prompt import PromptTemplate, PromptVersion
from app.models.memory import (
    MemoryCharacter,
    MemoryCharacterState,
    MemoryForeshadow,
    MemoryHardFact,
)
from app.models.memory_v2 import (
    DiscussionDecision,
    MemoryTimelineEvent,
    RawMemoryEntry,
    StableCharacterState,
    StableMemoryEntity,
)
from app.models.chief_agent import ChiefAgentMessage, ChiefAgentSession
from app.models.study import (
    BehaviorPattern,
    GraphEdge,
    GraphNode,
    StudyChapter,
    StudyCharacter,
    StudyMaterial,
)
from app.models.deepstudy import (
    BehaviorPatternEvidence,
    ChapterAnalysis,
    DeepStudyStageResult,
    Entity,
    EntityMention,
    ForeshadowChain,
    Relationship,
    SceneBeat,
    StudyRun,
    WritingTechnique,
)
from app.models.deepstudy_graph import (
    DeepStudyGraph,
    DeepStudyGraphEdge,
    DeepStudyGraphNode,
)
from app.models.discussion import DiscussionSession, DiscussionTurn
from app.models.agent_role import (
    AgentModelBinding,
    AgentPromptBinding,
    AgentRole,
    AgentRun,
    AgentRunEvent,
)
from app.models.comment_review import (
    ReaderAgentProfile,
    ReaderReviewRun,
    ReviewComment,
    ReviewCommentGroup,
    ReviewSettings,
)
from app.models.genre_prompt_map import (
    GenrePromptMapping,
    ProjectPromptSnapshot,
)
from app.models.behavior_card import (
    BehaviorCard,
    BehaviorCardTag,
    BehaviorCardTechnique,
    BehaviorCardSource,
    BehaviorCardUsageLog,
    BehaviorCategory,
)
from app.models.discussion_trace import (
    DiscussionThread,
    DiscussionMessage,
    DiscussionIssueSource,
    DiscussionSkillDraft,
    DiscussionRecycleJob,
    Skill,
)
from app.models.agent_memory import (
    AgentMemoryEntry,
    AgentMemoryLink,
    AgentMemoryAuditLog,
    AgentMemoryConsolidationJob,
    AgentMemoryAccessLog,
    MemoryChangeRequest,
)
from app.models.model_runtime import ModelRuntimeStat
from app.models.model_call_event import ModelCallEvent
from app.models.llm_cache import LLMCacheEntry
from app.models.project_study_link import ProjectStudyMaterialLink
from app.models.project_material import ProjectMaterial, ProjectMaterialIngestionRun
from app.models.prompt_auto_fill import (
    PromptAutoFillBatch,
    PromptRecommendationLog,
    PromptTemplatePerformance,
)

__all__ = [
    "Project",
    "Chapter",
    "ChapterVersion",
    "Outline",
    "Bible",
    "AgentTask",
    "AgentStep",
    "AgentEvent",
    "WorkerStatus",
    "WorkerPolicy",
    "ModelProvider",
    "ModelRoleAssignment",
    "PromptTemplate",
    "PromptVersion",
    "MemoryCharacter",
    "MemoryCharacterState",
    "MemoryForeshadow",
    "MemoryHardFact",
    "ChiefAgentSession",
    "ChiefAgentMessage",
    "StudyMaterial",
    "StudyChapter",
    "StudyCharacter",
    "BehaviorPattern",
    "GraphNode",
    "GraphEdge",
    "DiscussionSession",
    "DiscussionTurn",
    # P0-DeepStudy
    "StudyRun",
    "ChapterAnalysis",
    "Entity",
    "EntityMention",
    "SceneBeat",
    "Relationship",
    "ForeshadowChain",
    "BehaviorPatternEvidence",
    "WritingTechnique",
    "DeepStudyStageResult",
    # DeepStudy knowledge graph (two-layer)
    "DeepStudyGraph",
    "DeepStudyGraphNode",
    "DeepStudyGraphEdge",
    # P3: Raw + Stable memory
    "RawMemoryEntry",
    "StableMemoryEntity",
    "StableCharacterState",
    "MemoryTimelineEvent",
    "DiscussionDecision",
    # P4: Agent role / model binding / prompt binding / run / event
    "AgentRole",
    "AgentModelBinding",
    "AgentPromptBinding",
    "AgentRun",
    "AgentRunEvent",
    # P6: 评论区驱动的模拟读者 Agent 评审系统
    "ReaderAgentProfile",
    "ReviewComment",
    "ReviewCommentGroup",
    "ReaderReviewRun",
    "ReviewSettings",
    # P7: Genre-Prompt mapping + traceability
    "GenrePromptMapping",
    "ProjectPromptSnapshot",
    # P8: Behavior Card knowledge base
    "BehaviorCategory",
    "BehaviorCard",
    "BehaviorCardTag",
    "BehaviorCardTechnique",
    "BehaviorCardSource",
    "BehaviorCardUsageLog",
    # P9: Discussion Auto-Trace + Skill
    "DiscussionThread",
    "DiscussionMessage",
    "DiscussionIssueSource",
    "DiscussionSkillDraft",
    "DiscussionRecycleJob",
    "Skill",
    # P10: Agent Memory Layered Pool
    "AgentMemoryEntry",
    "AgentMemoryLink",
    "AgentMemoryAuditLog",
    "AgentMemoryConsolidationJob",
    "AgentMemoryAccessLog",
    "MemoryChangeRequest",
    # P0-Model-Failover: model runtime stats + call events
    "ModelRuntimeStat",
    "ModelCallEvent",
    "LLMCacheEntry",
    # NF2: Prompt auto-fill audit models
    "PromptAutoFillBatch",
    "PromptRecommendationLog",
    "PromptTemplatePerformance",
    # Project-Study boundary
    "ProjectStudyMaterialLink",
    "ProjectMaterial",
    "ProjectMaterialIngestionRun",
]
from app.models.evolution import (EvolutionPatch,EvolutionRun,ModelQualityStat,SkillCard,SkillUsageEvent,SkillVersion)
