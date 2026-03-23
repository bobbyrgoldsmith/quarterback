"""
Advisory document analyzer for Quarterback.
Analyzes external reference materials against organizational context.
"""

import json
import re
from typing import Dict, Any, List, Optional

import yaml

from quarterback.config import CONFIG_DIR


# Default alignment keywords — users can override via config/alignment.yaml
_DEFAULT_GOAL_KEYWORDS = {
    "newsletter": ["newsletter", "email list"],
    "content": [
        "content",
        "blog",
        "article",
        "post",
        "youtube",
        "video",
        "social media",
        "twitter",
        "linkedin",
    ],
    "growth": ["subscriber", "audience", "follower", "reach", "traffic", "seo"],
    "digital_product": ["pdf", "template", "guide", "ebook", "course", "digital product"],
    "saas": ["saas", "platform", "api", "tool", "service", "automation"],
    "monetization": ["revenue", "monetize", "income", "profit", "pricing", "paid"],
    "validation": ["mvp", "validate", "test idea"],
    "automation": ["automate", "automation"],
}

_DEFAULT_TECH_CONFLICTS = {
    "java": "Java not in preferred tech stack",
    ".net": ".NET not in preferred tech stack",
    "php": "PHP not in preferred tech stack",
    "ruby": "Ruby not in preferred tech stack",
}

_DEFAULT_GOAL_LABELS = {
    "newsletter": "Aligns with newsletter growth focus",
    "content": "Supports content publication strategy",
    "growth": "Aligns with audience growth goals",
    "digital_product": "Supports digital product strategy",
    "saas": "Aligns with SaaS/tools development goals",
    "monetization": "Aligns with revenue generation goals",
    "validation": "Supports lean/validation approach",
    "automation": "Aligns with automation and efficiency goals",
}


def _load_alignment_config() -> Dict[str, Any]:
    """Load user alignment overrides, merge with defaults."""
    user_path = CONFIG_DIR / "alignment.yaml"
    if not user_path.exists():
        return {
            "goal_keywords": _DEFAULT_GOAL_KEYWORDS,
            "tech_conflicts": _DEFAULT_TECH_CONFLICTS,
            "goal_labels": _DEFAULT_GOAL_LABELS,
        }

    try:
        with open(user_path) as f:
            user_cfg = yaml.safe_load(f) or {}
    except Exception:
        return {
            "goal_keywords": _DEFAULT_GOAL_KEYWORDS,
            "tech_conflicts": _DEFAULT_TECH_CONFLICTS,
            "goal_labels": _DEFAULT_GOAL_LABELS,
        }

    merged_keywords = {**_DEFAULT_GOAL_KEYWORDS, **user_cfg.get("goal_keywords", {})}
    merged_tech = {**_DEFAULT_TECH_CONFLICTS, **user_cfg.get("tech_conflicts", {})}
    merged_labels = {**_DEFAULT_GOAL_LABELS, **user_cfg.get("goal_labels", {})}

    return {
        "goal_keywords": merged_keywords,
        "tech_conflicts": merged_tech,
        "goal_labels": merged_labels,
    }


class AdvisoryAnalyzer:
    """
    Analyzes advisory documents against organizational context.
    Identifies conflicts, synergies, and extracts actionable recommendations.
    """

    def __init__(self, org_context: Dict[str, Any]):
        self.org_context = org_context
        self.goals = self._parse_goals(org_context.get("goals_content", ""))
        self.constraints = self._parse_constraints(org_context.get("constraints_content", ""))
        self.projects = org_context.get("projects", {})
        self.workflows = org_context.get("workflows", {})
        self._alignment = _load_alignment_config()

    def _parse_goals(self, goals_content: str) -> Dict[str, List[str]]:
        goals = {"strategic": [], "workflow": [], "project": [], "anti_goals": []}

        lines = goals_content.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "strategic" in line.lower() and "#" in line:
                current_section = "strategic"
            elif "workflow" in line.lower() and "#" in line:
                current_section = "workflow"
            elif "project" in line.lower() and "#" in line:
                current_section = "project"
            elif "anti-goal" in line.lower() and "#" in line:
                current_section = "anti_goals"
            elif line.startswith("-") or line.startswith("*"):
                goal_text = line.lstrip("-*").strip()
                if current_section and goal_text:
                    goals[current_section].append(goal_text)

        return goals

    def _parse_constraints(self, constraints_content: str) -> Dict[str, List[str]]:
        constraints = {"time": [], "budget": [], "tech": [], "strategic": []}

        lines = constraints_content.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "time" in line.lower() and "#" in line:
                current_section = "time"
            elif "budget" in line.lower() and "#" in line:
                current_section = "budget"
            elif "tech" in line.lower() and "#" in line:
                current_section = "tech"
            elif "strategic" in line.lower() and "#" in line:
                current_section = "strategic"
            elif line.startswith("-") or line.startswith("*"):
                constraint_text = line.lstrip("-*").strip()
                if current_section and constraint_text:
                    constraints[current_section].append(constraint_text)

        return constraints

    async def analyze_document(self, document: Any, session: Any) -> Dict[str, Any]:
        from quarterback.database import AdvisoryRecommendation

        recommendations = self._extract_recommendations(document.content)

        analyzed_recs = []
        for rec_text in recommendations:
            analysis = self._analyze_recommendation(rec_text, document)
            analyzed_recs.append(analysis)

            rec = AdvisoryRecommendation(
                advisory_document_id=document.id,
                recommendation_text=rec_text,
                category=analysis["category"],
                conflicts_with=json.dumps(analysis["conflicts"]),
                aligns_with=json.dumps(analysis["synergies"]),
                estimated_effort_hours=analysis.get("estimated_effort"),
                estimated_impact=analysis.get("estimated_impact"),
                status="pending",
            )
            session.add(rec)

        await session.commit()

        overall = self._generate_overall_assessment(analyzed_recs)

        return {
            "extracted_recommendations": analyzed_recs,
            "conflicts": overall["conflicts"],
            "synergies": overall["synergies"],
            "pros": overall["pros"],
            "cons": overall["cons"],
            "overall_assessment": overall["assessment"],
            "recommendation": overall["recommendation"],
            "items_for_discussion": overall["discussion_items"],
        }

    def _extract_recommendations(self, content: str) -> List[str]:
        recommendations = []
        sentences = re.split(r"[.\n]+", content)

        recommendation_indicators = [
            r"\bshould\b",
            r"\brecommend\b",
            r"\bsuggest\b",
            r"\bconsider\b",
            r"\bmust\b",
            r"\bneed to\b",
            r"\bought to\b",
            r"\btry to\b",
            r"\bstart\b",
            r"\bstop\b",
            r"\bcontinue\b",
            r"\bimplement\b",
            r"\blaunch\b",
            r"\bcreate\b",
            r"\bbuild\b",
            r"\bfocus on\b",
            r"\bdevelop\b",
            r"\buse\b",
            r"\bavoid\b",
            r"\binvest in\b",
            r"\bprioritize\b",
            r"\boptimize\b",
            r"\bleverage\b",
        ]

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 10:
                continue

            lower_sentence = sentence.lower()
            if any(re.search(pattern, lower_sentence) for pattern in recommendation_indicators):
                sentence = sentence.strip("- *")
                if sentence:
                    recommendations.append(sentence)

        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)

        return unique_recommendations[:20]

    def _analyze_recommendation(self, rec_text: str, document: Any) -> Dict[str, Any]:
        analysis = {
            "text": rec_text,
            "category": self._categorize_recommendation(rec_text),
            "conflicts": [],
            "synergies": [],
            "estimated_effort": None,
            "estimated_impact": None,
        }

        conflicts = self._check_constraints_conflicts(rec_text)
        analysis["conflicts"].extend(conflicts)

        synergies = self._check_goal_alignment(rec_text)
        analysis["synergies"].extend(synergies)

        analysis["estimated_effort"] = self._estimate_effort(rec_text)
        analysis["estimated_impact"] = self._estimate_impact(rec_text, len(synergies))

        return analysis

    def _check_constraints_conflicts(self, rec_text: str) -> List[str]:
        conflicts = []
        lower_rec = rec_text.lower()

        urgency_words = ["immediately", "urgent", "now", "asap", "right away", "today"]
        if any(word in lower_rec for word in urgency_words):
            if any("focus" in c.lower() for c in self.constraints.get("strategic", [])):
                conflicts.append("Urgency may conflict with current strategic focus constraints")

        expensive_indicators = ["expensive", "invest $", "cost", "paid", "subscription", "hire"]
        if any(indicator in lower_rec for indicator in expensive_indicators):
            budget_constraints = self.constraints.get("budget", [])
            if budget_constraints:
                conflicts.append(f"May conflict with budget constraints: {budget_constraints[0]}")

        tech_conflicts = self._alignment["tech_conflicts"]
        for tech, conflict_msg in tech_conflicts.items():
            if tech in lower_rec:
                tech_constraints = self.constraints.get("tech", [])
                if tech_constraints or "python" in str(self.org_context).lower():
                    conflicts.append(conflict_msg)

        consulting_words = ["consulting", "freelance", "client work", "agency"]
        if any(word in lower_rec for word in consulting_words):
            anti_goals = self.goals.get("anti_goals", [])
            if any("consulting" in ag.lower() or "client" in ag.lower() for ag in anti_goals):
                conflicts.append("Conflicts with anti-goal: Avoid consulting/client work")

        premature_scale = ["scale", "enterprise", "team of", "hire multiple"]
        if any(word in lower_rec for word in premature_scale):
            if "mvp" in str(self.goals).lower() or "validate" in str(self.goals).lower():
                conflicts.append("May be premature scaling - focus on validation first")

        return conflicts

    def _check_goal_alignment(self, rec_text: str) -> List[str]:
        synergies = []
        lower_rec = rec_text.lower()

        goal_keywords = self._alignment["goal_keywords"]
        goal_labels = self._alignment["goal_labels"]

        for key, keywords in goal_keywords.items():
            if key == "monetization":
                if any(word in lower_rec for word in keywords):
                    goals_text = " ".join(
                        self.goals.get("strategic", []) + self.goals.get("workflow", [])
                    )
                    if "revenue" in goals_text.lower() or "monetize" in goals_text.lower():
                        synergies.append(goal_labels.get(key, f"Aligns with {key} goals"))
            else:
                if any(word in lower_rec for word in keywords):
                    synergies.append(goal_labels.get(key, f"Aligns with {key} goals"))

        return synergies

    def _categorize_recommendation(self, rec_text: str) -> str:
        text_lower = rec_text.lower()

        categories = {
            "monetization": [
                "revenue",
                "monetize",
                "price",
                "paid",
                "premium",
                "subscription",
                "sponsor",
            ],
            "content_strategy": ["content", "publish", "write", "blog", "video", "podcast"],
            "growth": ["subscriber", "audience", "growth", "reach", "traffic", "viral"],
            "tools": ["tool", "software", "platform", "api", "automation"],
            "metrics": ["metric", "measure", "track", "analytics", "data"],
            "marketing": ["market", "promote", "advertis", "campaign", "seo", "social"],
            "product": ["product", "feature", "build", "develop", "launch"],
        }

        for category, keywords in categories.items():
            if any(keyword in text_lower for keyword in keywords):
                return category

        return "strategy"

    def _estimate_effort(self, rec_text: str) -> Optional[float]:
        text_lower = rec_text.lower()

        quick_indicators = ["tweak", "adjust", "update", "change", "fix", "optimize"]
        if any(word in text_lower for word in quick_indicators):
            return 1.5

        small_indicators = ["add", "create simple", "write", "setup", "configure"]
        if any(word in text_lower for word in small_indicators):
            return 3.0

        medium_indicators = ["create", "implement", "develop", "design", "integrate"]
        if any(word in text_lower for word in medium_indicators):
            return 6.0

        large_indicators = ["build", "launch", "develop complete", "full", "system", "platform"]
        if any(word in text_lower for word in large_indicators):
            return 20.0

        return 5.0

    def _estimate_impact(self, rec_text: str, synergy_count: int) -> Optional[int]:
        base_impact = 3

        if synergy_count >= 3:
            base_impact = 4
        elif synergy_count >= 2:
            base_impact = 3
        elif synergy_count == 0:
            base_impact = 2

        text_lower = rec_text.lower()
        if any(word in text_lower for word in ["revenue", "money", "profit", "income"]):
            base_impact = min(5, base_impact + 1)

        if any(word in text_lower for word in ["growth", "scale", "viral", "10x"]):
            base_impact = min(5, base_impact + 1)

        if any(word in text_lower for word in ["debug", "refactor", "internal"]):
            base_impact = max(1, base_impact - 1)

        return base_impact

    def _generate_overall_assessment(self, analyzed_recs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not analyzed_recs:
            return {
                "conflicts": [],
                "synergies": [],
                "pros": ["No actionable recommendations extracted"],
                "cons": ["Document may be too general or lack specific advice"],
                "assessment": "needs_clarification",
                "recommendation": "Review document manually for implicit recommendations",
                "discussion_items": ["Are there specific actions to take from this document?"],
            }

        total_conflicts = sum(len(r["conflicts"]) for r in analyzed_recs)
        total_synergies = sum(len(r["synergies"]) for r in analyzed_recs)

        if total_synergies > total_conflicts * 2:
            assessment = "highly_aligned"
            recommendation = (
                "Strong alignment with current goals. Recommend discussing implementation timeline."
            )
        elif total_synergies > total_conflicts:
            assessment = "aligned"
            recommendation = "Generally aligned. Review specific recommendations for adoption."
        elif total_synergies == total_conflicts or (total_synergies > 0 and total_conflicts > 0):
            assessment = "partially_aligned"
            recommendation = "Mixed alignment. Discuss trade-offs before adoption."
        else:
            assessment = "conflicts_detected"
            recommendation = "Significant conflicts with current constraints/goals. Consider deferring or archiving."

        all_conflicts = []
        all_synergies = []
        for rec in analyzed_recs:
            all_conflicts.extend(rec["conflicts"])
            all_synergies.extend(rec["synergies"])

        all_conflicts = list(set(all_conflicts))
        all_synergies = list(set(all_synergies))

        pros = []
        cons = []

        if all_synergies:
            pros.append(f"Aligns with {len(all_synergies)} organizational priorities")

        if len(analyzed_recs) > 0:
            pros.append(f"Provides {len(analyzed_recs)} specific recommendations")

        quick_wins = [
            r
            for r in analyzed_recs
            if r.get("estimated_effort", 100) < 5 and r.get("estimated_impact", 0) >= 4
        ]
        if quick_wins:
            pros.append(f"Contains {len(quick_wins)} quick win recommendations")

        if all_conflicts:
            cons.append(f"Conflicts with {len(all_conflicts)} current constraints/goals")

        if total_conflicts > total_synergies:
            cons.append("More conflicts than synergies detected")

        discussion_items = []
        if "conflicts_detected" in assessment or "partially" in assessment:
            discussion_items.append("Should any current constraints be adjusted?")
            discussion_items.append("What's the priority ordering of conflicting recommendations?")

        if quick_wins:
            discussion_items.append(f"Should we prioritize the {len(quick_wins)} quick win(s)?")

        return {
            "conflicts": all_conflicts,
            "synergies": all_synergies,
            "pros": pros if pros else ["Document provides external perspective"],
            "cons": cons if cons else ["No significant concerns identified"],
            "assessment": assessment,
            "recommendation": recommendation,
            "discussion_items": discussion_items if discussion_items else [],
        }
