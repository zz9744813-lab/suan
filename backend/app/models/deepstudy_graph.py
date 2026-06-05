"""DeepStudy knowledge graph persistence layer.

Two-layer graph architecture:
  Layer 1 — ``deepstudy_graphs``: per-material graph summary & status
  Layer 2 — ``deepstudy_graph_nodes`` + ``deepstudy_graph_edges``: full graph topology

Node ID conventions:
  - book:{material_id}
  - chapter:{material_id}:{chapter_index}
  - entity:{entity_id}
  - scene:{scene_beat_id}
  - foreshadow:{foreshadow_chain_id}
  - behavior:{behavior_pattern_evidence_id}
  - technique:{writing_technique_id}

Edge key conventions:
  - rel:{relationship_id}
  - contains:{material_id}:{idx}
  - foreshadow_connects:{foreshadow_id}
  - behavior_refs:{evidence_id}
  - tech_source:{technique_id}
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.core.database import Base


class DeepStudyGraph(Base):
    """Per-material graph summary record — Layer 1."""

    __tablename__ = "deepstudy_graphs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, nullable=False, unique=True)
    status = Column(String(40), nullable=False, default="not_started")
    graph_version = Column(Integer, default=1)
    node_count = Column(Integer, default=0)
    edge_count = Column(Integer, default=0)
    character_count = Column(Integer, default=0)
    location_count = Column(Integer, default=0)
    faction_count = Column(Integer, default=0)
    item_count = Column(Integer, default=0)
    event_count = Column(Integer, default=0)
    foreshadow_count = Column(Integer, default=0)
    behavior_pattern_count = Column(Integer, default=0)
    writing_technique_count = Column(Integer, default=0)
    layout_json = Column(JSON, nullable=True)
    stats_json = Column(JSON, nullable=True)
    last_error = Column(Text, nullable=True)
    built_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )


class DeepStudyGraphNode(Base):
    """Graph node — Layer 2."""

    __tablename__ = "deepstudy_graph_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, nullable=False)
    node_key = Column(String(240), nullable=False)
    node_type = Column(String(80), nullable=False)
    label = Column(String(240), nullable=False)
    summary = Column(Text, nullable=True)
    importance = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    first_seen_chapter = Column(Integer, nullable=True)
    last_seen_chapter = Column(Integer, nullable=True)
    source_stage = Column(String(80), nullable=True)
    payload_json = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
    x = Column(Float, nullable=True)
    y = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    __table_args__ = (UniqueConstraint("material_id", "node_key"),)


class DeepStudyGraphEdge(Base):
    """Graph edge — Layer 2."""

    __tablename__ = "deepstudy_graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_id = Column(Integer, nullable=False)
    edge_key = Column(String(320), nullable=False)
    source_node_key = Column(String(240), nullable=False)
    target_node_key = Column(String(240), nullable=False)
    source_node_id = Column(Integer, nullable=True)
    target_node_id = Column(Integer, nullable=True)
    edge_type = Column(String(80), nullable=False)
    label = Column(String(160), nullable=False)
    summary = Column(Text, nullable=True)
    direction = Column(String(30), default="directed")
    weight = Column(Float, default=0.5)
    confidence = Column(Float, default=0.5)
    source_stage = Column(String(80), nullable=True)
    evidence_json = Column(JSON, nullable=True)
    payload_json = Column(JSON, nullable=True)
    first_seen_chapter = Column(Integer, nullable=True)
    last_seen_chapter = Column(Integer, nullable=True)
    occurrence_count = Column(Integer, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    __table_args__ = (UniqueConstraint("material_id", "edge_key"),)
