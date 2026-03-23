"""
Time-aware task planning that considers working hours and current time.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import yaml

from quarterback.config import ALERTS_CONFIG_PATH


class TimeAwarePlanner:
    """Calculate available working time and filter tasks accordingly."""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = ALERTS_CONFIG_PATH

        self.config = self._load_config(config_path)
        self.working_hours = self.config.get("working_hours", {})

    def _load_config(self, config_path: Path) -> Dict:
        if not config_path.exists():
            return {}

        with open(config_path) as f:
            return yaml.safe_load(f) or {}

    def get_available_hours_today(self, current_time: Optional[datetime] = None) -> Dict:
        if current_time is None:
            current_time = datetime.now()

        planning_config = self.working_hours.get("planning", {})
        if not planning_config.get("time_aware", True):
            return {
                "available_hours": 8.0,
                "is_working_day": True,
                "is_working_hours": True,
                "suggested_timeframe": "today",
                "reason": "Time-aware planning disabled, using default 8-hour day",
            }

        working_days = self.working_hours.get("working_days", [0, 1, 2, 3, 4])
        current_weekday = current_time.weekday()
        is_working_day = current_weekday in working_days

        if not is_working_day:
            return {
                "available_hours": 0.0,
                "is_working_day": False,
                "is_working_hours": False,
                "suggested_timeframe": "tomorrow",
                "reason": f"Today is not a working day (weekday {current_weekday})",
            }

        start_time_str = self.working_hours.get("start_time", "09:00")
        end_time_str = self.working_hours.get("end_time", "18:00")

        start_hour, start_min = map(int, start_time_str.split(":"))
        end_hour, end_min = map(int, end_time_str.split(":"))

        work_start = current_time.replace(
            hour=start_hour, minute=start_min, second=0, microsecond=0
        )
        work_end = current_time.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

        is_working_hours = work_start <= current_time <= work_end

        if current_time < work_start:
            total_hours = (work_end - work_start).total_seconds() / 3600
            available_hours = total_hours
            reason = f"Before work hours (starts at {start_time_str})"
        elif current_time > work_end:
            return {
                "available_hours": 0.0,
                "is_working_day": True,
                "is_working_hours": False,
                "suggested_timeframe": "tomorrow",
                "reason": f"After work hours (ended at {end_time_str})",
            }
        else:
            available_hours = (work_end - current_time).total_seconds() / 3600
            reason = f"Currently {current_time.strftime('%H:%M')}, {available_hours:.1f}h until {end_time_str}"

        lunch_config = self.working_hours.get("lunch_break", {})
        if lunch_config.get("enabled", True):
            lunch_duration = lunch_config.get("duration", 1.0)
            lunch_start_str = lunch_config.get("start_time", "12:00")
            lunch_hour, lunch_min = map(int, lunch_start_str.split(":"))
            lunch_start = current_time.replace(
                hour=lunch_hour, minute=lunch_min, second=0, microsecond=0
            )
            lunch_end = lunch_start + timedelta(hours=lunch_duration)

            if current_time < lunch_end:
                overlap_start = max(current_time, lunch_start)
                overlap_end = min(work_end, lunch_end)
                if overlap_start < overlap_end:
                    lunch_deduction = (overlap_end - overlap_start).total_seconds() / 3600
                    available_hours -= lunch_deduction
                    reason += f" (minus {lunch_deduction:.1f}h lunch)"

        buffer_pct = planning_config.get("buffer_percentage", 0.25)
        available_hours *= 1 - buffer_pct
        reason += f" x {int((1 - buffer_pct) * 100)}% buffer = {available_hours:.1f}h available"

        min_hours = planning_config.get("min_hours_today", 1.0)
        quick_threshold = planning_config.get("quick_task_threshold", 2.0)

        if available_hours < min_hours:
            suggested_timeframe = "tomorrow"
        elif available_hours < quick_threshold:
            suggested_timeframe = "end_of_day"
        else:
            suggested_timeframe = "today"

        return {
            "available_hours": round(available_hours, 2),
            "is_working_day": is_working_day,
            "is_working_hours": is_working_hours,
            "suggested_timeframe": suggested_timeframe,
            "reason": reason,
        }

    def filter_tasks_by_available_time(
        self,
        tasks: List[Dict],
        available_hours: float,
        timeframe: str = "today",
    ) -> List[Dict]:
        if timeframe == "tomorrow":
            return tasks

        fitting_tasks = []
        cumulative_effort = 0.0

        sorted_tasks = sorted(
            tasks,
            key=lambda t: (
                -(t.get("priority", 3)),
                t.get("due_date") or "9999-12-31",
                -(t.get("impact", 3) / max(t.get("effort", 1), 0.1)),
            ),
        )

        for task in sorted_tasks:
            effort = task.get("effort", 0) or 0

            if timeframe == "end_of_day":
                quick_threshold = self.working_hours.get("planning", {}).get(
                    "quick_task_threshold", 2.0
                )
                if effort > quick_threshold:
                    continue

            if cumulative_effort + effort <= available_hours:
                fitting_tasks.append(task)
                cumulative_effort += effort

        return fitting_tasks

    def get_planning_summary(self, current_time: Optional[datetime] = None) -> Dict:
        time_info = self.get_available_hours_today(current_time)

        summary = {
            "current_time": (current_time or datetime.now()).strftime("%Y-%m-%d %H:%M"),
            "time_info": time_info,
            "recommendations": [],
        }

        timeframe = time_info["suggested_timeframe"]
        available = time_info["available_hours"]

        if timeframe == "tomorrow":
            summary["recommendations"].append(
                f"Limited time today ({available:.1f}h). Focus on planning tomorrow's tasks."
            )
        elif timeframe == "end_of_day":
            summary["recommendations"].append(
                f"Only {available:.1f}h remaining. Suggest quick wins and wrap-up tasks."
            )
        else:
            summary["recommendations"].append(
                f"{available:.1f}h available. Can tackle {int(available / 2)}-{int(available / 1)} medium-effort tasks."
            )

        return summary
