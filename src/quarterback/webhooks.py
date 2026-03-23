"""
Webhook API for external integrations.
Enables n8n, Zapier, and other automation tools to receive task events.
"""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiohttp

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quarterback.database import Webhook, WebhookEvent, Task


class WebhookManager:
    """Manages webhook registrations and event delivery."""

    def __init__(self, db_engine):
        self.db_engine = db_engine
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    async def start_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._delivery_worker())

    async def stop_worker(self):
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _delivery_worker(self):
        while True:
            try:
                event_id = await self._event_queue.get()
                await self._deliver_event(event_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Webhook delivery error: {e}")

    async def register_webhook(
        self,
        session: AsyncSession,
        name: str,
        url: str,
        events: List[str],
        secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        webhook = Webhook(
            name=name,
            url=url,
            secret=secret,
            events=json.dumps(events),
            active=True,
        )
        session.add(webhook)
        await session.commit()
        await session.refresh(webhook)

        return {
            "success": True,
            "webhook_id": webhook.id,
            "name": webhook.name,
            "url": webhook.url,
            "events": events,
            "message": f"Webhook '{name}' registered successfully",
        }

    async def list_webhooks(self, session: AsyncSession) -> List[Dict[str, Any]]:
        result = await session.execute(select(Webhook))
        webhooks = result.scalars().all()

        return [
            {
                "id": w.id,
                "name": w.name,
                "url": w.url,
                "events": json.loads(w.events),
                "active": w.active,
                "failure_count": w.failure_count,
                "last_triggered_at": w.last_triggered_at.isoformat()
                if w.last_triggered_at
                else None,
            }
            for w in webhooks
        ]

    async def update_webhook(
        self,
        session: AsyncSession,
        webhook_id: int,
        **kwargs,
    ) -> Dict[str, Any]:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        webhook = result.scalars().first()

        if not webhook:
            return {"success": False, "error": f"Webhook {webhook_id} not found"}

        if "name" in kwargs:
            webhook.name = kwargs["name"]
        if "url" in kwargs:
            webhook.url = kwargs["url"]
        if "secret" in kwargs:
            webhook.secret = kwargs["secret"]
        if "events" in kwargs:
            webhook.events = json.dumps(kwargs["events"])
        if "active" in kwargs:
            webhook.active = kwargs["active"]

        await session.commit()
        return {"success": True, "message": f"Webhook {webhook_id} updated"}

    async def delete_webhook(self, session: AsyncSession, webhook_id: int) -> Dict[str, Any]:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        webhook = result.scalars().first()

        if not webhook:
            return {"success": False, "error": f"Webhook {webhook_id} not found"}

        await session.delete(webhook)
        await session.commit()
        return {"success": True, "message": f"Webhook {webhook_id} deleted"}

    async def trigger_event(
        self,
        session: AsyncSession,
        event_type: str,
        payload: Dict[str, Any],
    ):
        result = await session.execute(select(Webhook).where(Webhook.active.is_(True)))
        webhooks = result.scalars().all()

        for webhook in webhooks:
            events = json.loads(webhook.events)
            if event_type in events or "*" in events:
                event = WebhookEvent(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    payload=json.dumps(payload, default=str),
                    status="pending",
                )
                session.add(event)
                await session.commit()
                await session.refresh(event)

                await self._event_queue.put(event.id)

    async def _deliver_event(self, event_id: int):
        from quarterback.database import get_session

        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
            event = result.scalars().first()

            if not event:
                return

            webhook_result = await session.execute(
                select(Webhook).where(Webhook.id == event.webhook_id)
            )
            webhook = webhook_result.scalars().first()

            if not webhook or not webhook.active:
                event.status = "cancelled"
                await session.commit()
                return

            payload = json.loads(event.payload)
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event.event_type,
                "X-Webhook-Delivery": str(event.id),
            }

            if webhook.secret:
                signature = hmac.new(
                    webhook.secret.encode(),
                    json.dumps(payload).encode(),
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Webhook-Signature"] = f"sha256={signature}"

            try:
                async with aiohttp.ClientSession() as client:
                    async with client.post(
                        webhook.url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        event.status = "sent" if response.status < 400 else "failed"
                        event.response_code = response.status
                        event.response_body = await response.text()
                        event.sent_at = datetime.utcnow()

                        webhook.last_triggered_at = datetime.utcnow()
                        if response.status >= 400:
                            webhook.failure_count += 1
                        else:
                            webhook.failure_count = 0

            except Exception as e:
                event.status = "failed"
                event.response_body = str(e)
                event.sent_at = datetime.utcnow()
                webhook.failure_count += 1

            await session.commit()

    async def get_agent_ready_tasks(
        self,
        session: AsyncSession,
        agent_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy.orm import joinedload

        query = (
            select(Task)
            .options(joinedload(Task.project))
            .where(Task.agent_ready.is_(True))
            .where(Task.agent_status.in_([None, "queued"]))
        )

        query = query.limit(limit)
        result = await session.execute(query)
        tasks = result.scalars().all()

        task_list = []
        for task in tasks:
            agent_config = json.loads(task.agent_config) if task.agent_config else {}

            if agent_type and agent_config.get("agent_type") != agent_type:
                continue

            task_list.append(
                {
                    "task_id": task.id,
                    "description": task.description,
                    "project": task.project.name if task.project else None,
                    "priority": task.priority,
                    "effort": task.effort,
                    "impact": task.impact,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "notes": task.notes,
                    "agent_config": agent_config,
                    "created_at": task.created_at.isoformat(),
                }
            )

        return task_list

    async def update_agent_status(
        self,
        session: AsyncSession,
        task_id: int,
        agent_status: str,
        agent_output: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalars().first()

        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        task.agent_status = agent_status
        if agent_output:
            task.agent_output = agent_output

        if agent_status == "processing" and not task.agent_started_at:
            task.agent_started_at = datetime.utcnow()

        if agent_status in ["completed", "failed"]:
            task.agent_completed_at = datetime.utcnow()
            task.agent_ready = False

            if agent_status == "completed":
                task.status = "completed"
                task.completed_at = datetime.utcnow()

        await session.commit()

        await self.trigger_event(
            session,
            "task.agent_status_update",
            {
                "task_id": task.id,
                "agent_status": agent_status,
                "agent_output": agent_output,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        return {
            "success": True,
            "message": f"Task {task_id} agent status updated to {agent_status}",
        }

    async def mark_task_agent_ready(
        self,
        session: AsyncSession,
        task_id: int,
        agent_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalars().first()

        if not task:
            return {"success": False, "error": f"Task {task_id} not found"}

        task.agent_config = json.dumps(agent_config)
        task.agent_ready = True
        task.agent_status = "queued"
        await session.commit()

        await self.trigger_event(
            session,
            "task.agent_ready",
            {
                "task_id": task.id,
                "description": task.description,
                "project": task.project.name if task.project else None,
                "priority": task.priority,
                "agent_config": agent_config,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        return {
            "success": True,
            "task_id": task.id,
            "message": f"Task {task_id} marked as agent-ready",
        }


WEBHOOK_EVENTS = [
    "task.created",
    "task.updated",
    "task.completed",
    "task.agent_ready",
    "task.agent_status_update",
    "project.created",
    "project.updated",
    "*",
]
