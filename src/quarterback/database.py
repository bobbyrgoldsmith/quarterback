"""
Database models and initialization for Quarterback.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    DateTime,
    Text,
    Float,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import os


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    mission: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    goals: Mapped[list["Goal"]] = relationship(back_populates="organization")
    workflows: Mapped[list["Workflow"]] = relationship(back_populates="organization")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    level: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    timeframe: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="goals")


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    goals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="workflows")
    projects: Mapped[list["Project"]] = relationship(back_populates="workflow")
    advisory_documents: Mapped[list["AdvisoryDocument"]] = relationship(back_populates="workflow")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    workflow: Mapped[Optional["Workflow"]] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
    advisory_documents: Mapped[list["AdvisoryDocument"]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    effort: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    impact: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    agent_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_ready: Mapped[bool] = mapped_column(default=False)
    agent_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    agent_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    agent_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")
    dependencies_from: Mapped[list["Dependency"]] = relationship(
        foreign_keys="Dependency.task_id", back_populates="task"
    )
    dependencies_to: Mapped[list["Dependency"]] = relationship(
        foreign_keys="Dependency.depends_on_task_id", back_populates="depends_on"
    )


class Dependency(Base):
    __tablename__ = "dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    dependency_type: Mapped[str] = mapped_column(String(50), default="blocks")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped["Task"] = relationship(foreign_keys=[task_id], back_populates="dependencies_from")
    depends_on: Mapped["Task"] = relationship(
        foreign_keys=[depends_on_task_id], back_populates="dependencies_to"
    )


class Conflict(Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    conflicting_entities: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class History(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdvisoryDocument(Base):
    __tablename__ = "advisory_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[Optional[int]] = mapped_column(ForeignKey("workflows.id"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"), nullable=True)

    title: Mapped[str] = mapped_column(String(512))
    source: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    analysis_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    adoption_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    adopted_recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejected_recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    adopted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    workflow: Mapped[Optional["Workflow"]] = relationship(back_populates="advisory_documents")
    project: Mapped[Optional["Project"]] = relationship(back_populates="advisory_documents")
    recommendations: Mapped[list["AdvisoryRecommendation"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024))
    secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    events: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_id: Mapped[int] = mapped_column(ForeignKey("webhooks.id"))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50))
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    webhook: Mapped["Webhook"] = relationship()


class AdvisoryRecommendation(Base):
    __tablename__ = "advisory_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    advisory_document_id: Mapped[int] = mapped_column(ForeignKey("advisory_documents.id"))

    recommendation_text: Mapped[str] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    decision_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    conflicts_with: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aligns_with: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_effort_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_impact: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    implemented_as_task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    document: Mapped["AdvisoryDocument"] = relationship(back_populates="recommendations")
    task: Mapped[Optional["Task"]] = relationship()


async def init_db(db_path: str = None):
    """Initialize the database with all tables."""
    if db_path is None:
        from quarterback.config import DB_PATH

        db_path = str(DB_PATH)

    db_dir = os.path.dirname(db_path)
    if db_dir and db_path != ":memory:":
        os.makedirs(db_dir, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    # Enable WAL mode for safe concurrent access from multiple MCP server processes
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


async def get_session(engine) -> AsyncSession:
    """Get a new database session."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()
