"""Tests for the webhook system."""

import pytest
import pytest_asyncio
from quarterback.webhooks import WebhookManager, WEBHOOK_EVENTS
from quarterback.database import WebhookEvent, Task
from sqlalchemy import select


@pytest_asyncio.fixture
async def webhook_manager(db_engine):
    manager = WebhookManager(db_engine)
    return manager


class TestRegisterWebhook:
    @pytest.mark.asyncio
    async def test_register_webhook(self, webhook_manager, db_session):
        result = await webhook_manager.register_webhook(
            db_session,
            name="Test Hook",
            url="https://example.com/hook",
            events=["task.created"],
            secret="my-secret",
        )
        assert result["success"] is True
        assert result["webhook_id"] is not None
        assert result["name"] == "Test Hook"

    @pytest.mark.asyncio
    async def test_register_webhook_all_events(self, webhook_manager, db_session):
        result = await webhook_manager.register_webhook(
            db_session,
            name="All Events",
            url="https://example.com/all",
            events=["*"],
        )
        assert result["success"] is True


class TestListWebhooks:
    @pytest.mark.asyncio
    async def test_list_empty(self, webhook_manager, db_session):
        result = await webhook_manager.list_webhooks(db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_after_register(self, webhook_manager, db_session):
        await webhook_manager.register_webhook(
            db_session, name="Hook1", url="https://a.com", events=["*"]
        )
        result = await webhook_manager.list_webhooks(db_session)
        assert len(result) == 1
        assert result[0]["name"] == "Hook1"


class TestUpdateWebhook:
    @pytest.mark.asyncio
    async def test_update_name(self, webhook_manager, db_session):
        reg = await webhook_manager.register_webhook(
            db_session, name="Old", url="https://a.com", events=["*"]
        )
        result = await webhook_manager.update_webhook(db_session, reg["webhook_id"], name="New")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, webhook_manager, db_session):
        result = await webhook_manager.update_webhook(db_session, 999)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_deactivate_webhook(self, webhook_manager, db_session):
        reg = await webhook_manager.register_webhook(
            db_session, name="Active", url="https://a.com", events=["*"]
        )
        result = await webhook_manager.update_webhook(db_session, reg["webhook_id"], active=False)
        assert result["success"] is True


class TestDeleteWebhook:
    @pytest.mark.asyncio
    async def test_delete_existing(self, webhook_manager, db_session):
        reg = await webhook_manager.register_webhook(
            db_session, name="Delete Me", url="https://a.com", events=["*"]
        )
        result = await webhook_manager.delete_webhook(db_session, reg["webhook_id"])
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, webhook_manager, db_session):
        result = await webhook_manager.delete_webhook(db_session, 999)
        assert result["success"] is False


class TestTriggerEvent:
    @pytest.mark.asyncio
    async def test_trigger_creates_event(self, webhook_manager, db_session):
        await webhook_manager.register_webhook(
            db_session, name="Hook", url="https://a.com", events=["task.created"]
        )
        await webhook_manager.trigger_event(db_session, "task.created", {"task_id": 1})
        result = await db_session.execute(select(WebhookEvent))
        events = result.scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "task.created"

    @pytest.mark.asyncio
    async def test_trigger_skips_unsubscribed(self, webhook_manager, db_session):
        await webhook_manager.register_webhook(
            db_session, name="Hook", url="https://a.com", events=["task.completed"]
        )
        await webhook_manager.trigger_event(db_session, "task.created", {"task_id": 1})
        result = await db_session.execute(select(WebhookEvent))
        events = result.scalars().all()
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_wildcard_receives_all(self, webhook_manager, db_session):
        await webhook_manager.register_webhook(
            db_session, name="All", url="https://a.com", events=["*"]
        )
        await webhook_manager.trigger_event(db_session, "task.created", {"task_id": 1})
        result = await db_session.execute(select(WebhookEvent))
        events = result.scalars().all()
        assert len(events) == 1


class TestAgentTasks:
    @pytest.mark.asyncio
    async def test_mark_agent_ready(self, webhook_manager, db_session):
        task = Task(description="Agent task", priority=3)
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        result = await webhook_manager.mark_task_agent_ready(
            db_session, task.id, {"autonomy_level": "autonomous", "agent_type": "dev"}
        )
        assert result["success"] is True

        await db_session.refresh(task)
        assert task.agent_ready is True
        assert task.agent_status == "queued"

    @pytest.mark.asyncio
    async def test_get_agent_ready_tasks(self, webhook_manager, db_session):
        task = Task(
            description="Ready task",
            priority=3,
            agent_ready=True,
            agent_status="queued",
            agent_config='{"agent_type": "dev"}',
        )
        db_session.add(task)
        await db_session.commit()

        tasks = await webhook_manager.get_agent_ready_tasks(db_session)
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Ready task"

    @pytest.mark.asyncio
    async def test_filter_by_agent_type(self, webhook_manager, db_session):
        t1 = Task(
            description="Dev task",
            priority=3,
            agent_ready=True,
            agent_status="queued",
            agent_config='{"agent_type": "dev"}',
        )
        t2 = Task(
            description="Research task",
            priority=3,
            agent_ready=True,
            agent_status="queued",
            agent_config='{"agent_type": "research"}',
        )
        db_session.add_all([t1, t2])
        await db_session.commit()

        tasks = await webhook_manager.get_agent_ready_tasks(db_session, agent_type="dev")
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Dev task"

    @pytest.mark.asyncio
    async def test_update_agent_status_completed(self, webhook_manager, db_session):
        task = Task(
            description="Complete me", priority=3, agent_ready=True, agent_status="processing"
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        result = await webhook_manager.update_agent_status(
            db_session, task.id, "completed", "Done!"
        )
        assert result["success"] is True

        await db_session.refresh(task)
        assert task.agent_status == "completed"
        assert task.agent_ready is False
        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_update_agent_status_nonexistent(self, webhook_manager, db_session):
        result = await webhook_manager.update_agent_status(db_session, 999, "completed")
        assert result["success"] is False


class TestWebhookEvents:
    def test_event_types_defined(self):
        assert "task.created" in WEBHOOK_EVENTS
        assert "task.completed" in WEBHOOK_EVENTS
        assert "task.agent_ready" in WEBHOOK_EVENTS
        assert "*" in WEBHOOK_EVENTS
