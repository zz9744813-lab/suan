"""DeepStudy DAG — stages and their dependencies.

The DAG controls the order in which the coordinator runs stages.
Each key is a stage name; its value is a list of upstream stages
that must complete before this stage is ready to run.
"""

from __future__ import annotations

DEEPSTUDY_DAG: dict[str, list[str]] = {
    "ingest": [],
    "chapterize": ["ingest"],
    "chapter_profile": ["chapterize"],
    "entity_extract": ["chapter_profile"],
    "event_extract": ["chapter_profile"],
    "scene_beat_extract": ["chapter_profile"],
    "relationship_analyze": ["entity_extract", "event_extract"],
    "foreshadow_analyze": ["event_extract", "scene_beat_extract"],
    "behavior_pattern_mine": ["entity_extract", "event_extract", "scene_beat_extract"],
    "technique_mine": ["behavior_pattern_mine", "foreshadow_analyze"],
    "graph_finalize": [
        "entity_extract",
        "event_extract",
        "relationship_analyze",
        "foreshadow_analyze",
        "behavior_pattern_mine",
        "technique_mine",
    ],
    "study_critic": ["graph_finalize"],
    "knowledge_index": ["study_critic"],
    "writing_context_sync": ["knowledge_index"],
}


def get_ready_stages(completed: list[str]) -> list[str]:
    """Return stages whose upstream dependencies are all satisfied.

    Args:
        completed: List of stage keys that have already completed.

    Returns:
        List of stage keys that are ready to run, in DAG order.
    """
    completed_set = set(completed)
    ready: list[str] = []
    for stage, deps in DEEPSTUDY_DAG.items():
        if stage in completed_set:
            continue
        if all(d in completed_set for d in deps):
            ready.append(stage)
    return ready


def get_next_stages(current_stage: str) -> list[str]:
    """Return the stages that immediately depend on ``current_stage``.

    Args:
        current_stage: The stage key whose downstream neighbours are needed.

    Returns:
        List of stage keys that have ``current_stage`` as a direct dependency.
    """
    downstream: list[str] = []
    for stage, deps in DEEPSTUDY_DAG.items():
        if current_stage in deps:
            downstream.append(stage)
    return downstream


def get_downstream_stages(stage_key: str) -> list[str]:
    """Return ALL stages downstream of ``stage_key`` (transitive closure).

    Useful for repair: when a stage fails, all its transitive downstream
    stages must be re-run.

    Args:
        stage_key: The stage key whose entire downstream closure is needed.

    Returns:
        List of stage keys (in DAG order) that transitively depend on ``stage_key``.
    """
    result: set[str] = set()
    queue: list[str] = [stage_key]
    while queue:
        current = queue.pop(0)
        for downstream in get_next_stages(current):
            if downstream not in result:
                result.add(downstream)
                queue.append(downstream)
    # Return in DAG order so the repair loop can process sequentially.
    ordered: list[str] = []
    for stage in DEEPSTUDY_DAG:
        if stage in result:
            ordered.append(stage)
    return ordered
