"""Tests for the advisory analyzer."""

import pytest
from quarterback.advisory_analyzer import AdvisoryAnalyzer
from quarterback.database import AdvisoryDocument, AdvisoryRecommendation
from sqlalchemy import select


@pytest.fixture
def analyzer(sample_org_context):
    return AdvisoryAnalyzer(sample_org_context)


@pytest.fixture
def empty_analyzer():
    return AdvisoryAnalyzer({})


class TestExtractRecommendations:
    def test_extracts_should_sentences(self, analyzer):
        content = "You should focus on building an email list. Ignore social media for now."
        recs = analyzer._extract_recommendations(content)
        assert len(recs) >= 1
        assert any("email" in r.lower() for r in recs)

    def test_extracts_recommend_sentences(self, analyzer):
        content = "We recommend investing in content marketing. It drives organic growth."
        recs = analyzer._extract_recommendations(content)
        assert len(recs) >= 1

    def test_extracts_consider_sentences(self, analyzer):
        content = "Consider launching a newsletter. It builds direct audience connection."
        recs = analyzer._extract_recommendations(content)
        assert len(recs) >= 1

    def test_skips_short_sentences(self, analyzer):
        content = "Do it. Build. Create. These short ones should be skipped."
        recs = analyzer._extract_recommendations(content)
        # The "These short ones should be skipped" should be caught
        assert all(len(r) >= 10 for r in recs)

    def test_deduplicates(self, analyzer):
        content = "You should build an API. You should build an API. Build something new."
        recs = analyzer._extract_recommendations(content)
        assert len(recs) == len(set(recs))

    def test_limits_to_20(self, analyzer):
        content = "\n".join([f"You should do thing number {i}" for i in range(30)])
        recs = analyzer._extract_recommendations(content)
        assert len(recs) <= 20

    def test_empty_content(self, analyzer):
        recs = analyzer._extract_recommendations("")
        assert len(recs) == 0


class TestCheckConstraintsConflicts:
    def test_budget_conflict(self, analyzer):
        conflicts = analyzer._check_constraints_conflicts("Hire a team of 5 developers immediately")
        assert len(conflicts) >= 1

    def test_tech_stack_conflict(self, analyzer):
        conflicts = analyzer._check_constraints_conflicts(
            "Rewrite the backend in Java for better performance"
        )
        assert any("Java" in c for c in conflicts)

    def test_no_conflict_for_aligned_tech(self, analyzer):
        conflicts = analyzer._check_constraints_conflicts("Build the API in Python using FastAPI")
        tech_conflicts = [c for c in conflicts if "tech stack" in c.lower()]
        assert len(tech_conflicts) == 0

    def test_consulting_anti_goal_conflict(self, analyzer):
        conflicts = analyzer._check_constraints_conflicts("Start a consulting business on the side")
        assert any("consulting" in c.lower() for c in conflicts)

    def test_premature_scaling_conflict(self, analyzer):
        conflicts = analyzer._check_constraints_conflicts(
            "Scale the enterprise platform to 10,000 users"
        )
        assert len(conflicts) >= 1


class TestCheckGoalAlignment:
    def test_content_alignment(self, analyzer):
        synergies = analyzer._check_goal_alignment(
            "Start publishing blog posts about developer tools"
        )
        assert len(synergies) >= 1

    def test_newsletter_alignment(self, analyzer):
        synergies = analyzer._check_goal_alignment("Build an email newsletter for subscribers")
        assert len(synergies) >= 1

    def test_saas_alignment(self, analyzer):
        synergies = analyzer._check_goal_alignment("Build a SaaS platform with an API")
        assert len(synergies) >= 1

    def test_no_alignment_for_unrelated(self, empty_analyzer):
        synergies = empty_analyzer._check_goal_alignment("Go fishing on Saturday")
        assert len(synergies) == 0


class TestCategorizeRecommendation:
    def test_monetization_category(self, analyzer):
        assert analyzer._categorize_recommendation("Focus on revenue and pricing") == "monetization"

    def test_content_category(self, analyzer):
        assert (
            analyzer._categorize_recommendation("Publish blog posts weekly") == "content_strategy"
        )

    def test_growth_category(self, analyzer):
        assert analyzer._categorize_recommendation("Grow your subscriber audience") == "growth"

    def test_default_strategy(self, analyzer):
        assert analyzer._categorize_recommendation("Think carefully about next steps") == "strategy"


class TestEstimateEffort:
    def test_quick_task(self, analyzer):
        effort = analyzer._estimate_effort("Tweak the homepage copy")
        assert effort == 1.5

    def test_medium_task(self, analyzer):
        effort = analyzer._estimate_effort("Implement a new authentication system")
        assert effort == 6.0

    def test_large_task(self, analyzer):
        effort = analyzer._estimate_effort("Build a complete analytics platform from scratch")
        assert effort == 20.0


class TestAnalyzeDocument:
    @pytest.mark.asyncio
    async def test_full_analysis(self, analyzer, db_session):
        doc = AdvisoryDocument(
            id=1,
            title="Growth Strategy",
            content="You should build an email newsletter. Consider creating blog content regularly. Invest in SEO for organic traffic.",
            priority=3,
        )
        db_session.add(doc)
        await db_session.commit()

        analysis = await analyzer.analyze_document(doc, db_session)

        assert "extracted_recommendations" in analysis
        assert "overall_assessment" in analysis
        assert "conflicts" in analysis
        assert "synergies" in analysis
        assert len(analysis["extracted_recommendations"]) >= 1

    @pytest.mark.asyncio
    async def test_analysis_creates_recommendations(self, analyzer, db_session):
        doc = AdvisoryDocument(
            id=2,
            title="Test Doc",
            content="You should automate your deployment pipeline.",
            priority=3,
        )
        db_session.add(doc)
        await db_session.commit()

        await analyzer.analyze_document(doc, db_session)

        result = await db_session.execute(
            select(AdvisoryRecommendation).where(
                AdvisoryRecommendation.advisory_document_id == doc.id
            )
        )
        recs = result.scalars().all()
        assert len(recs) >= 1
