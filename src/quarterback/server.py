#!/usr/bin/env python3
"""
Quarterback MCP Server
Strategic task management with cross-project prioritization for Claude.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List
import yaml

from mcp.server import Server
from mcp.types import Resource, Tool, TextContent
import mcp.server.stdio

from quarterback.config import ORG_CONTEXT_DIR
from quarterback.database import (
    init_db,
    get_session,
    Organization,
    Workflow,
    Project,
    Task,
    History,
    AdvisoryDocument,
)
from quarterback.prioritization import PrioritizationEngine
from quarterback.time_planner import TimeAwarePlanner
from quarterback.advisory_analyzer import AdvisoryAnalyzer
from quarterback.webhooks import WebhookManager, WEBHOOK_EVENTS
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload


class QuarterbackServer:
    """MCP Server for strategic task management."""

    def __init__(self):
        self.server = Server("quarterback")
        self.db_engine = None
        self.org_context = {}
        self.context_dir = str(ORG_CONTEXT_DIR)
        self.time_planner = TimeAwarePlanner()
        self.webhook_manager = None

        @self.server.list_tools()
        async def handle_list_tools():
            return await self.list_tools()

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict):
            return await self.call_tool(name, arguments)

        @self.server.list_resources()
        async def handle_list_resources():
            return await self.list_resources()

        @self.server.read_resource()
        async def handle_read_resource(uri: str):
            return await self.read_resource(uri)

    async def initialize(self):
        self.db_engine = await init_db()
        await self._load_org_context()
        await self._ensure_default_org()

        self.webhook_manager = WebhookManager(self.db_engine)
        await self.webhook_manager.start_worker()

    async def _load_org_context(self):
        try:
            goals_path = os.path.join(self.context_dir, "goals.md")
            if os.path.exists(goals_path):
                with open(goals_path, "r") as f:
                    self.org_context["goals_content"] = f.read()

            workflows_path = os.path.join(self.context_dir, "workflows.yaml")
            if os.path.exists(workflows_path):
                with open(workflows_path, "r") as f:
                    self.org_context["workflows"] = yaml.safe_load(f)

            projects_path = os.path.join(self.context_dir, "projects.yaml")
            if os.path.exists(projects_path):
                with open(projects_path, "r") as f:
                    self.org_context["projects"] = yaml.safe_load(f)

            constraints_path = os.path.join(self.context_dir, "constraints.md")
            if os.path.exists(constraints_path):
                with open(constraints_path, "r") as f:
                    self.org_context["constraints_content"] = f.read()

        except Exception as e:
            print(f"Error loading org context: {e}")

    async def _ensure_default_org(self):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Organization))
            org = result.scalars().first()

            if not org:
                org = Organization(name="Default Organization")
                session.add(org)
                await session.commit()

    async def list_tools(self) -> List[Tool]:
        return [
            Tool(
                name="get_priorities",
                description="Get prioritized list of tasks based on organizational context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "timeframe": {
                            "type": "string",
                            "enum": ["today", "this_week", "all"],
                            "default": "today",
                        },
                        "project_name": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "all"]},
                        "include_closed": {"type": "boolean", "default": False},
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            ),
            Tool(
                name="add_task",
                description="Add a new task with full metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "project_name": {"type": "string"},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "effort": {"type": "number", "description": "Estimated hours"},
                        "impact": {"type": "integer", "minimum": 1, "maximum": 5},
                        "due_date": {"type": "string", "format": "date-time"},
                        "notes": {"type": "string"},
                        "cost": {
                            "type": "number",
                            "description": "Financial cost associated with this task",
                        },
                    },
                    "required": ["description"],
                },
            ),
            Tool(
                name="update_task",
                description="Update an existing task.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "blocked", "closed"],
                        },
                        "cost": {
                            "type": "number",
                            "description": "Financial cost associated with this task",
                        },
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "effort": {"type": "number"},
                        "impact": {"type": "integer", "minimum": 1, "maximum": 5},
                        "notes": {"type": "string"},
                    },
                    "required": ["task_id"],
                },
            ),
            Tool(
                name="get_quick_wins",
                description="Identify quick win tasks (high impact, low effort).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                },
            ),
            Tool(
                name="detect_conflicts",
                description="Detect conflicting priorities and resource constraints.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="assess_task_value",
                description="Assess whether a proposed task aligns with organizational goals.",
                inputSchema={
                    "type": "object",
                    "properties": {"task_description": {"type": "string"}},
                    "required": ["task_description"],
                },
            ),
            Tool(
                name="get_blocking_tasks",
                description="Get tasks that are blocking other work.",
                inputSchema={
                    "type": "object",
                    "properties": {"project_name": {"type": "string"}},
                },
            ),
            Tool(
                name="add_project",
                description="Add a new project.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "path": {"type": "string"},
                        "workflow_name": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "status": {
                            "type": "string",
                            "enum": ["active", "paused", "completed", "archived"],
                        },
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="list_projects",
                description="List all projects.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["active", "paused", "completed", "archived", "all"],
                            "default": "active",
                        }
                    },
                },
            ),
            Tool(
                name="update_project",
                description="Update a project's properties.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["active", "paused", "completed", "archived"],
                        },
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "description": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="get_organizational_summary",
                description="Get comprehensive organizational state summary.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="add_advisory_document",
                description="Add a new advisory document for review and analysis.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "source": {"type": "string"},
                        "source_type": {
                            "type": "string",
                            "enum": [
                                "article",
                                "book",
                                "expert_advice",
                                "video",
                                "podcast",
                                "other",
                            ],
                        },
                        "project_name": {"type": "string"},
                        "workflow_name": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                        "auto_analyze": {"type": "boolean", "default": True},
                    },
                    "required": ["title", "content"],
                },
            ),
            Tool(
                name="list_advisory_documents",
                description="List advisory documents with filtering.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": [
                                "all",
                                "pending_review",
                                "analyzed",
                                "approved",
                                "rejected",
                                "partially_adopted",
                            ],
                            "default": "all",
                        },
                        "project_name": {"type": "string"},
                        "workflow_name": {"type": "string"},
                        "source_type": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            ),
            Tool(
                name="get_advisory_document",
                description="Get full details of a specific advisory document.",
                inputSchema={
                    "type": "object",
                    "properties": {"document_id": {"type": "integer"}},
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="analyze_advisory_document",
                description="Analyze an advisory document against organizational context.",
                inputSchema={
                    "type": "object",
                    "properties": {"document_id": {"type": "integer"}},
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="discuss_advisory_recommendations",
                description="Facilitate discussion about advisory recommendations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "integer"},
                        "recommendation_ids": {"type": "array", "items": {"type": "integer"}},
                        "user_feedback": {"type": "string"},
                    },
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="adopt_advisory_recommendations",
                description="Approve or reject recommendations, optionally creating tasks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "integer"},
                        "approved_recommendation_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "rejected_recommendation_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "create_tasks": {"type": "boolean", "default": False},
                        "adoption_notes": {"type": "string"},
                    },
                    "required": ["document_id"],
                },
            ),
            Tool(
                name="register_webhook",
                description="Register a webhook endpoint to receive task events.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                        "events": {
                            "type": "array",
                            "items": {"type": "string", "enum": WEBHOOK_EVENTS},
                        },
                        "secret": {"type": "string"},
                    },
                    "required": ["name", "url", "events"],
                },
            ),
            Tool(
                name="list_webhooks",
                description="List all registered webhooks.",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="update_webhook",
                description="Update a webhook configuration.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "webhook_id": {"type": "integer"},
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                        "events": {"type": "array", "items": {"type": "string"}},
                        "secret": {"type": "string"},
                        "active": {"type": "boolean"},
                    },
                    "required": ["webhook_id"],
                },
            ),
            Tool(
                name="delete_webhook",
                description="Delete a registered webhook.",
                inputSchema={
                    "type": "object",
                    "properties": {"webhook_id": {"type": "integer"}},
                    "required": ["webhook_id"],
                },
            ),
            Tool(
                name="mark_task_agent_ready",
                description="Mark a task for autonomous agent execution.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "agent_config": {
                            "type": "object",
                            "properties": {
                                "autonomy_level": {
                                    "type": "string",
                                    "enum": ["draft", "checkpoint", "autonomous"],
                                },
                                "agent_type": {
                                    "type": "string",
                                    "enum": ["research", "content", "dev", "social", "outreach"],
                                },
                                "checkpoint_rules": {"type": "object"},
                                "output_location": {"type": "string"},
                                "context": {"type": "string"},
                            },
                        },
                    },
                    "required": ["task_id", "agent_config"],
                },
            ),
            Tool(
                name="get_agent_ready_tasks",
                description="Get tasks queued for agent execution.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_type": {
                            "type": "string",
                            "enum": ["research", "content", "dev", "social", "outreach"],
                        },
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            ),
            Tool(
                name="update_agent_status",
                description="Update agent execution status of a task.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "integer"},
                        "agent_status": {
                            "type": "string",
                            "enum": ["queued", "processing", "checkpoint", "completed", "failed"],
                        },
                        "agent_output": {"type": "string"},
                    },
                    "required": ["task_id", "agent_status"],
                },
            ),
            Tool(
                name="setup_quarterback",
                description=(
                    "Interactive setup wizard for new Quarterback installations. "
                    "Use action='get_interview' to get the interview template and current config status, "
                    "then conduct a conversational interview with the user, and finally call with "
                    "action='apply_setup' with the structured answers to configure Quarterback."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["get_interview", "apply_setup"],
                            "description": "get_interview returns the template; apply_setup writes config",
                        },
                        "answers": {
                            "type": "object",
                            "description": "Structured interview answers (required for apply_setup)",
                            "properties": {
                                "organization": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "mission": {"type": "string"},
                                        "vision": {"type": "string"},
                                    },
                                },
                                "goals": {
                                    "type": "object",
                                    "properties": {
                                        "annual": {"type": "array", "items": {"type": "string"}},
                                        "quarterly": {"type": "array", "items": {"type": "string"}},
                                        "anti_goals": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                                "workflows": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {"type": "string"},
                                            "goals": {"type": "array", "items": {"type": "string"}},
                                            "priority": {"type": "integer"},
                                            "status": {"type": "string"},
                                        },
                                    },
                                },
                                "projects": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "path": {"type": "string"},
                                            "workflow": {"type": "string"},
                                            "description": {"type": "string"},
                                            "status": {"type": "string"},
                                            "priority": {"type": "integer"},
                                            "revenue_potential": {"type": "string"},
                                            "strategic_value": {"type": "string"},
                                            "technical_complexity": {"type": "string"},
                                            "next_milestone": {"type": "string"},
                                        },
                                    },
                                },
                                "constraints": {
                                    "type": "object",
                                    "properties": {
                                        "hours_per_week": {"type": "number"},
                                        "working_hours": {"type": "string"},
                                        "working_days": {"type": "string"},
                                        "budget_monthly": {"type": "number"},
                                        "team_size": {"type": "integer"},
                                        "preferred_stack": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "avoid_stack": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                },
                            },
                        },
                        "overwrite_existing": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, backs up and replaces existing config files",
                        },
                    },
                    "required": ["action"],
                },
            ),
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            handler_map = {
                "get_priorities": self._get_priorities,
                "add_task": self._add_task,
                "update_task": self._update_task,
                "get_quick_wins": self._get_quick_wins,
                "detect_conflicts": lambda a: self._detect_conflicts(),
                "assess_task_value": self._assess_task_value,
                "get_blocking_tasks": self._get_blocking_tasks,
                "add_project": self._add_project,
                "update_project": self._update_project,
                "list_projects": self._list_projects,
                "get_organizational_summary": lambda a: self._get_organizational_summary(),
                "add_advisory_document": self._add_advisory_document,
                "list_advisory_documents": self._list_advisory_documents,
                "get_advisory_document": self._get_advisory_document,
                "analyze_advisory_document": self._analyze_advisory_document,
                "discuss_advisory_recommendations": self._discuss_advisory_recommendations,
                "adopt_advisory_recommendations": self._adopt_advisory_recommendations,
                "register_webhook": self._register_webhook,
                "list_webhooks": lambda a: self._list_webhooks(),
                "update_webhook": self._update_webhook,
                "delete_webhook": self._delete_webhook,
                "mark_task_agent_ready": self._mark_task_agent_ready,
                "get_agent_ready_tasks": self._get_agent_ready_tasks,
                "update_agent_status": self._update_agent_status,
                "setup_quarterback": self._setup_quarterback,
            }

            handler = handler_map.get(name)
            if handler:
                result = await handler(arguments)
            else:
                result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))]

    # --- Tool implementations (same logic as original, just using package imports) ---

    async def _get_priorities(self, args):
        timeframe = args.get("timeframe", "today")
        project_name = args.get("project_name")
        status = args.get("status", "all")
        limit = args.get("limit", 10)

        time_info = self.time_planner.get_available_hours_today()

        async with await get_session(self.db_engine) as session:
            query = select(Task).options(joinedload(Task.project))

            if status != "all":
                query = query.where(Task.status == status)
            else:
                exclude = (
                    ["completed", "closed"] if not args.get("include_closed") else ["completed"]
                )
                query = query.where(~Task.status.in_(exclude))

            if project_name:
                project_result = await session.execute(
                    select(Project).where(Project.name == project_name)
                )
                project = project_result.scalars().first()
                if project:
                    query = query.where(Task.project_id == project.id)

            if timeframe == "today":
                query = query.where(
                    or_(
                        Task.due_date <= datetime.now(),
                        Task.priority >= 4,
                        Task.status == "in_progress",
                    )
                )
            elif timeframe == "this_week":
                from datetime import timedelta

                week_end = datetime.now() + timedelta(days=7)
                query = query.where(or_(Task.due_date <= week_end, Task.priority >= 3))

            result = await session.execute(query)
            tasks = result.scalars().all()

            engine = PrioritizationEngine(self.org_context)
            priorities = []

            for task in tasks:
                project_dict = None
                if task.project:
                    project_dict = {
                        "name": task.project.name,
                        "priority": task.project.priority,
                        "revenue_potential": "unknown",
                        "strategic_value": "unknown",
                    }

                task_dict = {
                    "id": task.id,
                    "description": task.description,
                    "status": task.status,
                    "priority": task.priority,
                    "effort": task.effort,
                    "impact": task.impact,
                    "due_date": task.due_date,
                }

                score = engine.calculate_priority(task_dict, project_dict)
                priorities.append(
                    {
                        "task_id": task.id,
                        "description": task.description,
                        "project": task.project.name if task.project else "None",
                        "status": task.status,
                        "priority": task.priority,
                        "effort": task.effort or 0,
                        "due_date": task.due_date.isoformat() if task.due_date else None,
                        "score": score.total_score,
                        "recommendation": score.recommendation,
                        "reasoning": score.reasoning,
                    }
                )

            priorities.sort(key=lambda x: x["score"], reverse=True)

            if timeframe == "today" and time_info["is_working_day"]:
                filtered = self.time_planner.filter_tasks_by_available_time(
                    priorities, time_info["available_hours"], time_info["suggested_timeframe"]
                )
                return {
                    "timeframe": timeframe,
                    "time_context": {
                        "available_hours": time_info["available_hours"],
                        "is_working_hours": time_info["is_working_hours"],
                        "suggested_timeframe": time_info["suggested_timeframe"],
                        "explanation": time_info["reason"],
                    },
                    "priorities": filtered[:limit],
                    "total_found": len(tasks),
                    "total_fitting": len(filtered),
                }
            else:
                return {
                    "timeframe": timeframe,
                    "priorities": priorities[:limit],
                    "total_found": len(tasks),
                }

    async def _add_task(self, args):
        async with await get_session(self.db_engine) as session:
            project_id = None
            if args.get("project_name"):
                result = await session.execute(
                    select(Project).where(Project.name == args["project_name"])
                )
                project = result.scalars().first()
                if project:
                    project_id = project.id

            due_date = None
            if args.get("due_date"):
                try:
                    due_date = datetime.fromisoformat(args["due_date"].replace("Z", "+00:00"))
                except Exception:
                    pass

            task = Task(
                project_id=project_id,
                description=args["description"],
                priority=args.get("priority", 3),
                effort=args.get("effort"),
                impact=args.get("impact", 3),
                cost=args.get("cost"),
                due_date=due_date,
                notes=args.get("notes"),
                status="pending",
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)

            history = History(
                entity_type="task", entity_id=task.id, action="created", context=json.dumps(args)
            )
            session.add(history)
            await session.commit()

            await self.webhook_manager.trigger_event(
                session,
                "task.created",
                {
                    "task_id": task.id,
                    "description": task.description,
                    "project": args.get("project_name"),
                    "priority": task.priority,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return {
                "success": True,
                "task_id": task.id,
                "message": f"Task created: {task.description}",
            }

    async def _update_task(self, args):
        task_id = args["task_id"]
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            task = result.scalars().first()
            if not task:
                return {"success": False, "error": f"Task {task_id} not found"}

            if "status" in args:
                task.status = args["status"]
                if args["status"] == "completed":
                    task.completed_at = datetime.now()
            if "priority" in args:
                task.priority = args["priority"]
            if "effort" in args:
                task.effort = args["effort"]
            if "impact" in args:
                task.impact = args["impact"]
            if "notes" in args:
                task.notes = args["notes"]
            if "cost" in args:
                task.cost = args["cost"]

            await session.commit()

            history = History(
                entity_type="task", entity_id=task.id, action="updated", context=json.dumps(args)
            )
            session.add(history)
            await session.commit()

            event_type = "task.completed" if args.get("status") == "completed" else "task.updated"
            await self.webhook_manager.trigger_event(
                session,
                event_type,
                {
                    "task_id": task.id,
                    "description": task.description,
                    "status": task.status,
                    "changes": args,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            return {"success": True, "message": f"Task {task_id} updated"}

    async def _get_quick_wins(self, args):
        async with await get_session(self.db_engine) as session:
            query = (
                select(Task)
                .options(joinedload(Task.project))
                .where(Task.status.in_(["pending", "in_progress"]))
            )
            if args.get("project_name"):
                pr = await session.execute(
                    select(Project).where(Project.name == args["project_name"])
                )
                p = pr.scalars().first()
                if p:
                    query = query.where(Task.project_id == p.id)
            result = await session.execute(query)
            tasks = result.scalars().all()
            engine = PrioritizationEngine(self.org_context)
            task_dicts = [
                {
                    "id": t.id,
                    "description": t.description,
                    "priority": t.priority,
                    "effort": t.effort,
                    "impact": t.impact,
                    "status": t.status,
                }
                for t in tasks
            ]
            quick_wins = engine.identify_quick_wins(task_dicts, args.get("limit", 5))
            results = []
            for score in quick_wins:
                task = next(t for t in tasks if t.id == score.task_id)
                results.append(
                    {
                        "task_id": task.id,
                        "description": task.description,
                        "project": task.project.name if task.project else "None",
                        "effort_hours": task.effort,
                        "impact": task.impact,
                        "quick_win_score": score.quick_win_score,
                        "reasoning": score.reasoning,
                    }
                )
            return {"quick_wins": results}

    async def _detect_conflicts(self):
        async with await get_session(self.db_engine) as session:
            tasks_result = await session.execute(
                select(Task)
                .options(joinedload(Task.project))
                .where(Task.status.in_(["pending", "in_progress"]))
            )
            tasks = tasks_result.scalars().all()
            projects_result = await session.execute(
                select(Project).where(Project.status == "active")
            )
            projects = projects_result.scalars().all()
            task_dicts = [
                {
                    "id": t.id,
                    "description": t.description,
                    "priority": t.priority,
                    "effort": t.effort,
                    "due_date": t.due_date,
                }
                for t in tasks
            ]
            project_dicts = [
                {"name": p.name, "priority": p.priority, "status": p.status} for p in projects
            ]
            engine = PrioritizationEngine(self.org_context)
            conflicts = engine.detect_conflicts(task_dicts, project_dicts)
            return {"conflicts": conflicts, "total_conflicts": len(conflicts)}

    async def _assess_task_value(self, args):
        engine = PrioritizationEngine(self.org_context)
        return engine.assess_task_value(args["task_description"], self.org_context)

    async def _get_blocking_tasks(self, args):
        async with await get_session(self.db_engine) as session:
            query = (
                select(Task)
                .options(joinedload(Task.project))
                .where(and_(Task.status.in_(["pending", "in_progress"]), Task.priority >= 4))
            )
            if args.get("project_name"):
                pr = await session.execute(
                    select(Project).where(Project.name == args["project_name"])
                )
                p = pr.scalars().first()
                if p:
                    query = query.where(Task.project_id == p.id)
            result = await session.execute(query)
            tasks = result.scalars().all()
            return {
                "blocking_tasks": [
                    {
                        "task_id": t.id,
                        "description": t.description,
                        "project": t.project.name if t.project else "None",
                        "priority": t.priority,
                        "status": t.status,
                    }
                    for t in tasks
                ]
            }

    async def _add_project(self, args):
        async with await get_session(self.db_engine) as session:
            workflow_id = None
            if args.get("workflow_name"):
                result = await session.execute(
                    select(Workflow).where(Workflow.name == args["workflow_name"])
                )
                workflow = result.scalars().first()
                if workflow:
                    workflow_id = workflow.id
            project = Project(
                workflow_id=workflow_id,
                name=args["name"],
                path=args.get("path"),
                description=args.get("description"),
                priority=args.get("priority", 3),
                status=args.get("status", "active"),
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return {
                "success": True,
                "project_id": project.id,
                "message": f"Project created: {project.name}",
            }

    async def _update_project(self, args):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Project).where(Project.name == args["name"]))
            project = result.scalars().first()
            if not project:
                return {"success": False, "error": f"Project '{args['name']}' not found"}
            updated_fields = []
            if "status" in args:
                project.status = args["status"]
                updated_fields.append(f"status={args['status']}")
            if "priority" in args:
                project.priority = args["priority"]
                updated_fields.append(f"priority={args['priority']}")
            if "description" in args:
                project.description = args["description"]
                updated_fields.append("description")
            if "context" in args:
                if project.context:
                    project.context += f"\n\n---\n\nUpdated {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC:\n{args['context']}"
                else:
                    project.context = args["context"]
                updated_fields.append("context")
            await session.commit()
            return {
                "success": True,
                "project_id": project.id,
                "project_name": project.name,
                "updated_fields": updated_fields,
                "message": f"Project '{args['name']}' updated: {', '.join(updated_fields)}",
            }

    async def _list_projects(self, args):
        async with await get_session(self.db_engine) as session:
            query = select(Project)
            sf = args.get("status", "active")
            if sf != "all":
                query = query.where(Project.status == sf)
            result = await session.execute(query)
            projects = result.scalars().all()
            return {
                "projects": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "path": p.path,
                        "status": p.status,
                        "priority": p.priority,
                        "description": p.description,
                        "has_context": bool(p.context),
                    }
                    for p in projects
                ],
                "total": len(projects),
            }

    async def _get_organizational_summary(self):
        async with await get_session(self.db_engine) as session:
            projects = (
                (await session.execute(select(Project).where(Project.status == "active")))
                .scalars()
                .all()
            )
            all_tasks = (await session.execute(select(Task))).scalars().all()
            advisory_docs = (await session.execute(select(AdvisoryDocument))).scalars().all()
            return {
                "active_projects": len(projects),
                "project_summary": [
                    {
                        "name": p.name,
                        "priority": p.priority,
                        "task_count": len([t for t in all_tasks if t.project_id == p.id]),
                    }
                    for p in projects
                ],
                "task_statistics": {
                    "total": len(all_tasks),
                    "pending": len([t for t in all_tasks if t.status == "pending"]),
                    "in_progress": len([t for t in all_tasks if t.status == "in_progress"]),
                    "completed": len([t for t in all_tasks if t.status == "completed"]),
                    "blocked": len([t for t in all_tasks if t.status == "blocked"]),
                },
                "advisory_document_statistics": {
                    "total": len(advisory_docs),
                    "pending_review": len(
                        [d for d in advisory_docs if d.status == "pending_review"]
                    ),
                    "analyzed": len([d for d in advisory_docs if d.status == "analyzed"]),
                    "approved": len([d for d in advisory_docs if d.status == "approved"]),
                    "rejected": len([d for d in advisory_docs if d.status == "rejected"]),
                    "partially_adopted": len(
                        [d for d in advisory_docs if d.status == "partially_adopted"]
                    ),
                },
                "org_context_loaded": bool(self.org_context),
            }

    async def _add_advisory_document(self, args):
        async with await get_session(self.db_engine) as session:
            project_id = workflow_id = None
            if args.get("project_name"):
                r = await session.execute(
                    select(Project).where(Project.name == args["project_name"])
                )
                p = r.scalars().first()
                if p:
                    project_id = p.id
            if args.get("workflow_name"):
                r = await session.execute(
                    select(Workflow).where(Workflow.name == args["workflow_name"])
                )
                w = r.scalars().first()
                if w:
                    workflow_id = w.id
            doc = AdvisoryDocument(
                title=args["title"],
                content=args["content"],
                source=args.get("source"),
                source_type=args.get("source_type", "other"),
                project_id=project_id,
                workflow_id=workflow_id,
                tags=json.dumps(args.get("tags", [])),
                priority=args.get("priority", 3),
                status="pending_review",
            )
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
            analysis = None
            if args.get("auto_analyze", True):
                analyzer = AdvisoryAnalyzer(self.org_context)
                analysis = await analyzer.analyze_document(doc, session)
                doc.analysis_result = json.dumps(analysis)
                doc.status = "analyzed"
                doc.reviewed_at = datetime.utcnow()
                await session.commit()
            return {
                "success": True,
                "document_id": doc.id,
                "title": doc.title,
                "status": doc.status,
                "analysis": analysis,
                "message": f"Advisory document '{doc.title}' added"
                + (" and analyzed" if analysis else ""),
            }

    async def _list_advisory_documents(self, args):
        async with await get_session(self.db_engine) as session:
            query = select(AdvisoryDocument).options(
                joinedload(AdvisoryDocument.project), joinedload(AdvisoryDocument.workflow)
            )
            filters = []
            status = args.get("status", "all")
            if status != "all":
                filters.append(AdvisoryDocument.status == status)
            if args.get("project_name"):
                r = await session.execute(
                    select(Project).where(Project.name == args["project_name"])
                )
                p = r.scalars().first()
                if p:
                    filters.append(AdvisoryDocument.project_id == p.id)
            if args.get("workflow_name"):
                r = await session.execute(
                    select(Workflow).where(Workflow.name == args["workflow_name"])
                )
                w = r.scalars().first()
                if w:
                    filters.append(AdvisoryDocument.workflow_id == w.id)
            if args.get("source_type"):
                filters.append(AdvisoryDocument.source_type == args["source_type"])
            if filters:
                query = query.where(and_(*filters))
            query = query.order_by(AdvisoryDocument.created_at.desc()).limit(args.get("limit", 10))
            result = await session.execute(query)
            documents = result.scalars().all()
            return {
                "documents": [
                    {
                        "id": d.id,
                        "title": d.title,
                        "source": d.source,
                        "source_type": d.source_type,
                        "status": d.status,
                        "project": d.project.name if d.project else None,
                        "workflow": d.workflow.name if d.workflow else None,
                        "tags": json.loads(d.tags) if d.tags else [],
                        "priority": d.priority,
                        "created_at": d.created_at.isoformat(),
                    }
                    for d in documents
                ],
                "count": len(documents),
            }

    async def _get_advisory_document(self, args):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument)
                .options(
                    joinedload(AdvisoryDocument.project),
                    joinedload(AdvisoryDocument.workflow),
                    joinedload(AdvisoryDocument.recommendations),
                )
                .where(AdvisoryDocument.id == args["document_id"])
            )
            doc = result.scalars().first()
            if not doc:
                return {"error": f"Advisory document {args['document_id']} not found"}
            return {
                "id": doc.id,
                "title": doc.title,
                "source": doc.source,
                "source_type": doc.source_type,
                "content": doc.content,
                "status": doc.status,
                "project": doc.project.name if doc.project else None,
                "workflow": doc.workflow.name if doc.workflow else None,
                "tags": json.loads(doc.tags) if doc.tags else [],
                "priority": doc.priority,
                "analysis": json.loads(doc.analysis_result) if doc.analysis_result else None,
                "recommendations": [
                    {
                        "id": r.id,
                        "text": r.recommendation_text,
                        "category": r.category,
                        "status": r.status,
                        "conflicts": json.loads(r.conflicts_with) if r.conflicts_with else [],
                        "synergies": json.loads(r.aligns_with) if r.aligns_with else [],
                        "estimated_effort_hours": r.estimated_effort_hours,
                        "estimated_impact": r.estimated_impact,
                        "decision_rationale": r.decision_rationale,
                    }
                    for r in doc.recommendations
                ],
                "created_at": doc.created_at.isoformat(),
                "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
            }

    async def _analyze_advisory_document(self, args):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument).where(AdvisoryDocument.id == args["document_id"])
            )
            doc = result.scalars().first()
            if not doc:
                return {"error": f"Advisory document {args['document_id']} not found"}
            analyzer = AdvisoryAnalyzer(self.org_context)
            analysis = await analyzer.analyze_document(doc, session)
            doc.analysis_result = json.dumps(analysis)
            doc.status = "analyzed"
            doc.reviewed_at = datetime.utcnow()
            await session.commit()
            return {
                "document_id": doc.id,
                "title": doc.title,
                "analysis": analysis,
                "message": "Analysis complete",
            }

    async def _discuss_advisory_recommendations(self, args):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument)
                .options(joinedload(AdvisoryDocument.recommendations))
                .where(AdvisoryDocument.id == args["document_id"])
            )
            doc = result.scalars().first()
            if not doc:
                return {"error": f"Advisory document {args['document_id']} not found"}
            rec_ids = args.get("recommendation_ids", [])
            recs = (
                [r for r in doc.recommendations if r.id in rec_ids]
                if rec_ids
                else doc.recommendations
            )
            discussion = {
                "document_title": doc.title,
                "document_id": doc.id,
                "user_feedback": args.get("user_feedback"),
                "recommendations": [],
            }
            for rec in recs:
                conflicts = json.loads(rec.conflicts_with) if rec.conflicts_with else []
                synergies = json.loads(rec.aligns_with) if rec.aligns_with else []
                rd = {
                    "id": rec.id,
                    "text": rec.recommendation_text,
                    "category": rec.category,
                    "status": rec.status,
                    "pros": list(synergies),
                    "cons": list(conflicts),
                    "estimated_effort_hours": rec.estimated_effort_hours,
                    "estimated_impact": rec.estimated_impact,
                }
                if rec.estimated_impact and rec.estimated_impact >= 4:
                    rd["pros"].append(f"High impact potential ({rec.estimated_impact}/5)")
                if rec.estimated_effort_hours and rec.estimated_effort_hours < 5:
                    rd["pros"].append(f"Quick to implement (~{rec.estimated_effort_hours}h)")
                if rec.estimated_effort_hours and rec.estimated_effort_hours > 20:
                    rd["cons"].append(
                        f"Significant time investment (~{rec.estimated_effort_hours}h)"
                    )
                discussion["recommendations"].append(rd)
            analysis = json.loads(doc.analysis_result) if doc.analysis_result else {}
            discussion["overall_assessment"] = analysis.get("overall_assessment", "unknown")
            discussion["overall_recommendation"] = analysis.get("recommendation", "")
            discussion["items_for_discussion"] = analysis.get("items_for_discussion", [])
            return discussion

    async def _adopt_advisory_recommendations(self, args):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument)
                .options(joinedload(AdvisoryDocument.recommendations))
                .where(AdvisoryDocument.id == args["document_id"])
            )
            doc = result.scalars().first()
            if not doc:
                return {"error": f"Advisory document {args['document_id']} not found"}
            approved_ids = args.get("approved_recommendation_ids", [])
            rejected_ids = args.get("rejected_recommendation_ids", [])
            create_tasks = args.get("create_tasks", False)
            created_tasks = []
            for rec in doc.recommendations:
                if rec.id in approved_ids:
                    rec.status = "approved"
                    rec.decided_at = datetime.utcnow()
                    if create_tasks and rec.implemented_as_task_id is None:
                        task = Task(
                            project_id=doc.project_id,
                            description=rec.recommendation_text,
                            priority=rec.estimated_impact or 3,
                            effort=rec.estimated_effort_hours,
                            impact=rec.estimated_impact,
                            status="pending",
                            notes=f"From advisory: {doc.title}",
                        )
                        session.add(task)
                        await session.flush()
                        rec.implemented_as_task_id = task.id
                        created_tasks.append(
                            {
                                "task_id": task.id,
                                "description": task.description,
                                "recommendation_id": rec.id,
                            }
                        )
                elif rec.id in rejected_ids:
                    rec.status = "rejected"
                    rec.decided_at = datetime.utcnow()
            total_recs = len(doc.recommendations)
            ac = len([r for r in doc.recommendations if r.status == "approved"])
            rc = len([r for r in doc.recommendations if r.status == "rejected"])
            if ac == total_recs:
                doc.status = "approved"
            elif rc == total_recs:
                doc.status = "rejected"
            elif ac > 0 or rc > 0:
                doc.status = "partially_adopted"
            doc.adopted_at = datetime.utcnow()
            doc.adoption_notes = args.get("adoption_notes")
            await session.commit()
            return {
                "success": True,
                "document_id": doc.id,
                "document_status": doc.status,
                "approved_count": len(approved_ids),
                "rejected_count": len(rejected_ids),
                "created_tasks": created_tasks,
                "message": f"Updated {len(approved_ids) + len(rejected_ids)} recommendations",
            }

    async def _register_webhook(self, args):
        async with await get_session(self.db_engine) as session:
            return await self.webhook_manager.register_webhook(
                session,
                name=args["name"],
                url=args["url"],
                events=args["events"],
                secret=args.get("secret"),
            )

    async def _list_webhooks(self):
        async with await get_session(self.db_engine) as session:
            webhooks = await self.webhook_manager.list_webhooks(session)
            return {"webhooks": webhooks, "count": len(webhooks)}

    async def _update_webhook(self, args):
        webhook_id = args.pop("webhook_id")
        async with await get_session(self.db_engine) as session:
            return await self.webhook_manager.update_webhook(session, webhook_id, **args)

    async def _delete_webhook(self, args):
        async with await get_session(self.db_engine) as session:
            return await self.webhook_manager.delete_webhook(session, args["webhook_id"])

    async def _mark_task_agent_ready(self, args):
        async with await get_session(self.db_engine) as session:
            return await self.webhook_manager.mark_task_agent_ready(
                session, task_id=args["task_id"], agent_config=args["agent_config"]
            )

    async def _get_agent_ready_tasks(self, args):
        async with await get_session(self.db_engine) as session:
            tasks = await self.webhook_manager.get_agent_ready_tasks(
                session, agent_type=args.get("agent_type"), limit=args.get("limit", 10)
            )
            return {"tasks": tasks, "count": len(tasks)}

    async def _update_agent_status(self, args):
        async with await get_session(self.db_engine) as session:
            return await self.webhook_manager.update_agent_status(
                session,
                task_id=args["task_id"],
                agent_status=args["agent_status"],
                agent_output=args.get("agent_output"),
            )

    async def _setup_quarterback(self, args):
        from quarterback.setup_wizard import get_interview_template, apply_setup

        action = args.get("action")
        if action == "get_interview":
            return get_interview_template()
        elif action == "apply_setup":
            answers = args.get("answers", {})
            overwrite = args.get("overwrite_existing", False)
            result = await apply_setup(answers, engine=self.db_engine, overwrite=overwrite)
            if result.get("success"):
                await self._load_org_context()
            return result
        else:
            return {"error": f"Unknown action: {action}. Use 'get_interview' or 'apply_setup'."}

    async def list_resources(self) -> List[Resource]:
        return [
            Resource(
                uri="context://goals",
                name="Organizational Goals",
                mimeType="text/markdown",
                description="Current organizational goals and strategic priorities",
            ),
            Resource(
                uri="context://workflows",
                name="Active Workflows",
                mimeType="application/json",
                description="Workflow definitions and project groupings",
            ),
            Resource(
                uri="context://constraints",
                name="Constraints",
                mimeType="text/markdown",
                description="Resource constraints and strategic boundaries",
            ),
        ]

    async def read_resource(self, uri: str) -> str:
        if uri == "context://goals":
            return self.org_context.get("goals_content", "# No goals defined")
        elif uri == "context://workflows":
            return json.dumps(self.org_context.get("workflows", {}), indent=2)
        elif uri == "context://constraints":
            return self.org_context.get("constraints_content", "# No constraints defined")
        else:
            raise ValueError(f"Unknown resource: {uri}")


async def _main():
    server_instance = QuarterbackServer()
    await server_instance.initialize()

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream, write_stream, server_instance.server.create_initialization_options()
        )


def run():
    """Entry point for quarterback-server command."""
    asyncio.run(_main())


if __name__ == "__main__":
    run()
