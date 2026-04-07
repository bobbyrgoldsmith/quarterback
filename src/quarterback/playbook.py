"""
Playbook — Compiled knowledge layer for Quarterback.

LLM wiki pattern: structured markdown pages that accumulate knowledge across
sessions. Claude reads and writes pages; humans browse in Obsidian or any
markdown viewer.

All file operations are synchronous (local disk I/O is fast).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from quarterback.config import (
    PLAYBOOK_COMPILED_DIR,
    PLAYBOOK_DIR,
    PLAYBOOK_SCHEMA_PATH,
    PLAYBOOK_WIKI_DIR,
)

CATEGORIES = ("entities", "concepts", "decisions", "compiled")


# ---------------------------------------------------------------------------
# Status & Discovery
# ---------------------------------------------------------------------------


def is_playbook_enabled() -> bool:
    """True if Playbook directory exists and has CLAUDE.md."""
    return PLAYBOOK_SCHEMA_PATH.exists()


def get_playbook_status() -> dict:
    """Check Playbook state and return summary."""
    if not is_playbook_enabled():
        return {"initialized": False, "path": str(PLAYBOOK_DIR)}

    counts: dict[str, int] = {}
    for cat in CATEGORIES:
        cat_dir = PLAYBOOK_WIKI_DIR / cat
        if cat_dir.is_dir():
            counts[cat] = len(list(cat_dir.glob("*.md")))
        else:
            counts[cat] = 0

    return {
        "initialized": True,
        "path": str(PLAYBOOK_DIR),
        "pages": counts,
        "total_pages": sum(counts.values()),
        "has_index": (PLAYBOOK_WIKI_DIR / "index.md").exists(),
        "has_compiled_goals": (PLAYBOOK_COMPILED_DIR / "goals.md").exists(),
        "has_compiled_constraints": (PLAYBOOK_COMPILED_DIR / "constraints.md").exists(),
        "has_obsidian": (PLAYBOOK_DIR / ".obsidian").is_dir(),
    }


# ---------------------------------------------------------------------------
# Read Operations
# ---------------------------------------------------------------------------


def read_page(page_path: str) -> dict:
    """Read a wiki page by relative path (e.g., 'entities/quarterback.md')."""
    full = PLAYBOOK_WIKI_DIR / page_path
    if not full.exists():
        return {"exists": False, "path": page_path}
    return {
        "exists": True,
        "path": page_path,
        "content": full.read_text(),
        "last_modified": datetime.fromtimestamp(full.stat().st_mtime).isoformat(),
    }


def read_index() -> str:
    """Read wiki/index.md content."""
    idx = PLAYBOOK_WIKI_DIR / "index.md"
    return idx.read_text() if idx.exists() else ""


def read_log() -> str:
    """Read wiki/log.md content."""
    log = PLAYBOOK_WIKI_DIR / "log.md"
    return log.read_text() if log.exists() else ""


def list_pages(category: str | None = None) -> list[dict]:
    """List all pages, optionally filtered by category."""
    pages = []
    cats = [category] if category and category in CATEGORIES else list(CATEGORIES)
    for cat in cats:
        cat_dir = PLAYBOOK_WIKI_DIR / cat
        if not cat_dir.is_dir():
            continue
        for f in sorted(cat_dir.glob("*.md")):
            pages.append(
                {
                    "path": f"{cat}/{f.name}",
                    "name": f.stem.replace("-", " ").title(),
                    "category": cat,
                    "last_modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
            )
    return pages


def search_pages(query: str, category: str | None = None) -> list[dict]:
    """Case-insensitive full-text search across wiki pages."""
    results = []
    q = query.lower()
    cats = [category] if category and category in CATEGORIES else list(CATEGORIES)
    for cat in cats:
        cat_dir = PLAYBOOK_WIKI_DIR / cat
        if not cat_dir.is_dir():
            continue
        for f in sorted(cat_dir.glob("*.md")):
            content = f.read_text()
            if q not in content.lower():
                continue
            matches = [line.strip() for line in content.splitlines() if q in line.lower()]
            results.append(
                {
                    "path": f"{cat}/{f.name}",
                    "name": f.stem.replace("-", " ").title(),
                    "category": cat,
                    "matches": matches[:5],
                }
            )
    return results


def read_compiled_goals() -> str | None:
    """Read compiled/goals.md if it exists."""
    p = PLAYBOOK_COMPILED_DIR / "goals.md"
    return p.read_text() if p.exists() else None


def read_compiled_constraints() -> str | None:
    """Read compiled/constraints.md if it exists."""
    p = PLAYBOOK_COMPILED_DIR / "constraints.md"
    return p.read_text() if p.exists() else None


# ---------------------------------------------------------------------------
# Write Operations
# ---------------------------------------------------------------------------


def write_page(
    page_path: str,
    content: str,
    log_entry: str | None = None,
) -> dict:
    """Write or update a wiki page. Auto-appends to log.md if log_entry given."""
    full = PLAYBOOK_WIKI_DIR / page_path
    full.parent.mkdir(parents=True, exist_ok=True)
    created = not full.exists()
    full.write_text(content)

    if log_entry:
        append_log(log_entry)

    return {
        "success": True,
        "path": page_path,
        "action": "created" if created else "updated",
    }


def append_log(entry: str) -> None:
    """Append a timestamped entry to wiki/log.md."""
    log = PLAYBOOK_WIKI_DIR / "log.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(f"\n- **{ts}**: {entry}\n")


# ---------------------------------------------------------------------------
# Initialization & Seeding
# ---------------------------------------------------------------------------


def initialize_playbook(
    playbook_path: Path | None = None,
    seed_data: dict | None = None,
) -> dict:
    """Create Playbook directory structure and seed initial pages."""
    pb = playbook_path or PLAYBOOK_DIR
    pages_created: list[str] = []

    # Create directories
    for d in [
        pb,
        pb / "raw",
        pb / "wiki",
        pb / "wiki" / "entities",
        pb / "wiki" / "concepts",
        pb / "wiki" / "decisions",
        pb / "wiki" / "compiled",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # Write CLAUDE.md schema (only if not exists — never overwrite user's schema)
    schema_path = pb / "CLAUDE.md"
    if not schema_path.exists():
        schema = generate_schema_md(str(pb))
        schema_path.write_text(schema)
        pages_created.append("CLAUDE.md")

    # Seed from interview data if provided
    entity_entries = []
    concept_entries = []
    decision_entries = []

    if seed_data:
        # Create entity pages from interview answers
        for ent in seed_data.get("entities", []):
            name = ent.get("name", "")
            if not name:
                continue
            slug = _slugify(name)
            path = pb / "wiki" / "entities" / f"{slug}.md"
            if not path.exists():
                content = seed_entity_page(
                    name=name,
                    description=ent.get("description", ""),
                    current_state=ent.get("current_state", ""),
                )
                path.write_text(content)
                pages_created.append(f"entities/{slug}.md")
            entity_entries.append(f"- [[{name}]] — {ent.get('description', '')[:80]}")

        # Create concept pages (skip existing)
        for con in seed_data.get("concepts", []):
            name = con.get("name", "")
            if not name:
                continue
            slug = _slugify(name)
            path = pb / "wiki" / "concepts" / f"{slug}.md"
            if not path.exists():
                content = seed_concept_page(
                    name=name,
                    summary=con.get("summary", ""),
                )
                path.write_text(content)
                pages_created.append(f"concepts/{slug}.md")
            concept_entries.append(f"- [[{name}]] — {con.get('summary', '')[:80]}")

        # Create decision pages (skip existing)
        for dec in seed_data.get("decisions", []):
            name = dec.get("name", "")
            if not name:
                continue
            slug = _slugify(name)
            path = pb / "wiki" / "decisions" / f"{slug}.md"
            if not path.exists():
                content = seed_decision_page(
                    name=name,
                    context=dec.get("context", ""),
                    decision=dec.get("decision", ""),
                )
                path.write_text(content)
                pages_created.append(f"decisions/{slug}.md")
            decision_entries.append(f"- [[Decision - {name}]]")

        # Auto-generate entity pages from projects if provided
        for proj in seed_data.get("projects", []):
            if isinstance(proj, dict):
                name = proj.get("name", "")
                desc = proj.get("description", "")
            elif isinstance(proj, str):
                name, desc = proj, ""
            else:
                continue
            if not name:
                continue
            slug = _slugify(name)
            path = pb / "wiki" / "entities" / f"{slug}.md"
            if not path.exists():
                content = seed_entity_page(name=name, description=desc)
                path.write_text(content)
                pages_created.append(f"entities/{slug}.md")
                entity_entries.append(f"- [[{name}]] — {desc[:80]}")

        # Generate compiled files from org answers
        if seed_data.get("goals") or seed_data.get("organization"):
            compiled_goals = seed_compiled_goals(seed_data)
            (pb / "wiki" / "compiled" / "goals.md").write_text(compiled_goals)
            pages_created.append("compiled/goals.md")

        if seed_data.get("constraints"):
            compiled_constraints = seed_compiled_constraints(seed_data)
            (pb / "wiki" / "compiled" / "constraints.md").write_text(compiled_constraints)
            pages_created.append("compiled/constraints.md")

        # Obsidian vault stub
        if seed_data.get("obsidian"):
            obs_dir = pb / ".obsidian"
            obs_dir.mkdir(exist_ok=True)
            (obs_dir / "app.json").write_text(
                '{\n  "showLineNumber": true,\n  "strictLineBreaks": true\n}\n'
            )

    # Write index.md (only if not exists — never overwrite user's index)
    index_path = pb / "wiki" / "index.md"
    if not index_path.exists():
        org_name = ""
        if seed_data and seed_data.get("organization"):
            org_name = seed_data["organization"].get("name", "")
        index = seed_index_md(entity_entries, concept_entries, decision_entries, org_name)
        index_path.write_text(index)
        pages_created.append("index.md")

    # Write initial log.md (only if not exists — never overwrite user's log)
    log_path = pb / "wiki" / "log.md"
    if not log_path.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        log_content = f"""Last updated: {today}

# Playbook Operations Log

Append-only record of all wiki changes.

---

## {today} — Playbook initialized

**Pages created**: {len(pages_created)}
{chr(10).join(f"- {p}" for p in pages_created)}

---
"""
        log_path.write_text(log_content)
        pages_created.append("log.md")
    else:
        # Append to existing log
        append_log(f"Playbook re-initialized. {len(pages_created)} pages created/updated.")

    return {
        "success": True,
        "path": str(pb),
        "pages_created": pages_created,
        "message": f"Playbook initialized with {len(pages_created)} pages at {pb}",
    }


# ---------------------------------------------------------------------------
# Page Templates
# ---------------------------------------------------------------------------


def seed_entity_page(
    name: str,
    description: str = "",
    current_state: str = "",
    relationships: list[str] | None = None,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    rels = ""
    if relationships:
        rels = "\n".join(f"- [[{r}]]" for r in relationships)
    return f"""Last updated: {today}

# {name}

## What it is
{description or "TODO: Add description."}

## Current state
{current_state or "TODO: Add current state."}

## Key relationships
{rels or "TODO: Add related entities, concepts, decisions."}

## History
- {today}: Page created during Playbook initialization
"""


def seed_concept_page(
    name: str,
    summary: str = "",
    how_it_works: str = "",
    where_applies: str = "",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""Last updated: {today}

# {name}

## Summary
{summary or "TODO: Add summary."}

## How it works
{how_it_works or "TODO: Add details."}

## Where it applies
{where_applies or "TODO: Add projects/workflows that use this concept."}

## Related
TODO: Add links to entities and decisions.
"""


def seed_decision_page(
    name: str,
    context: str = "",
    decision: str = "",
    alternatives: str = "",
    consequences: str = "",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""Last updated: {today}

# Decision: {name}
Date: {today}

## Context
{context or "TODO: Add what prompted this decision."}

## Decision
{decision or "TODO: Add what was decided."}

## Alternatives considered
{alternatives or "TODO: Add what else was evaluated."}

## Consequences
{consequences or "TODO: Add what changed as a result."}

## Related
TODO: Add links to affected entities and concepts.
"""


def seed_index_md(
    entities: list[str],
    concepts: list[str],
    decisions: list[str],
    org_name: str = "",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    header = f"for {org_name} " if org_name else ""
    ent_section = "\n".join(entities) if entities else "No entities yet."
    con_section = "\n".join(concepts) if concepts else "No concepts yet."
    dec_section = "\n".join(decisions) if decisions else "No decisions yet."

    return f"""Last updated: {today}

# Playbook Index

Master catalog of all compiled knowledge {header}— read this first for orientation.

## Entities

{ent_section}

## Concepts

{con_section}

## Decisions

{dec_section}

## Compiled (QB Sync)

These files are auto-maintained and read by Quarterback for task scoring:
- `compiled/goals.md` — Strategic goals, mission, anti-goals
- `compiled/constraints.md` — Budget, time, resource constraints

## Log

See [[log]] for append-only record of all wiki operations.
"""


def seed_compiled_goals(answers: dict) -> str:
    """Generate compiled/goals.md from setup wizard answers."""
    today = datetime.now().strftime("%Y-%m-%d")
    org = answers.get("organization", {})
    goals = answers.get("goals", {})
    projects = answers.get("projects", [])

    mission = org.get("mission", "TODO: Add mission.")
    vision = org.get("vision", "")
    annual = goals.get("annual", [])
    quarterly = goals.get("quarterly", [])
    anti_goals = goals.get("anti_goals", [])

    lines = [
        "# Organizational Goals\n",
        f"> Auto-generated by Playbook. Last synced: {today}\n",
        "## Mission",
        f"- {mission}\n",
    ]

    if vision:
        lines += ["## Vision", f"- {vision}\n"]

    if annual:
        lines += ["## Strategic Goals\n", "### Annual Goals"]
        lines += [f"- {g}" for g in annual]
        lines.append("")

    if quarterly:
        lines += ["### Quarterly Goals"]
        lines += [f"- {g}" for g in quarterly]
        lines.append("")

    if projects:
        lines += ["## Project Goals"]
        for p in projects:
            if isinstance(p, dict):
                name = p.get("name", "")
                milestone = p.get("next_milestone", "")
                if name:
                    lines.append(f"\n### {name}")
                    if milestone:
                        lines.append(f"- Next milestone: {milestone}")
            elif isinstance(p, str):
                lines.append(f"- {p}")
        lines.append("")

    if anti_goals:
        lines += ["## Anti-Goals"]
        lines += [f"- {g}" for g in anti_goals]
        lines.append("")

    return "\n".join(lines)


def seed_compiled_constraints(answers: dict) -> str:
    """Generate compiled/constraints.md from setup wizard answers."""
    today = datetime.now().strftime("%Y-%m-%d")
    c = answers.get("constraints", {})

    hours = c.get("hours_per_week", 40)
    working_hours = c.get("working_hours", "9am-6pm")
    working_days = c.get("working_days", "Monday-Friday")
    budget = c.get("budget_monthly")
    team_size = c.get("team_size", 1)
    preferred = c.get("preferred_stack", [])
    avoid = c.get("avoid_stack", [])

    lines = [
        "# Resource Constraints & Strategic Boundaries\n",
        f"> Auto-generated by Playbook. Last synced: {today}\n",
        "## Time Constraints\n",
        "### Available Time",
        f"- Development time: ~{hours} hours/week",
        f"- Business hours: {working_days}, {working_hours}\n",
    ]

    lines += [
        "## Resource Constraints\n",
        "### Budget",
    ]
    if budget:
        lines.append(f"- Monthly budget: ${budget}")
    else:
        lines.append("- Budget: Not specified")

    lines += [
        "\n### Technical Resources",
        f"- Team size: {team_size}",
    ]
    if preferred:
        lines.append(f"- Preferred stack: {', '.join(preferred)}")
    if avoid:
        lines.append(f"- Avoid: {', '.join(avoid)}")

    lines += [
        "\n## Strategic Boundaries\n",
        "### Conflict Resolution Guidelines\n",
        "When priorities conflict:",
        "1. Revenue-generating work trumps experimental projects",
        "2. Unblocking other projects takes priority",
        "3. Quick wins (< 4 hours) can interrupt planned work",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLAUDE.md Schema Template
# ---------------------------------------------------------------------------


def generate_schema_md(playbook_path: str = "") -> str:
    path_display = playbook_path or str(PLAYBOOK_DIR)
    return f"""# Playbook — Quarterback Knowledge Base

Playbook is the compiled knowledge layer for Quarterback. It follows the LLM wiki
pattern: Claude reads and writes structured markdown pages that accumulate knowledge
across sessions, ensuring all sessions and agents operate from the same canonical context.

## Architecture

```
{path_display}/
├── CLAUDE.md          # This file — schema and operating rules
├── raw/               # Immutable source material (dropped in by human)
├── wiki/
│   ├── index.md       # Master catalog of all wiki pages
│   ├── entities/      # People, companies, products, clients, tools
│   ├── concepts/      # Patterns, strategies, recurring themes
│   ├── decisions/     # Architectural and business decisions with rationale
│   ├── compiled/      # QB-compatible files read by Quarterback for scoring
│   │   ├── goals.md   # Strategic goals, anti-goals
│   │   └── constraints.md  # Budget, time, resources
│   └── log.md         # Append-only record of all wiki operations
└── .obsidian/         # Obsidian vault config (optional)
```

## Rules

### Reading
- Always read `wiki/index.md` first to understand what's available
- Follow links to relevant pages before generating output
- Prefer wiki content over re-deriving from QB tasks or memory files
- If wiki content conflicts with current code/QB state, trust current state and update the wiki

### Writing
- Only write to `wiki/` — never modify files in `raw/`
- Every write operation must append to `wiki/log.md`
- Use Obsidian-style `[[wikilinks]]` for cross-references between pages
- Keep pages focused: one entity, one concept, or one decision per page
- Include a `Last updated: YYYY-MM-DD` line at the top of every page

### Page Format

**Entity pages** (`wiki/entities/`):
```markdown
Last updated: YYYY-MM-DD

# Entity Name

## What it is
One-paragraph description.

## Current state
What's true right now.

## Key relationships
Links to related entities, concepts, decisions.

## History
Significant events in reverse chronological order.
```

**Concept pages** (`wiki/concepts/`):
```markdown
Last updated: YYYY-MM-DD

# Concept Name

## Summary
What this concept is and why it matters.

## How it works
Practical details.

## Where it applies
Projects, agents, or workflows that use this concept.

## Related
Links to entities and decisions.
```

**Decision pages** (`wiki/decisions/`):
```markdown
Last updated: YYYY-MM-DD

# Decision: [Title]
Date: YYYY-MM-DD

## Context
What prompted this decision.

## Decision
What was decided.

## Alternatives considered
What else was evaluated and why it was rejected.

## Consequences
What changed as a result.

## Related
Links to affected entities and concepts.
```

## QB Sync (compiled/)

Files in `wiki/compiled/` are read directly by Quarterback for task scoring and
conflict detection. These files use QB-compatible markdown format with keyword-based
section headers.

**Format requirements** (QB's parser looks for these keywords in headers):
- goals.md: "strategic", "workflow", "project", "anti-goal" (case-insensitive)
- constraints.md: "time", "budget", "tech", "strategic" (case-insensitive)
- List items must use `-` or `*` prefix

## Obsidian Integration

This directory can be opened as an Obsidian vault for visual browsing and graph view.
Install an Obsidian MCP server (e.g., `obsidian-claude-code-mcp`) for programmatic
access from Claude Code sessions. All cross-references use `[[wikilinks]]` which
render as clickable links in Obsidian.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")
