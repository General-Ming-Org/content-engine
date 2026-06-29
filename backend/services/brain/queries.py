"""LinkedIn signal harvest query templates and Tavily config."""

from __future__ import annotations

from services.research.queries import FOCUS_AREA_TO_DOMAIN, MY_FOCUS_AREAS

LINKEDIN_SIGNAL_TEMPLATES: list[str] = [
    "site:linkedin.com {focus_area} viral post",
    "linkedin.com post {focus_area} reactions comments",
    "{focus_area} linkedin hot take engineer",
]

LINKEDIN_TAVILY_CONFIG: dict[str, int | str | list[str]] = {
    "days": 14,
    "max_results": 5,
    "search_depth": "advanced",
    "include_domains": ["linkedin.com", "www.linkedin.com"],
}

HARVEST_QUERIES_PER_RUN: int = 6
HARVEST_MAX_STORE: int = 5
RAW_CONTENT_FETCH_LIMIT: int = 3
TRACTION_MIN_SCORE: float = 0.5


def default_focus_areas() -> list[str]:
    return list(MY_FOCUS_AREAS)


def build_linkedin_queries(focus_areas: list[str] | None = None) -> list[str]:
    areas = focus_areas or default_focus_areas()
    resolved: list[str] = []
    for focus in areas:
        for template in LINKEDIN_SIGNAL_TEMPLATES:
            resolved.append(template.format(focus_area=focus))
    return resolved[:10]


_query_rotation_offset: int = 0


def get_harvest_queries(focus_areas: list[str] | None = None) -> list[str]:
    global _query_rotation_offset
    all_queries = build_linkedin_queries(focus_areas)
    if not all_queries:
        return []
    count = min(HARVEST_QUERIES_PER_RUN, len(all_queries))
    start = _query_rotation_offset % len(all_queries)
    selected = [all_queries[(start + i) % len(all_queries)] for i in range(count)]
    _query_rotation_offset = (start + count) % len(all_queries)
    return selected


def focus_area_to_domain(focus_area: str) -> str:
    return FOCUS_AREA_TO_DOMAIN.get(focus_area, "ai_ml")
