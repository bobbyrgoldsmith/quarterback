"""
Notification system for Quarterback alerts.
Supports macOS, Linux, and console fallback.
"""

import subprocess
import sys
from typing import List, Dict, Any, Optional
from enum import Enum


class NotificationType(Enum):
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    UPCOMING = "upcoming"
    DAILY_SUMMARY = "daily_summary"
    TIME_SENSITIVE = "time_sensitive"


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationHandler:
    """Handle notifications across different platforms."""

    def __init__(self):
        self.platform = sys.platform

    def send(
        self,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.DAILY_SUMMARY,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        subtitle: Optional[str] = None,
    ) -> bool:
        if self.platform == "darwin":
            return self._send_macos(title, message, subtitle, priority)
        elif self.platform.startswith("linux"):
            return self._send_linux(title, message, subtitle)
        else:
            return self._send_console(title, message, subtitle)

    def _send_macos(
        self,
        title: str,
        message: str,
        subtitle: Optional[str],
        priority: NotificationPriority,
    ) -> bool:
        try:
            script_parts = [
                "display notification",
                f'"{message}"',
                f'with title "{title}"',
            ]

            if subtitle:
                script_parts.append(f'subtitle "{subtitle}"')

            sound = self._get_sound_for_priority(priority)
            if sound:
                script_parts.append(f'sound name "{sound}"')

            script = " ".join(script_parts)

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )

            return result.returncode == 0

        except Exception as e:
            print(f"Error sending macOS notification: {e}", file=sys.stderr)
            return False

    def _send_linux(self, title: str, message: str, subtitle: Optional[str]) -> bool:
        try:
            body = f"{subtitle}\n{message}" if subtitle else message
            result = subprocess.run(
                ["notify-send", title, body],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return self._send_console(title, message, subtitle)
        except Exception:
            return self._send_console(title, message, subtitle)

    def _send_console(self, title: str, message: str, subtitle: Optional[str]) -> bool:
        print("\n" + "=" * 80)
        print(f"NOTIFICATION: {title}")
        if subtitle:
            print(f"   {subtitle}")
        print(f"   {message}")
        print("=" * 80 + "\n")
        return True

    def _get_sound_for_priority(self, priority: NotificationPriority) -> Optional[str]:
        sound_map = {
            NotificationPriority.LOW: None,
            NotificationPriority.MEDIUM: "Ping",
            NotificationPriority.HIGH: "Purr",
            NotificationPriority.CRITICAL: "Basso",
        }
        return sound_map.get(priority)


class TaskNotifier:
    """High-level interface for task-related notifications."""

    def __init__(self):
        self.handler = NotificationHandler()

    def notify_overdue_task(self, task: Dict[str, Any]) -> bool:
        from datetime import datetime

        project = task.get("project", "No project")
        title = "Task Overdue"
        subtitle = project

        due_date = task.get("due_date")
        due_str = ""
        if due_date:
            if isinstance(due_date, datetime):
                due_str = f" (was due {due_date.strftime('%b %d')})"
            elif isinstance(due_date, str):
                due_str = f" (was due {due_date})"

        message = f"{task['description'][:100]}{due_str}"

        return self.handler.send(
            title=title,
            message=message,
            subtitle=subtitle,
            notification_type=NotificationType.OVERDUE,
            priority=NotificationPriority.HIGH,
        )

    def notify_due_today(self, task: Dict[str, Any]) -> bool:
        project = task.get("project", "No project")
        title = "Task Due Today"
        subtitle = project
        message = f"{task['description'][:100]}"

        effort = task.get("effort")
        if effort:
            message += f" ({effort}h estimated)"

        return self.handler.send(
            title=title,
            message=message,
            subtitle=subtitle,
            notification_type=NotificationType.DUE_TODAY,
            priority=NotificationPriority.HIGH,
        )

    def notify_upcoming_task(self, task: Dict[str, Any], days_until: int) -> bool:
        project = task.get("project", "No project")
        title = f"Task Due in {days_until} day{'s' if days_until != 1 else ''}"
        subtitle = project
        message = f"{task['description'][:100]}"

        return self.handler.send(
            title=title,
            message=message,
            subtitle=subtitle,
            notification_type=NotificationType.UPCOMING,
            priority=NotificationPriority.MEDIUM,
        )

    def notify_time_sensitive(self, task: Dict[str, Any]) -> bool:
        project = task.get("project", "No project")
        title = "Time-Sensitive Action Required"
        subtitle = project
        message = f"{task['description'][:100]}"

        return self.handler.send(
            title=title,
            message=message,
            subtitle=subtitle,
            notification_type=NotificationType.TIME_SENSITIVE,
            priority=NotificationPriority.CRITICAL,
        )

    def notify_daily_summary(
        self,
        overdue_count: int,
        due_today_count: int,
        upcoming_count: int,
        top_priorities: List[str],
    ) -> bool:
        title = "Daily Task Summary"

        summary_parts = []
        if overdue_count > 0:
            summary_parts.append(f"{overdue_count} overdue")
        if due_today_count > 0:
            summary_parts.append(f"{due_today_count} due today")
        if upcoming_count > 0:
            summary_parts.append(f"{upcoming_count} upcoming")

        if not summary_parts:
            message = "No urgent tasks today."
        else:
            message = ", ".join(summary_parts)

            if top_priorities:
                message += f"\n\nTop priority: {top_priorities[0][:60]}"

        return self.handler.send(
            title=title,
            message=message,
            notification_type=NotificationType.DAILY_SUMMARY,
            priority=NotificationPriority.MEDIUM,
        )

    def notify_quick_summary(
        self, message: str, priority: NotificationPriority = NotificationPriority.MEDIUM
    ) -> bool:
        return self.handler.send(
            title="Quarterback",
            message=message,
            notification_type=NotificationType.DAILY_SUMMARY,
            priority=priority,
        )


def send_notification(title: str, message: str, subtitle: Optional[str] = None) -> bool:
    handler = NotificationHandler()
    return handler.send(title, message, subtitle=subtitle)
