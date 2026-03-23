"""
Intelligent prioritization engine for Quarterback.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class PriorityScore:
    """Score breakdown for a task's priority."""

    task_id: int
    total_score: float
    impact_score: float
    urgency_score: float
    strategic_score: float
    effort_score: float
    quick_win_score: float
    recommendation: str
    reasoning: List[str]


class PrioritizationEngine:
    """
    Intelligent prioritization engine that considers multiple factors:
    - Impact on organizational goals
    - Urgency (due dates, blockers)
    - Strategic alignment
    - Effort required
    - Quick win potential
    """

    def __init__(
        self, org_context: Dict[str, Any], advisory_context: Optional[Dict[str, Any]] = None
    ):
        self.org_context = org_context
        self.advisory_context = advisory_context or {}
        self.weights = {
            "impact": 0.30,
            "urgency": 0.25,
            "strategic": 0.25,
            "effort": 0.15,
            "quick_win": 0.05,
        }

    def calculate_priority(
        self, task: Dict[str, Any], project: Optional[Dict[str, Any]] = None
    ) -> PriorityScore:
        """Calculate comprehensive priority score for a task."""

        reasoning = []

        impact_score = self._calculate_impact(task, project, reasoning)
        urgency_score = self._calculate_urgency(task, reasoning)
        strategic_score = self._calculate_strategic_alignment(task, project, reasoning)
        effort_score = self._calculate_effort_score(task, reasoning)
        quick_win_score = self._calculate_quick_win_score(impact_score, effort_score, reasoning)

        total_score = (
            impact_score * self.weights["impact"]
            + urgency_score * self.weights["urgency"]
            + strategic_score * self.weights["strategic"]
            + effort_score * self.weights["effort"]
            + quick_win_score * self.weights["quick_win"]
        )

        recommendation = self._generate_recommendation(total_score, quick_win_score, reasoning)

        return PriorityScore(
            task_id=task["id"],
            total_score=round(total_score, 2),
            impact_score=round(impact_score, 2),
            urgency_score=round(urgency_score, 2),
            strategic_score=round(strategic_score, 2),
            effort_score=round(effort_score, 2),
            quick_win_score=round(quick_win_score, 2),
            recommendation=recommendation,
            reasoning=reasoning,
        )

    def _calculate_impact(
        self, task: Dict[str, Any], project: Optional[Dict[str, Any]], reasoning: List[str]
    ) -> float:
        score = task.get("impact", 3)

        if project:
            if project.get("revenue_potential") == "high":
                score = min(5, score + 0.5)
                reasoning.append("Part of high-revenue project")

            if project.get("strategic_value") == "high":
                score = min(5, score + 0.5)
                reasoning.append("High strategic value")

        return score

    def _calculate_urgency(self, task: Dict[str, Any], reasoning: List[str]) -> float:
        score = 0.0

        if task.get("due_date"):
            due_date = (
                datetime.fromisoformat(task["due_date"])
                if isinstance(task["due_date"], str)
                else task["due_date"]
            )
            days_until_due = (due_date - datetime.now()).days

            if days_until_due < 0:
                score = 5.0
                reasoning.append("OVERDUE")
            elif days_until_due <= 1:
                score = 4.5
                reasoning.append("Due within 24 hours")
            elif days_until_due <= 3:
                score = 4.0
                reasoning.append("Due within 3 days")
            elif days_until_due <= 7:
                score = 3.0
                reasoning.append("Due this week")
            elif days_until_due <= 14:
                score = 2.0
                reasoning.append("Due within 2 weeks")
            else:
                score = 1.0

        if task.get("blocks_other_tasks"):
            score = min(5, score + 2.0)
            reasoning.append("Blocking other tasks")

        return score

    def _calculate_strategic_alignment(
        self, task: Dict[str, Any], project: Optional[Dict[str, Any]], reasoning: List[str]
    ) -> float:
        score = 3.0

        if not project:
            return score

        project_priority = project.get("priority", 3)
        if project_priority == 1:
            score = 5.0
            reasoning.append("Top priority project")
        elif project_priority == 2:
            score = 4.0
            reasoning.append("High priority project")
        elif project_priority <= 3:
            score = 3.0

        if task.get("is_milestone"):
            score = min(5, score + 1.0)
            reasoning.append("Milestone task")

        return score

    def _calculate_effort_score(self, task: Dict[str, Any], reasoning: List[str]) -> float:
        effort_hours = task.get("effort", 4)

        if effort_hours <= 1:
            score = 5.0
            reasoning.append("Very quick (<1 hour)")
        elif effort_hours <= 2:
            score = 4.5
            reasoning.append("Quick (1-2 hours)")
        elif effort_hours <= 4:
            score = 4.0
            reasoning.append("Moderate (2-4 hours)")
        elif effort_hours <= 8:
            score = 3.0
            reasoning.append("Standard (4-8 hours)")
        else:
            score = 2.0
            reasoning.append("Large effort (>8 hours)")

        return score

    def _calculate_quick_win_score(
        self, impact_score: float, effort_score: float, reasoning: List[str]
    ) -> float:
        if impact_score >= 4.0 and effort_score >= 4.0:
            reasoning.append("QUICK WIN: High impact, low effort!")
            return 5.0
        elif impact_score >= 3.5 and effort_score >= 4.0:
            return 4.0
        elif impact_score >= 3.0 and effort_score >= 3.5:
            return 3.0
        return 0.0

    def _generate_recommendation(
        self, total_score: float, quick_win_score: float, reasoning: List[str]
    ) -> str:
        if quick_win_score >= 4.0:
            return "DO NOW - Quick win opportunity"
        elif total_score >= 4.5:
            return "HIGH PRIORITY - Work on this today"
        elif total_score >= 3.5:
            return "MEDIUM PRIORITY - Schedule this week"
        elif total_score >= 2.5:
            return "NORMAL PRIORITY - Add to backlog"
        else:
            return "LOW PRIORITY - Consider deferring"

    def detect_conflicts(
        self, tasks: List[Dict[str, Any]], projects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect conflicting priorities and resource constraints."""
        conflicts = []

        high_priority_tasks = [t for t in tasks if t.get("priority", 3) >= 4]
        due_date_groups = {}

        for task in high_priority_tasks:
            if task.get("due_date"):
                due_str = str(task["due_date"])[:10]
                if due_str not in due_date_groups:
                    due_date_groups[due_str] = []
                due_date_groups[due_str].append(task)

        for due_date, task_group in due_date_groups.items():
            if len(task_group) > 1:
                total_effort = sum(t.get("effort", 4) for t in task_group)
                if total_effort > 8:
                    conflicts.append(
                        {
                            "type": "time_conflict",
                            "severity": "high",
                            "description": f"{len(task_group)} high-priority tasks due on {due_date} requiring {total_effort} hours total",
                            "tasks": [t["id"] for t in task_group],
                        }
                    )

        active_high_priority_projects = [
            p for p in projects if p.get("status") == "active" and p.get("priority", 3) <= 2
        ]

        if len(active_high_priority_projects) > 2:
            conflicts.append(
                {
                    "type": "focus_conflict",
                    "severity": "medium",
                    "description": f"{len(active_high_priority_projects)} high-priority projects active simultaneously - consider focusing efforts",
                    "projects": [p["name"] for p in active_high_priority_projects],
                }
            )

        return conflicts

    def identify_quick_wins(
        self, tasks: List[Dict[str, Any]], limit: int = 5
    ) -> List[PriorityScore]:
        """Identify quick win tasks."""
        scores = []
        for task in tasks:
            if task.get("status") not in ["completed", "blocked"]:
                score = self.calculate_priority(task, None)
                if score.quick_win_score >= 3.0:
                    scores.append(score)

        scores.sort(key=lambda x: (x.quick_win_score, x.total_score), reverse=True)
        return scores[:limit]

    def assess_task_value(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Assess if a proposed task is valuable or potentially counter-productive."""
        warnings = []
        suggestions = []

        task_lower = task_description.lower()

        time_waster_keywords = [
            "premature optimization",
            "perfect",
            "refactor everything",
            "rewrite from scratch",
            "build custom cms",
        ]

        for keyword in time_waster_keywords:
            if keyword in task_lower:
                warnings.append(
                    f"Potential time sink detected: '{keyword}' - consider if this truly adds value"
                )

        anti_goals = context.get("anti_goals", [])
        for anti_goal in anti_goals:
            if anti_goal.lower() in task_lower:
                warnings.append(f"Conflicts with anti-goal: '{anti_goal}' - reconsider this task")

        if any(word in task_lower for word in ["build", "create", "new", "implement"]):
            if "validate" not in task_lower and "mvp" not in task_lower:
                suggestions.append(
                    "Consider: Is there market validation for this? Should you start with an MVP?"
                )

        if "requirements" not in task_lower and "spec" not in task_lower:
            if any(word in task_lower for word in ["feature", "system", "platform", "service"]):
                suggestions.append(
                    "Consider: Do you have clear requirements defined before starting?"
                )

        approved_recs = self.advisory_context.get("approved_recommendations", [])
        for rec in approved_recs:
            if self._matches_recommendation(task_description, rec.get("text", "")):
                suggestions.append(
                    f"Aligns with approved advisory recommendation from: {rec.get('source', 'advisory document')}"
                )

        rejected_recs = self.advisory_context.get("rejected_recommendations", [])
        for rec in rejected_recs:
            if self._matches_recommendation(task_description, rec.get("text", "")):
                warnings.append(
                    f"Similar to previously rejected recommendation from: {rec.get('source', 'advisory document')}"
                )

        assessment = "valuable"
        if len(warnings) >= 2:
            assessment = "potentially_wasteful"
        elif len(warnings) == 1:
            assessment = "needs_clarification"

        return {
            "assessment": assessment,
            "warnings": warnings,
            "suggestions": suggestions,
            "should_proceed": len(warnings) == 0,
        }

    def _matches_recommendation(self, task_description: str, recommendation_text: str) -> bool:
        if not recommendation_text:
            return False

        task_lower = task_description.lower()
        rec_lower = recommendation_text.lower()

        common_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
        }
        task_words = set(
            word for word in task_lower.split() if word not in common_words and len(word) > 3
        )
        rec_words = set(
            word for word in rec_lower.split() if word not in common_words and len(word) > 3
        )

        if not task_words or not rec_words:
            return False

        overlap = task_words.intersection(rec_words)
        overlap_ratio = len(overlap) / min(len(task_words), len(rec_words))

        return overlap_ratio > 0.3
