"""Tests for database models and initialization."""

import pytest
from sqlalchemy import select

from quarterback.database import (
    Organization,
    Project,
    Task,
    Dependency,
    Conflict,
    History,
    AdvisoryDocument,
    AdvisoryRecommendation,
    Webhook,
    WebhookEvent,
    init_db,
)


class TestModels:
    @pytest.mark.asyncio
    async def test_create_organization(self, db_session):
        org = Organization(name="Test Corp", mission="Testing")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        assert org.id is not None
        assert org.name == "Test Corp"

    @pytest.mark.asyncio
    async def test_create_project(self, db_session):
        proj = Project(name="My Project", priority=2, status="active")
        db_session.add(proj)
        await db_session.commit()
        await db_session.refresh(proj)
        assert proj.id is not None
        assert proj.priority == 2

    @pytest.mark.asyncio
    async def test_create_task_with_project(self, db_session, sample_projects):
        task = Task(
            project_id=sample_projects[0].id,
            description="Test task",
            priority=4,
            effort=2.5,
            impact=3,
            status="pending",
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        assert task.id is not None
        assert task.project_id == sample_projects[0].id

    @pytest.mark.asyncio
    async def test_task_agent_fields(self, db_session):
        task = Task(
            description="Agent task",
            priority=3,
            agent_config='{"autonomy_level": "autonomous"}',
            agent_ready=True,
            agent_status="queued",
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        assert task.agent_ready is True
        assert task.agent_status == "queued"

    @pytest.mark.asyncio
    async def test_create_advisory_document(self, db_session, sample_projects):
        doc = AdvisoryDocument(
            title="Test Advisory",
            content="Some content",
            source="test.com",
            source_type="article",
            project_id=sample_projects[0].id,
            priority=3,
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)
        assert doc.id is not None
        assert doc.status == "pending_review"

    @pytest.mark.asyncio
    async def test_advisory_recommendation_relationship(self, db_session):
        doc = AdvisoryDocument(title="Test", content="Content", priority=3)
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        rec = AdvisoryRecommendation(
            advisory_document_id=doc.id,
            recommendation_text="Do this thing",
            category="strategy",
            estimated_effort_hours=5.0,
            estimated_impact=4,
        )
        db_session.add(rec)
        await db_session.commit()
        await db_session.refresh(rec)
        assert rec.advisory_document_id == doc.id

    @pytest.mark.asyncio
    async def test_create_webhook(self, db_session):
        webhook = Webhook(
            name="Test Hook",
            url="https://example.com/hook",
            events='["task.created"]',
            active=True,
        )
        db_session.add(webhook)
        await db_session.commit()
        await db_session.refresh(webhook)
        assert webhook.id is not None
        assert webhook.failure_count == 0

    @pytest.mark.asyncio
    async def test_create_webhook_event(self, db_session):
        webhook = Webhook(name="Hook", url="https://example.com", events='["*"]')
        db_session.add(webhook)
        await db_session.commit()
        await db_session.refresh(webhook)

        event = WebhookEvent(
            webhook_id=webhook.id,
            event_type="task.created",
            payload='{"task_id": 1}',
            status="pending",
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)
        assert event.webhook_id == webhook.id

    @pytest.mark.asyncio
    async def test_dependency_model(self, db_session):
        t1 = Task(description="Task 1", priority=3)
        t2 = Task(description="Task 2", priority=3)
        db_session.add_all([t1, t2])
        await db_session.commit()

        dep = Dependency(task_id=t1.id, depends_on_task_id=t2.id, dependency_type="blocks")
        db_session.add(dep)
        await db_session.commit()
        await db_session.refresh(dep)
        assert dep.task_id == t1.id

    @pytest.mark.asyncio
    async def test_history_model(self, db_session):
        history = History(
            entity_type="task",
            entity_id=1,
            action="created",
            context='{"description": "test"}',
        )
        db_session.add(history)
        await db_session.commit()
        await db_session.refresh(history)
        assert history.action == "created"

    @pytest.mark.asyncio
    async def test_conflict_model(self, db_session):
        conflict = Conflict(
            resource_type="time",
            conflicting_entities="[1, 2]",
            severity="high",
            description="Two tasks compete for time",
        )
        db_session.add(conflict)
        await db_session.commit()
        await db_session.refresh(conflict)
        assert conflict.resolved is False

    @pytest.mark.asyncio
    async def test_task_default_status(self, db_session):
        task = Task(description="Default status", priority=3)
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)
        assert task.status == "pending"

    @pytest.mark.asyncio
    async def test_project_tasks_relationship(self, db_session, sample_projects, sample_tasks):
        result = await db_session.execute(
            select(Task).where(Task.project_id == sample_projects[0].id)
        )
        tasks = result.scalars().all()
        assert len(tasks) >= 2


class TestInitDb:
    @pytest.mark.asyncio
    async def test_init_in_memory(self):
        engine = await init_db(":memory:")
        assert engine is not None
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_init_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        engine = await init_db(db_path)
        async with engine.begin() as conn:
            # Verify tables exist by querying metadata
            from sqlalchemy import text

            result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = {row[0] for row in result}
            assert "tasks" in tables
            assert "projects" in tables
            assert "advisory_documents" in tables
            assert "webhooks" in tables
        await engine.dispose()
