from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, UniqueConstraint
from app.core.database import Base
import datetime

class ProjectStudyMaterialLink(Base):
    __tablename__ = "project_study_material_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, nullable=False)
    material_id = Column(Integer, nullable=False)
    link_type = Column(String(50), default="reference")
    weight = Column(Float, default=1.0)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    __table_args__ = (UniqueConstraint("project_id", "material_id"),)
