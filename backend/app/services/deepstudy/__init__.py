"""DeepStudy execution layer — DAG coordinator, event bus, stage results,
graph materializer, behaviour/technique miners, knowledge indexer,
writing-context sync, and auto-repair.

All modules are importable from this package:

  from app.services.deepstudy import (
      DeepStudyCoordinatorAgent,
      DeepStudyEventBus, deepstudy_event_bus,
      StageResultStore,
      GraphMaterializer,
      BehaviorPatternMiner,
      TechniqueMiner,
      KnowledgeIndexer,
      WritingContextSync,
      AutoRepair,
      DEEPSTUDY_DAG, get_ready_stages, get_next_stages, get_downstream_stages,
  )
"""

from .auto_repair import AutoRepair
from .behavior_miner import BehaviorPatternMiner
from .coordinator import DeepStudyCoordinatorAgent
from .event_bus import DeepStudyEventBus, deepstudy_event_bus
from .graph_materializer import GraphMaterializer
from .job_graph import (
    DEEPSTUDY_DAG,
    get_downstream_stages,
    get_next_stages,
    get_ready_stages,
)
from .knowledge_indexer import KnowledgeIndexer
from .stage_result_store import StageResultStore
from .technique_miner import TechniqueMiner
from .writing_context_sync import WritingContextSync

__all__ = [
    "DeepStudyCoordinatorAgent",
    "DeepStudyEventBus",
    "deepstudy_event_bus",
    "StageResultStore",
    "GraphMaterializer",
    "BehaviorPatternMiner",
    "TechniqueMiner",
    "KnowledgeIndexer",
    "WritingContextSync",
    "AutoRepair",
    "DEEPSTUDY_DAG",
    "get_ready_stages",
    "get_next_stages",
    "get_downstream_stages",
]
