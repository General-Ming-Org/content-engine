"""Opinion-mining research config — edit here to tune lane, queries, and search quality.

RELEVANCE (what the post is about) lives in MY_FOCUS_AREAS + the relevance gate.
OPINION-RICHNESS (where arguments live) lives in SOURCE_PREFERENCES — the main quality dial.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID
# ── A) Lane definition ────────────────────────────────────────────────────────
# Single place to define your field. Downstream gates and query templating derive from this.

MY_FOCUS_AREAS: list[str] = [
    "RAG and retrieval systems",
    "LLM inference infra",
    "agent orchestration",
    "MLOps",
    "applied LLM product engineering",
]

# ── B) Opinion-source query templates (vendor-agnostic) ───────────────────────
# Resolved into OPINION_SOURCE_QUERIES via build_opinion_source_queries().
# Short, natural-language shapes aimed at arguments — not docs or changelogs.

OPINION_QUERY_TEMPLATES: list[str] = [
    "unpopular opinion {focus_area}",
    "why teams regret {approach} in {focus_area}",
    "{focus_area} overrated underrated",
    "lessons learned {focus_area} postmortem",
    "{focus_area} debate hot take",
]

# Fills the {approach} slot — generic regrets, no product names.
REGRET_APPROACHES: list[str] = [
    "building everything in-house",
    "outsourcing too early",
    "standardizing on one stack",
]

# ── C) Where practitioners argue (opinion-richness axis) ──────────────────────
# Tavily include_domains / exclude_domains. Tune this list to bias toward venues
# with takes and away from docs, changelogs, and SEO farms.
# This filter is about WHERE arguments live, not WHAT they are about.

SOURCE_PREFERENCES: dict[str, list[str]] = {
    "include_domains": [
        "news.ycombinator.com",
        "reddit.com",
        "lobste.rs",
        "dev.to",
        "substack.com",
    ],
    "exclude_domains": [
        "docs.aws.amazon.com",
        "cloud.google.com",
        "learn.microsoft.com",
        "kubernetes.io",
        "pytorch.org",
        "huggingface.co",
        "arxiv.org",
    ],
}

# ── G) Tavily call tuning ─────────────────────────────────────────────────────
# Recency window, result volume, and depth. searcher.py reads these directly.

TAVILY_SEARCH_CONFIG: dict[str, int | str] = {
    "days": 10,  # last 7–14 days — tighten for hotter takes, widen if sparse
    "max_results": 5,  # per query — keep modest; opinion signal dilutes with volume
    "search_depth": "advanced",
}

# How many resolved queries to run per sweep (rotates through the full list).
SWEEP_QUERIES_PER_RUN: int = 9

# Max stance topics to persist after gates (LLM cost control).
SWEEP_MAX_STANCES: int = 3

# ── E) Debatability gate threshold ──────────────────────────────────────────
# Stances below this score are dropped. If none survive, the day is skipped — no fallback post.
# Scale: 1–10 from stance extraction.

DEBATABILITY_MIN_SCORE: float = 6.0

# Maps focus_area strings to the legacy domain enum for Postgres compatibility.
FOCUS_AREA_TO_DOMAIN: dict[str, str] = {
    "RAG and retrieval systems": "data_eng",
    "LLM inference infra": "sre_infra",
    "agent orchestration": "ai_ml",
    "MLOps": "data_eng",
    "applied LLM product engineering": "software_eng",
}

_query_rotation_offset: int = 0


def build_opinion_source_queries() -> list[str]:
    """Resolve templates into ~8–10 vendor-agnostic opinion queries."""
    resolved: list[str] = []
    for focus in MY_FOCUS_AREAS:
        for template in OPINION_QUERY_TEMPLATES:
            if "{approach}" in template:
                for approach in REGRET_APPROACHES[:1]:
                    resolved.append(
                        template.format(focus_area=focus, approach=approach)
                    )
            else:
                resolved.append(template.format(focus_area=focus))
    return resolved[:10]


def get_sweep_queries(user_id: UUID | None = None) -> list[str]:
    """Rotate a window of queries so each sweep covers the lane without running all every time."""
    all_queries = build_opinion_source_queries()
    if not all_queries:
        return []
    count = min(SWEEP_QUERIES_PER_RUN, len(all_queries))
    if user_id is not None:
        day = datetime.now(timezone.utc).date().isoformat()
        seed = int(hashlib.md5(f"{user_id}:{day}".encode()).hexdigest(), 16)
        start = seed % len(all_queries)
    else:
        global _query_rotation_offset
        start = _query_rotation_offset % len(all_queries)
        _query_rotation_offset = (start + count) % len(all_queries)
    return [all_queries[(start + i) % len(all_queries)] for i in range(count)]

def focus_area_to_domain(focus_area: str) -> str:
    return FOCUS_AREA_TO_DOMAIN.get(focus_area, "ai_ml")
