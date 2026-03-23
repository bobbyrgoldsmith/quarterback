#!/usr/bin/env python3
"""
Alert Daemon for Quarterback.
Monitors tasks and sends notifications based on configured rules.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
import logging

from quarterback.config import ALERTS_CONFIG_PATH, ORG_CONTEXT_DIR, LOG_DIR
from quarterback.database import init_db, get_session, Task
from quarterback.notifications import TaskNotifier, NotificationPriority
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload


class AlertConfig:
    """Configuration for the alert system."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = ALERTS_CONFIG_PATH

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return self._get_default_config()

        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}, using defaults", file=sys.stderr)
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "quiet_hours": {"enabled": True, "start": "22:00", "end": "08:00"},
            "active_days": [0, 1, 2, 3, 4, 5, 6],
            "thresholds": {
                "min_priority": 4,
                "upcoming_days": 3,
                "notify_overdue": True,
                "notify_due_today": True,
                "notify_upcoming": True,
            },
            "time_sensitive_projects": [],
            "notifications": {
                "sound_enabled": True,
                "show_project": True,
                "show_effort": True,
            },
            "filters": {
                "excluded_projects": [],
                "excluded_statuses": ["completed", "blocked"],
            },
        }

    def is_enabled(self) -> bool:
        return self.config.get("enabled", True)

    def is_quiet_hours(self) -> bool:
        quiet = self.config.get("quiet_hours", {})
        if not quiet.get("enabled", False):
            return False

        now = datetime.now().time()
        start_str = quiet.get("start", "22:00")
        end_str = quiet.get("end", "08:00")

        try:
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            if start_time > end_time:
                return now >= start_time or now <= end_time
            else:
                return start_time <= now <= end_time

        except Exception:
            return False

    def is_active_day(self) -> bool:
        today = datetime.now().weekday()
        active_days = self.config.get("active_days", [0, 1, 2, 3, 4, 5, 6])
        return today in active_days

    def get_time_sensitive_projects(self) -> List[str]:
        return self.config.get("time_sensitive_projects", [])

    def get_min_priority(self) -> int:
        return self.config.get("thresholds", {}).get("min_priority", 4)

    def get_upcoming_days(self) -> int:
        return self.config.get("thresholds", {}).get("upcoming_days", 3)

    def should_notify_overdue(self) -> bool:
        return self.config.get("thresholds", {}).get("notify_overdue", True)

    def should_notify_due_today(self) -> bool:
        return self.config.get("thresholds", {}).get("notify_due_today", True)

    def should_notify_upcoming(self) -> bool:
        return self.config.get("thresholds", {}).get("notify_upcoming", True)

    def get_excluded_statuses(self) -> List[str]:
        return self.config.get("filters", {}).get("excluded_statuses", ["completed", "blocked"])


class AlertDaemon:
    """Daemon that monitors tasks and sends alerts."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = AlertConfig(config_path)
        self.notifier = TaskNotifier()
        self.db_engine = None
        self.logger = self._setup_logging()
        self.org_context = {}

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("AlertDaemon")
        logger.setLevel(logging.INFO)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_config = self.config.config.get("logging", {})
        if log_config.get("enabled", False):
            log_file_str = log_config.get("log_file", str(LOG_DIR / "alerts.log"))
            log_file = Path(log_file_str).expanduser()
            log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, log_config.get("level", "INFO")))
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        return logger

    async def initialize(self):
        self.logger.info("Initializing Alert Daemon...")
        self.db_engine = await init_db()
        await self._load_org_context()
        self.logger.info("Alert Daemon initialized successfully")

    async def _load_org_context(self):
        context_dir = ORG_CONTEXT_DIR
        try:
            goals_path = context_dir / "goals.md"
            if goals_path.exists():
                self.org_context["goals_content"] = goals_path.read_text()

            workflows_path = context_dir / "workflows.yaml"
            if workflows_path.exists():
                self.org_context["workflows"] = yaml.safe_load(workflows_path.read_text())

            constraints_path = context_dir / "constraints.md"
            if constraints_path.exists():
                self.org_context["constraints_content"] = constraints_path.read_text()
        except Exception as e:
            self.logger.warning(f"Error loading org context: {e}")

    async def check_alerts(self) -> Dict[str, int]:
        if not self.config.is_enabled():
            self.logger.debug("Alerts are disabled")
            return {"disabled": 1}

        if not self.config.is_active_day():
            self.logger.debug("Today is not an active day")
            return {"inactive_day": 1}

        if self.config.is_quiet_hours():
            self.logger.debug("Currently in quiet hours")
            return {"quiet_hours": 1}

        self.logger.info("Checking for alerts...")

        counts = {
            "overdue": 0,
            "due_today": 0,
            "upcoming": 0,
            "time_sensitive": 0,
        }

        async with await get_session(self.db_engine) as session:
            excluded_statuses = self.config.get_excluded_statuses()
            query = (
                select(Task)
                .options(joinedload(Task.project))
                .where(
                    and_(
                        Task.status.notin_(excluded_statuses),
                        Task.due_date.isnot(None),
                    )
                )
            )

            result = await session.execute(query)
            tasks = result.scalars().all()

            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            today_end = today_start + timedelta(days=1)
            upcoming_end = today_start + timedelta(days=self.config.get_upcoming_days())

            time_sensitive_projects = self.config.get_time_sensitive_projects()
            min_priority = self.config.get_min_priority()

            for task in tasks:
                task_dict = {
                    "id": task.id,
                    "description": task.description,
                    "due_date": task.due_date,
                    "priority": task.priority or 3,
                    "effort": task.effort,
                    "project": task.project.name if task.project else "No project",
                }

                project_name = task.project.name if task.project else None
                is_time_sensitive = project_name in time_sensitive_projects

                if not is_time_sensitive and task.priority < min_priority:
                    continue

                if self.config.should_notify_overdue() and task.due_date < now:
                    if self.notifier.notify_overdue_task(task_dict):
                        counts["overdue"] += 1
                        self.logger.info(
                            f"Sent overdue alert for task {task.id}: {task.description[:50]}"
                        )

                        if is_time_sensitive:
                            counts["time_sensitive"] += 1

                elif (
                    self.config.should_notify_due_today()
                    and today_start <= task.due_date < today_end
                ):
                    if self.notifier.notify_due_today(task_dict):
                        counts["due_today"] += 1
                        self.logger.info(
                            f"Sent due-today alert for task {task.id}: {task.description[:50]}"
                        )

                elif (
                    self.config.should_notify_upcoming()
                    and today_end <= task.due_date < upcoming_end
                ):
                    days_until = (task.due_date - now).days + 1
                    if self.notifier.notify_upcoming_task(task_dict, days_until):
                        counts["upcoming"] += 1
                        self.logger.info(
                            f"Sent upcoming alert for task {task.id}: {task.description[:50]}"
                        )

        total = sum(counts.values())
        self.logger.info(f"Alert check complete: {total} notifications sent")
        return counts

    async def send_daily_summary(self) -> bool:
        if not self.config.is_enabled():
            return False

        self.logger.info("Generating daily summary...")

        async with await get_session(self.db_engine) as session:
            excluded_statuses = self.config.get_excluded_statuses()
            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            today_end = today_start + timedelta(days=1)
            upcoming_end = today_start + timedelta(days=7)

            overdue_result = await session.execute(
                select(Task).where(
                    and_(
                        Task.status.notin_(excluded_statuses),
                        Task.due_date.isnot(None),
                        Task.due_date < now,
                    )
                )
            )
            overdue_count = len(overdue_result.scalars().all())

            due_today_result = await session.execute(
                select(Task).where(
                    and_(
                        Task.status.notin_(excluded_statuses),
                        Task.due_date.isnot(None),
                        Task.due_date >= today_start,
                        Task.due_date < today_end,
                    )
                )
            )
            due_today_count = len(due_today_result.scalars().all())

            upcoming_result = await session.execute(
                select(Task).where(
                    and_(
                        Task.status.notin_(excluded_statuses),
                        Task.due_date.isnot(None),
                        Task.due_date >= today_end,
                        Task.due_date < upcoming_end,
                    )
                )
            )
            upcoming_count = len(upcoming_result.scalars().all())

            priorities_result = await session.execute(
                select(Task)
                .options(joinedload(Task.project))
                .where(Task.status.in_(["pending", "in_progress"]))
                .order_by(Task.priority.desc())
                .limit(3)
            )
            top_tasks = priorities_result.scalars().all()
            top_priorities = [task.description for task in top_tasks]

            success = self.notifier.notify_daily_summary(
                overdue_count=overdue_count,
                due_today_count=due_today_count,
                upcoming_count=upcoming_count,
                top_priorities=top_priorities,
            )

            if success:
                self.logger.info(
                    f"Sent daily summary: {overdue_count} overdue, {due_today_count} due today, {upcoming_count} upcoming"
                )

            return success


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Quarterback Alert Daemon")
    parser.add_argument(
        "--mode",
        choices=["check", "summary", "test"],
        default="check",
        help="Operation mode",
    )
    parser.add_argument("--config", help="Path to alerts config file")

    args = parser.parse_args()

    daemon = AlertDaemon(args.config)
    await daemon.initialize()

    if args.mode == "check":
        counts = await daemon.check_alerts()
        print(f"Alert check complete: {counts}")

    elif args.mode == "summary":
        success = await daemon.send_daily_summary()
        if success:
            print("Daily summary sent")
        else:
            print("Failed to send daily summary")

    elif args.mode == "test":
        print("Sending test notification...")
        success = daemon.notifier.notify_quick_summary(
            "This is a test notification from Quarterback!", NotificationPriority.MEDIUM
        )
        if success:
            print("Test notification sent")
        else:
            print("Failed to send test notification")


if __name__ == "__main__":
    asyncio.run(main())
