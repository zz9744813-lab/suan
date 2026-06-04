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
    Entity,
    EntityMention,
    ForeshadowChain,
    Relationship,
    SceneBeat,
    StudyRun,
    WritingTechnique,
)
from app.models.discussion import DiscussionSession, DiscussionTurn

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
    # P3: Raw + Stable memory
    "RawMemoryEntry",
    "StableMemoryEntity",
    "StableCharacterState",
    "MemoryTimelineEvent",
    "DiscussionDecision",
]
