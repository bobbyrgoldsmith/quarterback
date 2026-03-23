"""Tests for time-aware planning."""

import pytest
from datetime import datetime
from quarterback.time_planner import TimeAwarePlanner


@pytest.fixture
def planner(tmp_path):
    """Planner with a test config."""
    config_path = tmp_path / "alerts.yaml"
    config_path.write_text("""
working_hours:
  working_days: [0, 1, 2, 3, 4]
  start_time: "09:00"
  end_time: "18:00"
  lunch_break:
    enabled: true
    duration: 1.0
    start_time: "12:00"
  planning:
    time_aware: true
    min_hours_today: 1.0
    buffer_percentage: 0.25
    quick_task_threshold: 2.0
""")
    return TimeAwarePlanner(config_path=config_path)


@pytest.fixture
def planner_no_config(tmp_path):
    """Planner with no config file."""
    return TimeAwarePlanner(config_path=tmp_path / "nonexistent.yaml")


class TestAvailableHours:
    def test_before_work_hours(self, planner):
        # Monday at 7:00 AM
        dt = datetime(2026, 3, 23, 7, 0)  # Monday
        result = planner.get_available_hours_today(dt)
        assert result["is_working_day"] is True
        assert result["available_hours"] > 0
        assert "Before work hours" in result["reason"]

    def test_during_work_hours(self, planner):
        # Monday at 10:00 AM
        dt = datetime(2026, 3, 23, 10, 0)
        result = planner.get_available_hours_today(dt)
        assert result["is_working_day"] is True
        assert result["is_working_hours"] is True
        assert result["available_hours"] > 0

    def test_after_work_hours(self, planner):
        # Monday at 7:00 PM
        dt = datetime(2026, 3, 23, 19, 0)
        result = planner.get_available_hours_today(dt)
        assert result["available_hours"] == 0.0
        assert result["suggested_timeframe"] == "tomorrow"

    def test_non_working_day(self, planner):
        # Saturday
        dt = datetime(2026, 3, 28, 10, 0)
        result = planner.get_available_hours_today(dt)
        assert result["is_working_day"] is False
        assert result["available_hours"] == 0.0

    def test_lunch_deduction(self, planner):
        # Monday at 11:00 AM (before lunch, lunch should be deducted)
        dt = datetime(2026, 3, 23, 11, 0)
        result = planner.get_available_hours_today(dt)
        # 7 hours until 18:00, minus 1h lunch, times 0.75 buffer
        assert result["available_hours"] < 7.0

    def test_after_lunch(self, planner):
        # Monday at 13:00 (after lunch)
        dt = datetime(2026, 3, 23, 13, 0)
        result = planner.get_available_hours_today(dt)
        # 5 hours until 18:00, times 0.75 buffer = 3.75
        assert 3.0 <= result["available_hours"] <= 4.0

    def test_end_of_day_timeframe(self, planner):
        # Monday at 16:30 — ~1.5h remaining after buffer
        dt = datetime(2026, 3, 23, 16, 30)
        result = planner.get_available_hours_today(dt)
        assert result["suggested_timeframe"] in ["end_of_day", "tomorrow"]

    def test_no_config_defaults(self, planner_no_config):
        result = planner_no_config.get_available_hours_today()
        # No config means no working_hours, so time_aware check returns True by default
        assert isinstance(result["available_hours"], float)

    def test_time_aware_disabled(self, tmp_path):
        config_path = tmp_path / "alerts.yaml"
        config_path.write_text("""
working_hours:
  planning:
    time_aware: false
""")
        planner = TimeAwarePlanner(config_path=config_path)
        result = planner.get_available_hours_today()
        assert result["available_hours"] == 8.0
        assert result["suggested_timeframe"] == "today"


class TestFilterTasks:
    def test_filters_by_available_time(self, planner):
        tasks = [
            {"effort": 2, "priority": 5, "impact": 5},
            {"effort": 3, "priority": 4, "impact": 4},
            {"effort": 4, "priority": 3, "impact": 3},
        ]
        filtered = planner.filter_tasks_by_available_time(tasks, 5.0, "today")
        total_effort = sum(t["effort"] for t in filtered)
        assert total_effort <= 5.0

    def test_tomorrow_returns_all(self, planner):
        tasks = [{"effort": 100, "priority": 3, "impact": 3}]
        filtered = planner.filter_tasks_by_available_time(tasks, 1.0, "tomorrow")
        assert len(filtered) == len(tasks)

    def test_end_of_day_only_quick_tasks(self, planner):
        tasks = [
            {"effort": 1, "priority": 5, "impact": 5},
            {"effort": 5, "priority": 5, "impact": 5},
        ]
        filtered = planner.filter_tasks_by_available_time(tasks, 3.0, "end_of_day")
        assert all(t["effort"] <= 2.0 for t in filtered)


class TestPlanningSummary:
    def test_summary_structure(self, planner):
        summary = planner.get_planning_summary(datetime(2026, 3, 23, 10, 0))
        assert "current_time" in summary
        assert "time_info" in summary
        assert "recommendations" in summary
        assert len(summary["recommendations"]) >= 1
