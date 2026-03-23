"""Shared test fixtures for Quarterback."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from quarterback.database import Base, Organization, Project, Task


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Create a database session for testing."""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_org(db_session):
    """Create a sample organization."""
    org = Organization(name="Test Org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def sample_projects(db_session):
    """Create sample projects."""
    projects = [
        Project(name="Alpha", priority=1, status="active", description="Top priority project"),
        Project(name="Beta", priority=2, status="active", description="Second project"),
        Project(name="Gamma", priority=4, status="active", description="Low priority project"),
    ]
    for p in projects:
        db_session.add(p)
    await db_session.commit()
    for p in projects:
        await db_session.refresh(p)
    return projects


@pytest_asyncio.fixture
async def sample_tasks(db_session, sample_projects):
    """Create sample tasks across projects."""
    from datetime import datetime, timedelta

    now = datetime.now()
    tasks = [
        Task(
            project_id=sample_projects[0].id,
            description="Critical bug fix",
            priority=5,
            effort=1.0,
            impact=5,
            status="pending",
            due_date=now - timedelta(days=1),
        ),
        Task(
            project_id=sample_projects[0].id,
            description="Deploy v2 API",
            priority=4,
            effort=4.0,
            impact=4,
            status="in_progress",
            due_date=now + timedelta(days=1),
        ),
        Task(
            project_id=sample_projects[1].id,
            description="Write documentation",
            priority=2,
            effort=3.0,
            impact=2,
            status="pending",
            due_date=now + timedelta(days=14),
        ),
        Task(
            project_id=sample_projects[1].id,
            description="Add email templates",
            priority=3,
            effort=2.0,
            impact=3,
            status="pending",
        ),
        Task(
            project_id=sample_projects[2].id,
            description="Refactor logging",
            priority=1,
            effort=8.0,
            impact=1,
            status="pending",
        ),
        Task(
            project_id=None,
            description="Quick cleanup",
            priority=3,
            effort=0.5,
            impact=4,
            status="pending",
        ),
        Task(
            project_id=sample_projects[0].id,
            description="Update landing page",
            priority=4,
            effort=2.0,
            impact=5,
            status="pending",
            due_date=now + timedelta(days=3),
        ),
        Task(
            description="Completed old task", priority=3, effort=2.0, impact=3, status="completed"
        ),
    ]
    for t in tasks:
        db_session.add(t)
    await db_session.commit()
    for t in tasks:
        await db_session.refresh(t)
    return tasks


@pytest.fixture
def sample_org_context():
    """Sample organizational context for testing."""
    return {
        "goals_content": """# Goals
## Strategic Goals
- Launch MVP product
- Generate revenue from SaaS tools
- Build newsletter to 1000 subscribers

## Anti-Goals
- Consulting work
- Premature optimization
""",
        "constraints_content": """# Constraints
## Budget Constraints
- Max $100/month infrastructure
## Tech Constraints
- Python and TypeScript only
## Strategic Boundaries
- Focus on product-led growth
""",
        "workflows": {
            "workflows": [
                {"name": "Product", "status": "active", "priority": 1},
                {"name": "Content", "status": "active", "priority": 2},
            ]
        },
        "projects": {
            "projects": [
                {"name": "Alpha", "priority": 1, "status": "active"},
                {"name": "Beta", "priority": 2, "status": "active"},
            ]
        },
    }
