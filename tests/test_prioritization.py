"""Tests for the prioritization engine."""

import pytest
from datetime import datetime, timedelta
from quarterback.prioritization import PrioritizationEngine, PriorityScore


@pytest.fixture
def engine():
    return PrioritizationEngine({})


@pytest.fixture
def engine_with_context(sample_org_context):
    return PrioritizationEngine(sample_org_context)


class TestCalculatePriority:
    def test_basic_score(self, engine):
        task = {"id": 1, "description": "Test task", "priority": 3, "effort": 4, "impact": 3}
        score = engine.calculate_priority(task)
        assert isinstance(score, PriorityScore)
        assert score.task_id == 1
        assert 0 <= score.total_score <= 5

    def test_high_impact_high_priority(self, engine):
        task = {
            "id": 1,
            "description": "Critical",
            "priority": 5,
            "effort": 1,
            "impact": 5,
            "due_date": datetime.now() - timedelta(days=1),
        }
        score = engine.calculate_priority(task)
        assert score.total_score >= 4.0

    def test_low_priority_task(self, engine):
        task = {"id": 1, "description": "Low", "priority": 1, "effort": 20, "impact": 1}
        score = engine.calculate_priority(task)
        assert score.total_score <= 3.0

    def test_overdue_urgency(self, engine):
        task = {
            "id": 1,
            "description": "Overdue",
            "priority": 3,
            "effort": 4,
            "impact": 3,
            "due_date": datetime.now() - timedelta(days=2),
        }
        score = engine.calculate_priority(task)
        assert score.urgency_score == 5.0
        assert any("OVERDUE" in r for r in score.reasoning)

    def test_due_tomorrow_urgency(self, engine):
        task = {
            "id": 1,
            "description": "Tomorrow",
            "priority": 3,
            "effort": 4,
            "impact": 3,
            "due_date": datetime.now() + timedelta(hours=12),
        }
        score = engine.calculate_priority(task)
        assert score.urgency_score >= 4.0

    def test_due_in_3_days(self, engine):
        task = {
            "id": 1,
            "description": "Soon",
            "priority": 3,
            "effort": 4,
            "impact": 3,
            "due_date": datetime.now() + timedelta(days=2, hours=12),
        }
        score = engine.calculate_priority(task)
        assert score.urgency_score == 4.0

    def test_due_in_week(self, engine):
        task = {
            "id": 1,
            "description": "This week",
            "priority": 3,
            "effort": 4,
            "impact": 3,
            "due_date": datetime.now() + timedelta(days=5),
        }
        score = engine.calculate_priority(task)
        assert score.urgency_score == 3.0

    def test_no_due_date(self, engine):
        task = {"id": 1, "description": "No date", "priority": 3, "effort": 4, "impact": 3}
        score = engine.calculate_priority(task)
        assert score.urgency_score == 0.0

    def test_project_boosts_impact(self, engine):
        task = {"id": 1, "description": "Test", "priority": 3, "effort": 4, "impact": 3}
        project = {
            "name": "Alpha",
            "priority": 1,
            "revenue_potential": "high",
            "strategic_value": "high",
        }
        score = engine.calculate_priority(task, project)
        assert score.impact_score >= 3.5

    def test_top_priority_project(self, engine):
        task = {"id": 1, "description": "Test", "priority": 3, "effort": 4, "impact": 3}
        project = {"name": "Top", "priority": 1}
        score = engine.calculate_priority(task, project)
        assert score.strategic_score == 5.0

    def test_effort_very_quick(self, engine):
        task = {"id": 1, "description": "Quick", "priority": 3, "effort": 0.5, "impact": 3}
        score = engine.calculate_priority(task)
        assert score.effort_score == 5.0

    def test_effort_large(self, engine):
        task = {"id": 1, "description": "Huge", "priority": 3, "effort": 20, "impact": 3}
        score = engine.calculate_priority(task)
        assert score.effort_score == 2.0

    def test_quick_win_detected(self, engine):
        task = {"id": 1, "description": "Quick win", "priority": 3, "effort": 1, "impact": 5}
        score = engine.calculate_priority(task)
        assert score.quick_win_score >= 4.0
        assert "QUICK WIN" in score.recommendation or score.quick_win_score >= 4.0

    def test_no_quick_win_for_large_effort(self, engine):
        task = {"id": 1, "description": "Big", "priority": 3, "effort": 20, "impact": 5}
        score = engine.calculate_priority(task)
        assert score.quick_win_score == 0.0

    def test_string_due_date(self, engine):
        future = (datetime.now() + timedelta(days=5)).isoformat()
        task = {
            "id": 1,
            "description": "String date",
            "priority": 3,
            "effort": 4,
            "impact": 3,
            "due_date": future,
        }
        score = engine.calculate_priority(task)
        assert score.urgency_score > 0

    def test_recommendation_text(self, engine):
        task = {"id": 1, "description": "Test", "priority": 3, "effort": 4, "impact": 3}
        score = engine.calculate_priority(task)
        assert isinstance(score.recommendation, str)
        assert len(score.recommendation) > 0

    def test_weights_sum_to_one(self, engine):
        assert abs(sum(engine.weights.values()) - 1.0) < 0.01

    def test_max_score_cap(self, engine):
        task = {
            "id": 1,
            "description": "Max",
            "priority": 5,
            "effort": 0.5,
            "impact": 5,
            "due_date": datetime.now() - timedelta(days=1),
            "blocks_other_tasks": True,
        }
        project = {
            "name": "Top",
            "priority": 1,
            "revenue_potential": "high",
            "strategic_value": "high",
        }
        score = engine.calculate_priority(task, project)
        assert score.total_score <= 5.5  # Slightly over 5 possible due to all bonuses


class TestDetectConflicts:
    def test_no_conflicts_when_few_tasks(self, engine):
        tasks = [
            {
                "id": 1,
                "description": "Task",
                "priority": 4,
                "effort": 2,
                "due_date": str(datetime.now().date()),
            }
        ]
        projects = [{"name": "A", "priority": 1, "status": "active"}]
        conflicts = engine.detect_conflicts(tasks, projects)
        assert len(conflicts) == 0

    def test_time_conflict_detected(self, engine):
        due = str(datetime.now().date())
        tasks = [
            {"id": 1, "description": "T1", "priority": 4, "effort": 5, "due_date": due},
            {"id": 2, "description": "T2", "priority": 5, "effort": 5, "due_date": due},
        ]
        conflicts = engine.detect_conflicts(tasks, [])
        assert any(c["type"] == "time_conflict" for c in conflicts)

    def test_focus_conflict_detected(self, engine):
        projects = [
            {"name": "A", "priority": 1, "status": "active"},
            {"name": "B", "priority": 2, "status": "active"},
            {"name": "C", "priority": 1, "status": "active"},
        ]
        conflicts = engine.detect_conflicts([], projects)
        assert any(c["type"] == "focus_conflict" for c in conflicts)

    def test_no_focus_conflict_with_two_projects(self, engine):
        projects = [
            {"name": "A", "priority": 1, "status": "active"},
            {"name": "B", "priority": 2, "status": "active"},
        ]
        conflicts = engine.detect_conflicts([], projects)
        focus_conflicts = [c for c in conflicts if c["type"] == "focus_conflict"]
        assert len(focus_conflicts) == 0


class TestIdentifyQuickWins:
    def test_finds_quick_wins(self, engine):
        tasks = [
            {
                "id": 1,
                "description": "Quick",
                "priority": 3,
                "effort": 1,
                "impact": 5,
                "status": "pending",
            },
            {
                "id": 2,
                "description": "Slow",
                "priority": 3,
                "effort": 20,
                "impact": 2,
                "status": "pending",
            },
        ]
        wins = engine.identify_quick_wins(tasks)
        assert len(wins) >= 1
        assert wins[0].task_id == 1

    def test_excludes_completed(self, engine):
        tasks = [
            {
                "id": 1,
                "description": "Done",
                "priority": 3,
                "effort": 1,
                "impact": 5,
                "status": "completed",
            },
        ]
        wins = engine.identify_quick_wins(tasks)
        assert len(wins) == 0

    def test_respects_limit(self, engine):
        tasks = [
            {
                "id": i,
                "description": f"Win {i}",
                "priority": 3,
                "effort": 1,
                "impact": 5,
                "status": "pending",
            }
            for i in range(10)
        ]
        wins = engine.identify_quick_wins(tasks, limit=3)
        assert len(wins) <= 3


class TestAssessTaskValue:
    def test_valuable_task(self, engine_with_context):
        result = engine_with_context.assess_task_value("Launch MVP product", {})
        assert result["assessment"] == "valuable"
        assert result["should_proceed"] is True

    def test_time_waster_detected(self, engine_with_context):
        result = engine_with_context.assess_task_value(
            "Rewrite from scratch the entire backend", {}
        )
        assert len(result["warnings"]) > 0

    def test_anti_goal_detected(self, engine_with_context):
        result = engine_with_context.assess_task_value(
            "Start consulting work", {"anti_goals": ["consulting"]}
        )
        assert len(result["warnings"]) > 0

    def test_build_suggestion(self, engine_with_context):
        result = engine_with_context.assess_task_value("Build a new platform for users", {})
        assert len(result["suggestions"]) > 0
