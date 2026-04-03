#!/usr/bin/env python3
"""
Quarterback CLI — Strategic task prioritization without an AI runtime.
"""

import asyncio
import sys
import shutil
import sqlite3
from datetime import datetime
from typing import Optional
import argparse
from pathlib import Path

from quarterback.config import QUARTERBACK_HOME, DATA_DIR, ORG_CONTEXT_DIR, CONFIG_DIR, DB_PATH
from quarterback.database import (
    init_db,
    get_session,
    Project,
    Task,
    AdvisoryDocument,
)
from quarterback.prioritization import PrioritizationEngine
from quarterback.time_planner import TimeAwarePlanner
from quarterback.context_manager import get_project_context
from quarterback.advisory_analyzer import AdvisoryAnalyzer
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import joinedload
import yaml
import os
import json


class QuarterbackCLI:
    """Standalone CLI for task management."""

    def __init__(self):
        self.db_engine = None
        self.org_context = {}
        self.context_dir = ORG_CONTEXT_DIR
        self.time_planner = TimeAwarePlanner()

    async def initialize(self):
        self.db_engine = await init_db()
        await self._load_org_context()

    async def _load_org_context(self):
        try:
            goals_path = self.context_dir / "goals.md"
            if goals_path.exists():
                self.org_context["goals_content"] = goals_path.read_text()

            workflows_path = self.context_dir / "workflows.yaml"
            if workflows_path.exists():
                self.org_context["workflows"] = yaml.safe_load(workflows_path.read_text())

            projects_path = self.context_dir / "projects.yaml"
            if projects_path.exists():
                self.org_context["projects"] = yaml.safe_load(projects_path.read_text())

            constraints_path = self.context_dir / "constraints.md"
            if constraints_path.exists():
                self.org_context["constraints_content"] = constraints_path.read_text()

        except Exception as e:
            print(f"Warning: Error loading org context: {e}", file=sys.stderr)

    async def cmd_priorities(
        self, timeframe: str = "today", project: Optional[str] = None, limit: int = 10
    ):
        time_info = self.time_planner.get_available_hours_today()

        async with await get_session(self.db_engine) as session:
            query = select(Task).options(joinedload(Task.project))
            query = query.where(Task.status.in_(["pending", "in_progress"]))

            if project:
                project_result = await session.execute(
                    select(Project).where(Project.name == project)
                )
                proj = project_result.scalars().first()
                if proj:
                    query = query.where(Task.project_id == proj.id)
                else:
                    print(f"Error: Project '{project}' not found", file=sys.stderr)
                    return

            if timeframe == "today":
                query = query.where(
                    or_(
                        Task.due_date <= datetime.now(),
                        Task.priority >= 4,
                        Task.status == "in_progress",
                    )
                )
            elif timeframe == "week":
                from datetime import timedelta

                week_end = datetime.now() + timedelta(days=7)
                query = query.where(or_(Task.due_date <= week_end, Task.priority >= 3))

            result = await session.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                print(f"No tasks found for timeframe: {timeframe}")
                return

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
                        "task": task,
                        "effort": task.effort or 0,
                        "score": score.total_score,
                        "recommendation": score.recommendation,
                        "reasoning": score.reasoning,
                    }
                )

            priorities.sort(key=lambda x: x["score"], reverse=True)

            if timeframe == "today" and time_info["is_working_day"]:
                print(f"\n{'=' * 80}")
                print("TIME CONTEXT")
                print(f"{'=' * 80}")
                print(f"Available hours: {time_info['available_hours']:.1f}h")
                print(f"Suggested focus: {time_info['suggested_timeframe']}")
                print(f"Reason: {time_info['reason']}")
                print()

                filtered_priorities = self.time_planner.filter_tasks_by_available_time(
                    priorities,
                    time_info["available_hours"],
                    time_info["suggested_timeframe"],
                )

                priorities_to_show = filtered_priorities[:limit]
                total_filtered = len(filtered_priorities)
            else:
                priorities_to_show = priorities[:limit]
                total_filtered = len(priorities)

            print(f"{'=' * 80}")
            print(f"PRIORITIES - {timeframe.upper()}")
            print(f"{'=' * 80}\n")

            for i, p in enumerate(priorities_to_show, 1):
                task = p["task"]
                score = p["score"]
                rec = p["recommendation"]
                effort = p["effort"]

                print(f"{i}. [{task.id}] {task.description[:60]}")
                print(f"   Score: {score:.2f} | {rec}")
                print(f"   Project: {task.project.name if task.project else 'None'}")
                print(f"   Status: {task.status} | Priority: {task.priority} | Effort: {effort}h")

                if p["reasoning"]:
                    print(f"   Reasoning: {', '.join(p['reasoning'][:3])}")

                print()

            print(f"{'=' * 80}")
            if timeframe == "today" and time_info["is_working_day"]:
                print(
                    f"Total: {len(tasks)} tasks found, {total_filtered} fit in available time, showing top {len(priorities_to_show)}"
                )
            else:
                print(f"Total: {len(tasks)} tasks found, showing top {len(priorities_to_show)}")
            print(f"{'=' * 80}\n")

    async def cmd_add_task(
        self,
        description: str,
        project: Optional[str] = None,
        priority: int = 3,
        effort: Optional[float] = None,
        impact: int = 3,
        due_date: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        async with await get_session(self.db_engine) as session:
            project_id = None
            if project:
                result = await session.execute(select(Project).where(Project.name == project))
                proj = result.scalars().first()
                if proj:
                    project_id = proj.id
                else:
                    print(f"Warning: Project '{project}' not found", file=sys.stderr)

            due_dt = None
            if due_date:
                try:
                    due_dt = datetime.fromisoformat(due_date)
                except Exception:
                    print(f"Warning: Invalid date format '{due_date}'", file=sys.stderr)

            task = Task(
                project_id=project_id,
                description=description,
                priority=priority,
                effort=effort,
                impact=impact,
                due_date=due_dt,
                notes=notes,
                status="pending",
            )

            session.add(task)
            await session.commit()
            await session.refresh(task)

            print(f"Task created: #{task.id} - {task.description}")

    async def cmd_update_task(
        self,
        task_id: int,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        effort: Optional[float] = None,
        impact: Optional[int] = None,
        notes: Optional[str] = None,
    ):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            task = result.scalars().first()

            if not task:
                print(f"Error: Task #{task_id} not found", file=sys.stderr)
                return

            updated = []

            if status:
                task.status = status
                updated.append(f"status={status}")
                if status == "completed":
                    task.completed_at = datetime.now()

            if priority is not None:
                task.priority = priority
                updated.append(f"priority={priority}")

            if effort is not None:
                task.effort = effort
                updated.append(f"effort={effort}")

            if impact is not None:
                task.impact = impact
                updated.append(f"impact={impact}")

            if notes is not None:
                task.notes = notes
                updated.append("notes")

            await session.commit()

            print(f"Task #{task_id} updated: {', '.join(updated)}")

    async def cmd_list_tasks(self, status: Optional[str] = None, project: Optional[str] = None):
        async with await get_session(self.db_engine) as session:
            query = select(Task).options(joinedload(Task.project))

            if status:
                query = query.where(Task.status == status)

            if project:
                project_result = await session.execute(
                    select(Project).where(Project.name == project)
                )
                proj = project_result.scalars().first()
                if proj:
                    query = query.where(Task.project_id == proj.id)

            result = await session.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                print("No tasks found")
                return

            print(f"\n{'=' * 80}")
            print(f"TASKS ({len(tasks)} total)")
            print(f"{'=' * 80}\n")

            for task in tasks:
                status_icon = {"pending": "o", "in_progress": "-", "completed": "x", "blocked": "!"}
                icon = status_icon.get(task.status, "?")

                print(
                    f"[{icon}] [{task.id}] {task.description[:60]} (P{task.priority} | {task.status})"
                )
                if task.project:
                    print(f"   Project: {task.project.name}")
                if task.due_date:
                    print(f"   Due: {task.due_date.strftime('%Y-%m-%d')}")
                print()

            print(f"{'=' * 80}\n")

    async def cmd_quick_wins(self, project: Optional[str] = None, limit: int = 5):
        async with await get_session(self.db_engine) as session:
            query = (
                select(Task)
                .options(joinedload(Task.project))
                .where(Task.status.in_(["pending", "in_progress"]))
            )

            if project:
                project_result = await session.execute(
                    select(Project).where(Project.name == project)
                )
                proj = project_result.scalars().first()
                if proj:
                    query = query.where(Task.project_id == proj.id)

            result = await session.execute(query)
            tasks = result.scalars().all()

            if not tasks:
                print("No tasks found")
                return

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

            quick_wins = engine.identify_quick_wins(task_dicts, limit)

            if not quick_wins:
                print("No quick wins found")
                return

            print(f"\n{'=' * 80}")
            print("QUICK WINS")
            print(f"{'=' * 80}\n")

            for i, score in enumerate(quick_wins, 1):
                task = next(t for t in tasks if t.id == score.task_id)
                print(f"{i}. [{task.id}] {task.description[:60]}")
                print(f"   Score: {score.quick_win_score:.2f} | {score.recommendation}")
                print(f"   Project: {task.project.name if task.project else 'None'}")
                print(f"   Effort: {task.effort}h | Impact: {task.impact}/5")
                print(f"   Why: {', '.join(score.reasoning[:2])}")
                print()

            print(f"{'=' * 80}\n")

    async def cmd_conflicts(self):
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

            if not conflicts:
                print("No conflicts detected")
                return

            print(f"\n{'=' * 80}")
            print("CONFLICTS DETECTED")
            print(f"{'=' * 80}\n")

            for conflict in conflicts:
                print(f"{conflict['type'].upper()} - {conflict['severity'].upper()}")
                print(f"   {conflict['description']}")
                print()

            print(f"{'=' * 80}\n")

    async def cmd_projects(self, status: str = "active"):
        async with await get_session(self.db_engine) as session:
            query = select(Project)

            if status != "all":
                query = query.where(Project.status == status)

            result = await session.execute(query)
            projects = result.scalars().all()

            if not projects:
                print(f"No {status} projects found")
                return

            print(f"\n{'=' * 80}")
            print(f"PROJECTS - {status.upper()} ({len(projects)} total)")
            print(f"{'=' * 80}\n")

            for proj in projects:
                tasks_result = await session.execute(select(Task).where(Task.project_id == proj.id))
                task_count = len(tasks_result.scalars().all())

                print(f"[{proj.id}] {proj.name} (Priority {proj.priority})")
                if proj.path:
                    print(f"   Path: {proj.path}")
                print(f"   Status: {proj.status} | Tasks: {task_count}")
                if proj.description:
                    print(f"   {proj.description[:70]}")
                print()

            print(f"{'=' * 80}\n")

    async def cmd_summary(self):
        async with await get_session(self.db_engine) as session:
            projects_result = await session.execute(
                select(Project).where(Project.status == "active")
            )
            projects = projects_result.scalars().all()

            tasks_result = await session.execute(select(Task))
            all_tasks = tasks_result.scalars().all()

            print(f"\n{'=' * 80}")
            print("ORGANIZATIONAL SUMMARY")
            print(f"{'=' * 80}\n")

            print(f"Active Projects: {len(projects)}")
            for p in projects[:5]:
                task_count = len([t for t in all_tasks if t.project_id == p.id])
                print(f"  - {p.name} (P{p.priority}) - {task_count} tasks")

            print("\nTask Statistics:")
            print(f"  Total: {len(all_tasks)}")
            print(f"  Pending: {len([t for t in all_tasks if t.status == 'pending'])}")
            print(f"  In Progress: {len([t for t in all_tasks if t.status == 'in_progress'])}")
            print(f"  Completed: {len([t for t in all_tasks if t.status == 'completed'])}")
            print(f"  Blocked: {len([t for t in all_tasks if t.status == 'blocked'])}")

            print("\nContext Loaded:")
            for key, label in [
                ("goals_content", "Goals"),
                ("workflows", "Workflows"),
                ("projects", "Projects"),
                ("constraints_content", "Constraints"),
            ]:
                loaded = "yes" if self.org_context.get(key) else "no"
                print(f"  {label}: {loaded}")

            print(f"\n{'=' * 80}\n")

    async def cmd_alert_check(self):
        try:
            from quarterback.alert_daemon import AlertDaemon

            daemon = AlertDaemon()
            await daemon.initialize()
            counts = await daemon.check_alerts()

            if "disabled" in counts:
                print("Alerts are disabled in config")
            elif "quiet_hours" in counts:
                print("Currently in quiet hours - no alerts sent")
            elif "inactive_day" in counts:
                print("Today is not an active day - no alerts sent")
            else:
                total = sum(counts.values())
                print(f"\n{'=' * 80}")
                print("ALERT CHECK RESULTS")
                print(f"{'=' * 80}\n")
                print(f"  Overdue: {counts.get('overdue', 0)}")
                print(f"  Due Today: {counts.get('due_today', 0)}")
                print(f"  Upcoming: {counts.get('upcoming', 0)}")
                print(f"  Time-Sensitive: {counts.get('time_sensitive', 0)}")
                print(f"\n  Total notifications sent: {total}")
                print(f"\n{'=' * 80}\n")

        except ImportError as e:
            print(f"Error: Could not import alert_daemon: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Error running alert check: {e}", file=sys.stderr)

    async def cmd_alert_summary(self):
        try:
            from quarterback.alert_daemon import AlertDaemon

            daemon = AlertDaemon()
            await daemon.initialize()
            success = await daemon.send_daily_summary()
            if success:
                print("Daily summary notification sent")
            else:
                print("Failed to send daily summary")
        except Exception as e:
            print(f"Error sending summary: {e}", file=sys.stderr)

    async def cmd_alert_test(self):
        try:
            from quarterback.notifications import TaskNotifier, NotificationPriority

            notifier = TaskNotifier()
            success = notifier.notify_quick_summary(
                "This is a test notification from Quarterback!", NotificationPriority.MEDIUM
            )
            if success:
                print("Test notification sent successfully")
            else:
                print("Failed to send test notification")
        except Exception as e:
            print(f"Error sending test notification: {e}", file=sys.stderr)

    async def cmd_alert_config(self):
        from quarterback.config import ALERTS_CONFIG_PATH

        config_path = ALERTS_CONFIG_PATH

        if not config_path.exists():
            print(f"Config file not found: {config_path}")
            print("Run 'quarterback init' to create default config")
            return

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            print(f"\n{'=' * 80}")
            print("ALERT CONFIGURATION")
            print(f"{'=' * 80}\n")

            print(f"Status: {'Enabled' if config.get('enabled') else 'Disabled'}")

            quiet = config.get("quiet_hours", {})
            if quiet.get("enabled"):
                print(f"Quiet Hours: {quiet.get('start')} - {quiet.get('end')}")
            else:
                print("Quiet Hours: Disabled")

            thresholds = config.get("thresholds", {})
            print("\nNotification Thresholds:")
            print(f"  Min Priority: {thresholds.get('min_priority', 4)}")
            print(f"  Upcoming Days: {thresholds.get('upcoming_days', 3)}")

            print(f"\nConfig file: {config_path}")
            print(f"\n{'=' * 80}\n")

        except Exception as e:
            print(f"Error reading config: {e}", file=sys.stderr)

    async def cmd_project_info(self, project_name: str):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Project).where(Project.name == project_name))
            project = result.scalars().first()

            if not project:
                print(f"Error: Project '{project_name}' not found", file=sys.stderr)
                return

            print(f"\n{'=' * 80}")
            print(f"PROJECT: {project.name}")
            print(f"{'=' * 80}\n")

            print(f"ID: {project.id}")
            print(f"Status: {project.status}")
            print(f"Priority: {project.priority}")
            if project.path:
                print(f"Path: {project.path}")
            if project.description:
                print(f"\nDescription:\n{project.description}")

            context_info = get_project_context(project.name, project.path, project.context)

            if context_info["unified_context"]:
                print(f"\n{'-' * 80}")
                print("CONTEXT:")
                print(f"{'-' * 80}")
                print(context_info["unified_context"])
            else:
                print("\nNo context stored.")

            print(f"\n{'=' * 80}\n")

    async def cmd_project_context(
        self, project_name: str, context: Optional[str] = None, action: str = "view"
    ):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(select(Project).where(Project.name == project_name))
            project = result.scalars().first()

            if not project:
                print(f"Error: Project '{project_name}' not found", file=sys.stderr)
                return

            if action == "view":
                if project.context:
                    print(f"\n{'=' * 80}")
                    print(f"CONTEXT: {project.name}")
                    print(f"{'=' * 80}\n")
                    print(project.context)
                    print(f"\n{'=' * 80}\n")
                else:
                    print(f"No context stored for project '{project_name}'")

            elif action == "add" and context:
                if project.context:
                    project.context += f"\n\n---\n\nAdded {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:\n{context}"
                else:
                    project.context = context
                await session.commit()
                print(f"Context added to project '{project_name}'")

            elif action == "replace" and context:
                project.context = context
                await session.commit()
                print(f"Context replaced for project '{project_name}'")

            elif action == "clear":
                project.context = None
                await session.commit()
                print(f"Context cleared for project '{project_name}'")

    async def cmd_plan_day(self):
        summary = self.time_planner.get_planning_summary()

        print(f"\n{'=' * 80}")
        print(f"DAILY PLAN - {summary['current_time']}")
        print(f"{'=' * 80}\n")

        time_info = summary["time_info"]

        print("TIME ANALYSIS")
        print(f"   Available hours: {time_info['available_hours']:.1f}h")
        print(f"   Working day: {'Yes' if time_info['is_working_day'] else 'No'}")
        print(
            f"   Current status: {'Working hours' if time_info['is_working_hours'] else 'Outside working hours'}"
        )
        print(f"   Focus: {time_info['suggested_timeframe']}")
        print(f"   {time_info['reason']}")
        print()

        if summary["recommendations"]:
            print("RECOMMENDATIONS")
            for rec in summary["recommendations"]:
                print(f"   - {rec}")
            print()

        if time_info["suggested_timeframe"] in ["today", "end_of_day"]:
            print("TODAY'S TASKS (filtered by available time)")
            print(f"{'=' * 80}\n")

            async with await get_session(self.db_engine) as session:
                query = (
                    select(Task)
                    .options(joinedload(Task.project))
                    .where(Task.status.in_(["pending", "in_progress"]))
                    .where(
                        or_(
                            Task.due_date <= datetime.now(),
                            Task.priority >= 4,
                            Task.status == "in_progress",
                        )
                    )
                )

                result = await session.execute(query)
                tasks = result.scalars().all()

                if tasks:
                    engine = PrioritizationEngine(self.org_context)
                    priorities = []

                    for task in tasks:
                        project_dict = None
                        if task.project:
                            project_dict = {
                                "name": task.project.name,
                                "priority": task.project.priority,
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
                                "task": task,
                                "effort": task.effort or 0,
                                "score": score.total_score,
                            }
                        )

                    priorities.sort(key=lambda x: x["score"], reverse=True)

                    filtered = self.time_planner.filter_tasks_by_available_time(
                        priorities,
                        time_info["available_hours"],
                        time_info["suggested_timeframe"],
                    )

                    total_effort = 0
                    for i, p in enumerate(filtered, 1):
                        task = p["task"]
                        effort = p["effort"]
                        total_effort += effort

                        print(f"{i}. [{task.id}] {task.description}")
                        print(
                            f"   Project: {task.project.name if task.project else 'None'} | Effort: {effort}h | Priority: {task.priority}"
                        )
                        if task.due_date:
                            print(f"   Due: {task.due_date.strftime('%Y-%m-%d')}")
                        print()

                    print(f"{'=' * 80}")
                    print(
                        f"Total: {len(filtered)} tasks ({total_effort:.1f}h) fit in {time_info['available_hours']:.1f}h available"
                    )
                else:
                    print("   No tasks found for today!")

        elif time_info["suggested_timeframe"] == "tomorrow":
            print("Too little time remaining today.")
            print("   Run this command tomorrow morning for your daily plan.")

        print(f"{'=' * 80}\n")

    async def cmd_advisory_add(
        self,
        title: str,
        content: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        source: Optional[str] = None,
        source_type: str = "other",
        project: Optional[str] = None,
        workflow: Optional[str] = None,
        tags: Optional[list] = None,
        priority: int = 3,
        auto_analyze: bool = True,
    ):
        if url:
            print(f"Fetching content from URL: {url}")
            try:
                fetched_content, fetched_title = _fetch_url_content(url)
                content = fetched_content
                if not title or title == "Untitled":
                    title = fetched_title
                if not source:
                    source = url
                print(f"Fetched: {fetched_title[:60]}...")
            except Exception as e:
                print(f"Error fetching URL: {e}", file=sys.stderr)
                return
        elif file_path:
            try:
                with open(os.path.expanduser(file_path), "r") as f:
                    content = f.read()
                print(f"Read {len(content)} characters from {file_path}")
            except Exception as e:
                print(f"Error reading file: {e}", file=sys.stderr)
                return
        elif not content:
            print("Error: Must provide --content, --file, or --url", file=sys.stderr)
            return

        async with await get_session(self.db_engine) as session:
            project_id = None

            if project:
                result = await session.execute(select(Project).where(Project.name == project))
                proj = result.scalars().first()
                if proj:
                    project_id = proj.id
                else:
                    print(f"Warning: Project '{project}' not found", file=sys.stderr)

            doc = AdvisoryDocument(
                title=title,
                content=content,
                source=source,
                source_type=source_type,
                project_id=project_id,
                tags=json.dumps(tags or []),
                priority=priority,
                status="pending_review",
            )

            session.add(doc)
            await session.commit()
            await session.refresh(doc)

            print(f"\nAdvisory document added: #{doc.id} - {title}")

            if auto_analyze:
                print(f"\n{'=' * 80}")
                print("ANALYSIS RESULTS")
                print(f"{'=' * 80}\n")

                analyzer = AdvisoryAnalyzer(self.org_context)
                analysis = await analyzer.analyze_document(doc, session)
                doc.analysis_result = json.dumps(analysis)
                doc.status = "analyzed"
                doc.reviewed_at = datetime.utcnow()
                await session.commit()

                print(f"Overall Assessment: {analysis['overall_assessment'].upper()}")
                print(f"Recommendation: {analysis['recommendation']}\n")

                if analysis["conflicts"]:
                    print("CONFLICTS:")
                    for conflict in analysis["conflicts"]:
                        print(f"   - {conflict}")
                    print()

                if analysis["synergies"]:
                    print("SYNERGIES:")
                    for synergy in analysis["synergies"]:
                        print(f"   - {synergy}")
                    print()

                recs = analysis["extracted_recommendations"]
                if recs:
                    print(f"RECOMMENDATIONS ({len(recs)}):")
                    for i, rec in enumerate(recs[:5], 1):
                        print(f"\n{i}. {rec['text'][:100]}...")
                        print(f"   Category: {rec['category']}")
                    if len(recs) > 5:
                        print(f"\n... and {len(recs) - 5} more recommendations")
                    print()

                print(f"{'=' * 80}\n")
                print(f"View full details: quarterback advisory-view --id {doc.id}")

    async def cmd_advisory_list(
        self, status: str = "all", project: Optional[str] = None, limit: int = 10
    ):
        async with await get_session(self.db_engine) as session:
            query = select(AdvisoryDocument).options(joinedload(AdvisoryDocument.project))

            filters = []
            if status != "all":
                filters.append(AdvisoryDocument.status == status)

            if project:
                result = await session.execute(select(Project).where(Project.name == project))
                proj = result.scalars().first()
                if proj:
                    filters.append(AdvisoryDocument.project_id == proj.id)

            if filters:
                query = query.where(and_(*filters))

            query = query.order_by(AdvisoryDocument.created_at.desc()).limit(limit)
            result = await session.execute(query)
            documents = result.scalars().all()

            if not documents:
                print("No advisory documents found.")
                return

            print(f"\n{'=' * 80}")
            print(f"ADVISORY DOCUMENTS ({len(documents)})")
            print(f"{'=' * 80}\n")

            for doc in documents:
                tags = json.loads(doc.tags) if doc.tags else []
                print(f"#{doc.id}: {doc.title}")
                print(f"   Status: {doc.status}")
                print(f"   Source: {doc.source or 'N/A'} ({doc.source_type})")
                if doc.project:
                    print(f"   Project: {doc.project.name}")
                if tags:
                    print(f"   Tags: {', '.join(tags)}")
                print(f"   Created: {doc.created_at.strftime('%Y-%m-%d %H:%M')}")
                print()

    async def cmd_advisory_view(
        self,
        doc_id: int,
        show_content: bool = False,
        show_analysis: bool = True,
        show_recommendations: bool = True,
    ):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument)
                .options(
                    joinedload(AdvisoryDocument.project),
                    joinedload(AdvisoryDocument.recommendations),
                )
                .where(AdvisoryDocument.id == doc_id)
            )
            doc = result.scalars().first()

            if not doc:
                print(f"Error: Advisory document #{doc_id} not found", file=sys.stderr)
                return

            print(f"\n{'=' * 80}")
            print(f"ADVISORY DOCUMENT #{doc.id}")
            print(f"{'=' * 80}\n")

            print(f"Title: {doc.title}")
            print(f"Source: {doc.source or 'N/A'} ({doc.source_type})")
            print(f"Status: {doc.status}")
            if doc.project:
                print(f"Project: {doc.project.name}")
            print(f"Priority: {doc.priority}/5")
            print(f"Created: {doc.created_at.strftime('%Y-%m-%d %H:%M')}")
            print()

            if show_content:
                print(f"{'=' * 80}")
                print("CONTENT")
                print(f"{'=' * 80}\n")
                print(doc.content[:500] + "..." if len(doc.content) > 500 else doc.content)
                print()

            if show_analysis and doc.analysis_result:
                analysis = json.loads(doc.analysis_result)
                print(f"{'=' * 80}")
                print("ANALYSIS")
                print(f"{'=' * 80}\n")
                print(f"Assessment: {analysis['overall_assessment'].upper()}")
                print(f"Recommendation: {analysis['recommendation']}\n")

                if analysis.get("conflicts"):
                    print("Conflicts:")
                    for c in analysis["conflicts"]:
                        print(f"   - {c}")
                    print()

                if analysis.get("synergies"):
                    print("Synergies:")
                    for s in analysis["synergies"]:
                        print(f"   - {s}")
                    print()

            if show_recommendations and doc.recommendations:
                print(f"{'=' * 80}")
                print(f"RECOMMENDATIONS ({len(doc.recommendations)})")
                print(f"{'=' * 80}\n")

                for i, rec in enumerate(doc.recommendations, 1):
                    print(f"{i}. [{rec.status.upper()}] {rec.recommendation_text[:80]}...")
                    print(f"   ID: {rec.id} | Category: {rec.category}")
                    if rec.estimated_effort_hours:
                        print(
                            f"   Effort: {rec.estimated_effort_hours}h | Impact: {rec.estimated_impact}/5"
                        )
                    print()

    async def cmd_advisory_analyze(self, doc_id: int):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument).where(AdvisoryDocument.id == doc_id)
            )
            doc = result.scalars().first()

            if not doc:
                print(f"Error: Advisory document #{doc_id} not found", file=sys.stderr)
                return

            print(f"\nAnalyzing: {doc.title}")
            print(f"{'=' * 80}\n")

            analyzer = AdvisoryAnalyzer(self.org_context)
            analysis = await analyzer.analyze_document(doc, session)

            doc.analysis_result = json.dumps(analysis)
            doc.status = "analyzed"
            doc.reviewed_at = datetime.utcnow()
            await session.commit()

            print(f"Overall Assessment: {analysis['overall_assessment'].upper()}")
            print(f"Recommendation: {analysis['recommendation']}\n")

            recs = analysis["extracted_recommendations"]
            print(f"EXTRACTED {len(recs)} RECOMMENDATIONS\n")

            print(f"{'=' * 80}")
            print("Analysis complete")

    async def cmd_advisory_approve(
        self,
        doc_id: int,
        approve: Optional[list] = None,
        reject: Optional[list] = None,
        create_tasks: bool = False,
        notes: Optional[str] = None,
    ):
        async with await get_session(self.db_engine) as session:
            result = await session.execute(
                select(AdvisoryDocument)
                .options(joinedload(AdvisoryDocument.recommendations))
                .where(AdvisoryDocument.id == doc_id)
            )
            doc = result.scalars().first()

            if not doc:
                print(f"Error: Advisory document #{doc_id} not found", file=sys.stderr)
                return

            approved_ids = approve or []
            rejected_ids = reject or []

            if not approved_ids and not rejected_ids:
                print(
                    "Error: Must specify --approve or --reject recommendation IDs", file=sys.stderr
                )
                return

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
                            notes=f"From advisory document: {doc.title}",
                        )
                        session.add(task)
                        await session.flush()
                        rec.implemented_as_task_id = task.id
                        created_tasks.append(task)

                elif rec.id in rejected_ids:
                    rec.status = "rejected"
                    rec.decided_at = datetime.utcnow()

            total_recs = len(doc.recommendations)
            approved_count = len([r for r in doc.recommendations if r.status == "approved"])
            rejected_count = len([r for r in doc.recommendations if r.status == "rejected"])

            if approved_count == total_recs:
                doc.status = "approved"
            elif rejected_count == total_recs:
                doc.status = "rejected"
            elif approved_count > 0 or rejected_count > 0:
                doc.status = "partially_adopted"

            doc.adopted_at = datetime.utcnow()
            doc.adoption_notes = notes

            await session.commit()

            print(f"\nUpdated {len(approved_ids) + len(rejected_ids)} recommendations")
            print(f"  Approved: {len(approved_ids)}")
            print(f"  Rejected: {len(rejected_ids)}")
            print(f"  Document status: {doc.status}")

            if created_tasks:
                print(f"\nCreated {len(created_tasks)} task(s):")
                for task in created_tasks:
                    print(f"   - Task #{task.id}: {task.description[:60]}...")

    async def cmd_advisory_import(
        self,
        url: Optional[str] = None,
        file_path: Optional[str] = None,
        title: Optional[str] = None,
        source: Optional[str] = None,
        project: Optional[str] = None,
        priority: int = 3,
    ):
        if url:
            await self.cmd_advisory_add(
                title=title or "Untitled",
                url=url,
                source=source,
                source_type="article",
                project=project,
                priority=priority,
            )
        elif file_path:
            await self.cmd_advisory_add(
                title=title or Path(file_path).stem,
                file_path=file_path,
                source=source or file_path,
                source_type="other",
                project=project,
                priority=priority,
            )
        else:
            print("Reading content from stdin (Ctrl+D when done)...")
            content = sys.stdin.read()
            if content:
                await self.cmd_advisory_add(
                    title=title or "Imported Content",
                    content=content,
                    source=source or "stdin",
                    source_type="other",
                    project=project,
                    priority=priority,
                )
            else:
                print("Error: No content provided", file=sys.stderr)


def _fetch_url_content(url: str) -> tuple:
    """Fetch and parse content from URL. Returns (content, title)."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        raise Exception(
            "requests and beautifulsoup4 required for URL fetching. "
            "Install with: pip install quarterback[import]"
        )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")

    title = "Untitled"
    if soup.title:
        title = soup.title.string.strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text().strip()

    content = ""

    article_selectors = [
        "article",
        "main",
        ".post-content",
        ".article-content",
        ".entry-content",
        '[role="main"]',
        ".content",
    ]

    for selector in article_selectors:
        article = soup.select_one(selector)
        if article:
            paragraphs = article.find_all(["p", "h1", "h2", "h3", "h4", "li"])
            content = "\n\n".join(
                [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
            )
            if content:
                break

    if not content:
        paragraphs = soup.find_all("p")
        content = "\n\n".join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])

    if not content:
        content = soup.get_text()

    content = "\n".join([line.strip() for line in content.split("\n") if line.strip()])

    return content, title


def cmd_init():
    """Initialize a new Quarterback installation."""
    print("Initializing Quarterback...")

    # Create directory structure
    for d in [DATA_DIR, ORG_CONTEXT_DIR, CONFIG_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  Created {d}")

    # Copy example org-context files from package
    pkg_dir = Path(__file__).parent.parent.parent
    example_src = pkg_dir / "org-context"
    if example_src.exists():
        for f in example_src.glob("*.example.*"):
            dest = ORG_CONTEXT_DIR / f.name
            if not dest.exists():
                shutil.copy2(f, dest)
                print(f"  Copied {f.name}")

    readme_src = example_src / "README.md" if example_src.exists() else None
    if readme_src and readme_src.exists():
        dest = ORG_CONTEXT_DIR / "README.md"
        if not dest.exists():
            shutil.copy2(readme_src, dest)

    # Copy example alert config
    alert_example_src = pkg_dir / "config" / "alerts.example.yaml"
    if alert_example_src.exists():
        dest = CONFIG_DIR / "alerts.example.yaml"
        if not dest.exists():
            shutil.copy2(alert_example_src, dest)
            print("  Copied alerts.example.yaml")

    # Initialize empty database
    async def _init_db():
        from quarterback.database import init_db

        await init_db()

    asyncio.run(_init_db())
    print(f"  Created database at {DB_PATH}")

    print("\nYou're set up! Run `quarterback priorities` to get started.")
    print(f"Configure your org context in {ORG_CONTEXT_DIR}/")


def cmd_setup():
    """Interactive setup wizard for Quarterback."""
    import asyncio
    from quarterback.setup_wizard import apply_setup, get_setup_status

    print("\n  Quarterback Setup Wizard")
    print("  ========================\n")

    status = get_setup_status()
    if not status["quarterback_initialized"]:
        print("  Initializing Quarterback first...")
        cmd_init()
        print()

    overwrite = False
    has_existing = any(
        status[k]
        for k in [
            "goals_configured",
            "workflows_configured",
            "projects_configured",
            "constraints_configured",
        ]
    )
    if has_existing:
        resp = input("  Existing config found. Overwrite? (originals backed up) [y/N]: ").strip()
        if resp.lower() != "y":
            print("  Setup cancelled. Existing config preserved.")
            return
        overwrite = True

    print("  1. ORGANIZATION\n")
    org_name = input("  What is your business or project called? > ").strip()
    mission = input("  Describe what you do in one sentence: > ").strip()
    vision = input("  Where do you want to be in 2-3 years? (Enter to skip): > ").strip()

    print("\n  2. GOALS\n")
    print("  What are your top goals for this year? (one per line, blank to finish):")
    annual = []
    while True:
        g = input("  > ").strip()
        if not g:
            break
        annual.append(g)

    print("  What are you focused on this quarter? (one per line, blank to finish):")
    quarterly = []
    while True:
        g = input("  > ").strip()
        if not g:
            break
        quarterly.append(g)

    print("  Anything you do NOT want to work on? (one per line, blank to finish):")
    anti_goals = []
    while True:
        g = input("  > ").strip()
        if not g:
            break
        anti_goals.append(g)

    print("\n  3. WORKFLOWS & PROJECTS\n")
    print("  Add your work themes/workflows (blank name to finish):")
    workflows = []
    while True:
        name = input("  Workflow name: > ").strip()
        if not name:
            break
        desc = input(f"  Description for '{name}': > ").strip()
        workflows.append(
            {
                "name": name,
                "description": desc,
                "goals": [],
                "priority": len(workflows) + 1,
                "status": "active",
            }
        )

    print("\n  Add your projects (blank name to finish):")
    projects = []
    wf_names = [w["name"] for w in workflows]
    while True:
        name = input("  Project name: > ").strip()
        if not name:
            break
        path = input(f"  Path for '{name}' (e.g. ~/projects/foo): > ").strip()
        workflow = ""
        if wf_names:
            print(f"  Workflows: {', '.join(wf_names)}")
            workflow = input(f"  Workflow for '{name}': > ").strip()
        priority = input(f"  Priority 1-5 for '{name}' [3]: > ").strip()
        projects.append(
            {
                "name": name,
                "path": path,
                "workflow": workflow,
                "status": "active",
                "priority": int(priority) if priority.isdigit() else 3,
            }
        )

    print("\n  4. CONSTRAINTS\n")
    hours = input("  Hours per week available [40]: > ").strip()
    working_hours = input("  Working hours (e.g. 9am-6pm) [9am-6pm]: > ").strip()
    team_size = input("  Team size [1]: > ").strip()
    budget = input("  Monthly budget for tools/infra (Enter to skip): > ").strip()
    stack = input("  Preferred tech stack (comma-separated, Enter to skip): > ").strip()

    answers = {
        "organization": {
            "name": org_name or "My Organization",
            "mission": mission,
            "vision": vision,
        },
        "goals": {"annual": annual, "quarterly": quarterly, "anti_goals": anti_goals},
        "workflows": workflows,
        "projects": projects,
        "constraints": {
            "hours_per_week": int(hours) if hours.isdigit() else 40,
            "working_hours": working_hours or "9am-6pm",
            "working_days": "Monday-Friday",
            "team_size": int(team_size) if team_size.isdigit() else 1,
            "budget_monthly": float(budget) if budget else None,
            "preferred_stack": [s.strip() for s in stack.split(",") if s.strip()] if stack else [],
        },
    }

    print("\n  Writing configuration...")
    result = asyncio.run(apply_setup(answers, overwrite=overwrite))

    if result.get("success"):
        print("  Done! Quarterback is configured.\n")
        print("  Next steps:")
        for step in result.get("next_steps", []):
            print(f"    - {step}")
        print()
    else:
        print(f"  Error: {result.get('message', 'Unknown error')}")


def cmd_migrate(source_dir: str):
    """Migrate from an existing task-manager installation."""
    source = Path(source_dir).expanduser()

    if not source.exists():
        print(f"Error: Source directory '{source}' not found", file=sys.stderr)
        sys.exit(1)

    source_db = source / "data" / "tasks.db"
    if not source_db.exists():
        print(f"Error: No database found at {source_db}", file=sys.stderr)
        sys.exit(1)

    # Run init first if needed
    if not QUARTERBACK_HOME.exists():
        print("Running init first...")
        cmd_init()
        print()

    print(f"Migrating from {source}...")

    # Copy database
    dest_db = DB_PATH
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, dest_db)
    print(f"  Copied database -> {dest_db}")

    # Copy org-context files (skip .example files)
    source_org = source / "org-context"
    if source_org.exists():
        for f in source_org.iterdir():
            if f.is_file() and ".example" not in f.name:
                dest = ORG_CONTEXT_DIR / f.name
                shutil.copy2(f, dest)
                print(f"  Copied org-context/{f.name}")

    # Copy alerts config
    source_alerts = source / "config" / "alerts.yaml"
    if source_alerts.exists():
        dest = CONFIG_DIR / "alerts.yaml"
        shutil.copy2(source_alerts, dest)
        print("  Copied config/alerts.yaml")

    # Verify integrity
    source_conn = sqlite3.connect(str(source_db))
    dest_conn = sqlite3.connect(str(dest_db))

    try:
        src_tasks = source_conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
        dst_tasks = dest_conn.execute("SELECT count(*) FROM tasks").fetchone()[0]

        src_projects = source_conn.execute("SELECT count(*) FROM projects").fetchone()[0]
        dst_projects = dest_conn.execute("SELECT count(*) FROM projects").fetchone()[0]

        dst_docs = 0
        try:
            dst_docs = dest_conn.execute("SELECT count(*) FROM advisory_documents").fetchone()[0]
        except sqlite3.OperationalError:
            pass  # Table may not exist in older installs

        assert src_tasks == dst_tasks, f"Task count mismatch: {src_tasks} vs {dst_tasks}"
        assert src_projects == dst_projects, "Project count mismatch"

        print(
            f"\nMigrated {dst_tasks} tasks, {dst_projects} projects, {dst_docs} advisory documents."
        )
        print(f"Source unchanged at {source}.")

    finally:
        source_conn.close()
        dest_conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Quarterback - Strategic task prioritization for multi-project operators"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Init command
    subparsers.add_parser("init", help="Initialize Quarterback")

    # Setup wizard command
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Migrate from task-manager")
    migrate_parser.add_argument("source_dir", help="Source directory (e.g., ~/.task-manager)")

    # Priorities command
    priorities_parser = subparsers.add_parser("priorities", help="Show prioritized tasks")
    priorities_parser.add_argument(
        "timeframe",
        nargs="?",
        default="today",
        choices=["today", "week", "all"],
        help="Timeframe to show",
    )
    priorities_parser.add_argument("-p", "--project", help="Filter by project name")
    priorities_parser.add_argument("-l", "--limit", type=int, default=10, help="Max tasks to show")

    # Add task command
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("description", help="Task description")
    add_parser.add_argument("-p", "--project", help="Project name")
    add_parser.add_argument(
        "--priority", type=int, default=3, choices=[1, 2, 3, 4, 5], help="Priority (1-5)"
    )
    add_parser.add_argument("--effort", type=float, help="Estimated effort in hours")
    add_parser.add_argument(
        "--impact", type=int, default=3, choices=[1, 2, 3, 4, 5], help="Impact (1-5)"
    )
    add_parser.add_argument("--due", help="Due date (YYYY-MM-DD)")
    add_parser.add_argument("--notes", help="Additional notes")

    # Update task command
    update_parser = subparsers.add_parser("update", help="Update a task")
    update_parser.add_argument("task_id", type=int, help="Task ID")
    update_parser.add_argument(
        "-s",
        "--status",
        choices=["pending", "in_progress", "completed", "blocked"],
        help="New status",
    )
    update_parser.add_argument("--priority", type=int, choices=[1, 2, 3, 4, 5], help="New priority")
    update_parser.add_argument("--effort", type=float, help="New effort estimate")
    update_parser.add_argument("--impact", type=int, choices=[1, 2, 3, 4, 5], help="New impact")
    update_parser.add_argument("--notes", help="New notes")

    # List tasks command
    list_parser = subparsers.add_parser("list", help="List all tasks")
    list_parser.add_argument(
        "-s",
        "--status",
        choices=["pending", "in_progress", "completed", "blocked"],
        help="Filter by status",
    )
    list_parser.add_argument("-p", "--project", help="Filter by project")

    # Quick wins command
    quickwins_parser = subparsers.add_parser("quick-wins", help="Find quick win tasks")
    quickwins_parser.add_argument("-p", "--project", help="Filter by project")
    quickwins_parser.add_argument("-l", "--limit", type=int, default=5, help="Max tasks to show")

    # Conflicts command
    subparsers.add_parser("conflicts", help="Detect priority conflicts")

    # Projects command
    projects_parser = subparsers.add_parser("projects", help="List projects")
    projects_parser.add_argument(
        "-s",
        "--status",
        default="active",
        choices=["active", "paused", "completed", "archived", "all"],
        help="Filter by status",
    )

    # Summary command
    subparsers.add_parser("summary", help="Show organizational summary")

    # Alert commands
    subparsers.add_parser("alert-check", help="Check and send task alerts")
    subparsers.add_parser("alert-summary", help="Send daily summary notification")
    subparsers.add_parser("alert-test", help="Send a test notification")
    subparsers.add_parser("alert-config", help="Show alert configuration")

    # Project context commands
    project_info_parser = subparsers.add_parser(
        "project-info", help="Show detailed project information"
    )
    project_info_parser.add_argument("project", help="Project name")

    project_context_parser = subparsers.add_parser(
        "project-context", help="View or manage project context"
    )
    project_context_parser.add_argument("project", help="Project name")

    # Daily planning command
    subparsers.add_parser("plan-day", help="Show time-aware daily plan with task recommendations")
    project_context_parser.add_argument("--add", metavar="TEXT", help="Add context to project")
    project_context_parser.add_argument("--replace", metavar="TEXT", help="Replace project context")
    project_context_parser.add_argument(
        "--clear", action="store_true", help="Clear project context"
    )

    # Advisory document commands
    advisory_add_parser = subparsers.add_parser("advisory-add", help="Add advisory document")
    advisory_add_parser.add_argument("--title", required=True, help="Document title")
    advisory_add_parser.add_argument("--content", help="Document content (direct text)")
    advisory_add_parser.add_argument("--file", help="Read content from file path")
    advisory_add_parser.add_argument("--url", help="Fetch content from URL")
    advisory_add_parser.add_argument("--source", help="Source attribution")
    advisory_add_parser.add_argument(
        "--source-type",
        default="other",
        choices=["article", "book", "expert_advice", "video", "podcast", "other"],
        help="Type of source",
    )
    advisory_add_parser.add_argument("--project", help="Associate with project")
    advisory_add_parser.add_argument(
        "--priority", type=int, default=3, choices=[1, 2, 3, 4, 5], help="Priority (1-5)"
    )
    advisory_add_parser.add_argument(
        "--no-analyze", action="store_true", help="Skip automatic analysis"
    )

    advisory_list_parser = subparsers.add_parser("advisory-list", help="List advisory documents")
    advisory_list_parser.add_argument(
        "--status",
        default="all",
        choices=["all", "pending_review", "analyzed", "approved", "rejected", "partially_adopted"],
        help="Filter by status",
    )
    advisory_list_parser.add_argument("--project", help="Filter by project")
    advisory_list_parser.add_argument("--limit", type=int, default=10, help="Max documents to show")

    advisory_view_parser = subparsers.add_parser(
        "advisory-view", help="View advisory document details"
    )
    advisory_view_parser.add_argument("--id", type=int, required=True, help="Document ID")
    advisory_view_parser.add_argument(
        "--show-content", action="store_true", help="Show full content"
    )
    advisory_view_parser.add_argument("--no-analysis", action="store_true", help="Hide analysis")
    advisory_view_parser.add_argument(
        "--no-recommendations", action="store_true", help="Hide recommendations"
    )

    advisory_analyze_parser = subparsers.add_parser(
        "advisory-analyze", help="Analyze advisory document"
    )
    advisory_analyze_parser.add_argument(
        "--id", type=int, required=True, help="Document ID to analyze"
    )

    advisory_approve_parser = subparsers.add_parser(
        "advisory-approve", help="Approve/reject recommendations"
    )
    advisory_approve_parser.add_argument("--id", type=int, required=True, help="Document ID")
    advisory_approve_parser.add_argument(
        "--approve", help="Comma-separated recommendation IDs to approve"
    )
    advisory_approve_parser.add_argument(
        "--reject", help="Comma-separated recommendation IDs to reject"
    )
    advisory_approve_parser.add_argument(
        "--create-tasks", action="store_true", help="Create tasks for approved recommendations"
    )
    advisory_approve_parser.add_argument("--notes", help="Adoption notes")

    advisory_import_parser = subparsers.add_parser(
        "advisory-import", help="Smart import advisory document"
    )
    advisory_import_parser.add_argument("--url", help="Fetch from URL")
    advisory_import_parser.add_argument("--file", help="Read from file")
    advisory_import_parser.add_argument("--title", help="Document title")
    advisory_import_parser.add_argument("--source", help="Source attribution")
    advisory_import_parser.add_argument("--project", help="Associate with project")
    advisory_import_parser.add_argument(
        "--priority", type=int, default=3, choices=[1, 2, 3, 4, 5], help="Priority (1-5)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle sync commands
    if args.command == "init":
        cmd_init()
        return

    if args.command == "migrate":
        cmd_migrate(args.source_dir)
        return

    if args.command == "setup":
        cmd_setup()
        return

    # Handle async commands
    cli = QuarterbackCLI()

    async def run():
        await cli.initialize()

        if args.command == "priorities":
            await cli.cmd_priorities(args.timeframe, args.project, args.limit)
        elif args.command == "add":
            await cli.cmd_add_task(
                args.description,
                args.project,
                args.priority,
                args.effort,
                args.impact,
                args.due,
                args.notes,
            )
        elif args.command == "update":
            await cli.cmd_update_task(
                args.task_id, args.status, args.priority, args.effort, args.impact, args.notes
            )
        elif args.command == "list":
            await cli.cmd_list_tasks(args.status, args.project)
        elif args.command == "quick-wins":
            await cli.cmd_quick_wins(args.project, args.limit)
        elif args.command == "conflicts":
            await cli.cmd_conflicts()
        elif args.command == "projects":
            await cli.cmd_projects(args.status)
        elif args.command == "summary":
            await cli.cmd_summary()
        elif args.command == "alert-check":
            await cli.cmd_alert_check()
        elif args.command == "alert-summary":
            await cli.cmd_alert_summary()
        elif args.command == "alert-test":
            await cli.cmd_alert_test()
        elif args.command == "alert-config":
            await cli.cmd_alert_config()
        elif args.command == "project-info":
            await cli.cmd_project_info(args.project)
        elif args.command == "plan-day":
            await cli.cmd_plan_day()
        elif args.command == "project-context":
            if args.add:
                await cli.cmd_project_context(args.project, args.add, "add")
            elif args.replace:
                await cli.cmd_project_context(args.project, args.replace, "replace")
            elif args.clear:
                await cli.cmd_project_context(args.project, action="clear")
            else:
                await cli.cmd_project_context(args.project, action="view")
        elif args.command == "advisory-add":
            await cli.cmd_advisory_add(
                title=args.title,
                content=args.content,
                file_path=args.file,
                url=args.url,
                source=args.source,
                source_type=args.source_type,
                project=args.project,
                priority=args.priority,
                auto_analyze=not args.no_analyze,
            )
        elif args.command == "advisory-list":
            await cli.cmd_advisory_list(status=args.status, project=args.project, limit=args.limit)
        elif args.command == "advisory-view":
            await cli.cmd_advisory_view(
                doc_id=args.id,
                show_content=args.show_content,
                show_analysis=not args.no_analysis,
                show_recommendations=not args.no_recommendations,
            )
        elif args.command == "advisory-analyze":
            await cli.cmd_advisory_analyze(doc_id=args.id)
        elif args.command == "advisory-approve":
            approve_ids = [int(x.strip()) for x in args.approve.split(",")] if args.approve else []
            reject_ids = [int(x.strip()) for x in args.reject.split(",")] if args.reject else []
            await cli.cmd_advisory_approve(
                doc_id=args.id,
                approve=approve_ids,
                reject=reject_ids,
                create_tasks=args.create_tasks,
                notes=args.notes,
            )
        elif args.command == "advisory-import":
            await cli.cmd_advisory_import(
                url=args.url,
                file_path=args.file,
                title=args.title,
                source=args.source,
                project=args.project,
                priority=args.priority,
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
