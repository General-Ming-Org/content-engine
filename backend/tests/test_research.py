"""Research service unit tests — opinion-mining pipeline."""
import pytest

from services.research.queries import (
    DEBATABILITY_MIN_SCORE,
    MY_FOCUS_AREAS,
    SOURCE_PREFERENCES,
    TAVILY_SEARCH_CONFIG,
    build_opinion_source_queries,
    get_sweep_queries,
)
from services.research.scorer import _compute_score, _ngram_similarity
from services.research.stance_gates import apply_stance_gates, passes_relevance_gate
from services.research.searcher import _dedupe_results, _tavily_params


def test_focus_areas_seeded():
    assert len(MY_FOCUS_AREAS) >= 3
    assert "RAG and retrieval systems" in MY_FOCUS_AREAS


def test_opinion_queries_vendor_agnostic():
    queries = build_opinion_source_queries()
    assert 8 <= len(queries) <= 10
    joined = " ".join(queries).lower()
    assert "vllm" not in joined
    assert "production" not in joined
    assert "unpopular opinion" in joined


def test_sweep_query_rotation():
    first = get_sweep_queries()
    second = get_sweep_queries()
    assert len(first) >= 1
    assert first != second or len(build_opinion_source_queries()) <= len(first)


def test_tavily_params_surface_config():
    params = _tavily_params()
    assert params["days"] == TAVILY_SEARCH_CONFIG["days"]
    assert params["max_results"] == TAVILY_SEARCH_CONFIG["max_results"]
    assert params["include_domains"] == SOURCE_PREFERENCES["include_domains"]
    assert params["exclude_domains"] == SOURCE_PREFERENCES["exclude_domains"]


def test_ngram_similarity_identical():
    assert _ngram_similarity("machine learning inference", "machine learning inference") == 1.0


def test_ngram_similarity_different():
    sim = _ngram_similarity("kubernetes networking", "python async generators")
    assert sim < 0.2


def test_relevance_gate_accepts_lane_match():
    stance = {
        "thesis": "RAG chunking is overrated",
        "focus_area": "RAG and retrieval systems",
        "debatability_score": 8,
    }
    assert passes_relevance_gate(stance)


def test_relevance_gate_rejects_out_of_lane():
    stance = {
        "thesis": "Kubernetes ingress controllers are all the same",
        "focus_area": "kubernetes networking",
        "debatability_score": 9,
    }
    assert not passes_relevance_gate(stance)


def test_debatability_gate_skips_bland():
    stances = [
        {
            "thesis": "Spicy take",
            "focus_area": MY_FOCUS_AREAS[0],
            "debatability_score": DEBATABILITY_MIN_SCORE - 1,
        },
        {
            "thesis": "Sharper take",
            "focus_area": MY_FOCUS_AREAS[0],
            "debatability_score": DEBATABILITY_MIN_SCORE + 1,
        },
    ]
    surviving = apply_stance_gates(stances)
    assert len(surviving) == 1
    assert surviving[0]["thesis"] == "Sharper take"


def test_apply_stance_gates_empty_when_all_rejected():
    stances = [
        {"thesis": "x", "focus_area": "totally unrelated field", "debatability_score": 10},
    ]
    assert apply_stance_gates(stances) == []


def test_dedupe_results_by_url():
    results = [
        {"url": "https://example.com/a", "title": "A"},
        {"url": "https://example.com/a", "title": "A duplicate"},
        {"url": "https://example.com/b", "title": "B"},
    ]
    assert len(_dedupe_results(results)) == 2


def test_compute_score_legacy_synthesis():
    enriched = {
        "title": "Test",
        "summary": "Test summary",
        "domain": "sre_infra",
        "synthesis": {
            "confidence": 9,
            "key_facts": ["fact1", "fact2", "fact3", "fact4", "fact5"],
            "trade_offs": "Real trade-off here",
        },
    }
    assert _compute_score(enriched) >= 0.8


@pytest.mark.asyncio
async def test_opinion_sweep_skips_when_no_stances(mock_tavily):
    from unittest.mock import AsyncMock, patch

    with patch(
        "services.research.dedupe.archive_duplicate_topics",
        new_callable=AsyncMock,
        return_value=0,
    ):
        with patch(
            "services.research.stance_extractor.extract_stances_from_results",
            new_callable=AsyncMock,
            return_value=[],
        ):
            from services.research.searcher import sweep

            result = await sweep()
            assert result["status"] == "complete"
            assert result["results_stored"] == 0
            assert result["skip_reasons"].get("no_debatable_stances") == 1


@pytest.mark.asyncio
async def test_opinion_sweep_stores_gated_stance(mock_tavily):
    from unittest.mock import AsyncMock, MagicMock, patch

    stance = {
        "thesis": "Most RAG pipelines over-index on chunk size",
        "anti_position": "bigger chunks are always better",
        "evidence": "teams keep shrinking chunks after eval failures",
        "source_url": "https://news.ycombinator.com/item?id=1",
        "topic": "RAG chunking",
        "focus_area": MY_FOCUS_AREAS[0],
        "debatability_score": 8,
        "attribution": "",
    }

    with patch(
        "services.research.dedupe.archive_duplicate_topics",
        new_callable=AsyncMock,
        return_value=0,
    ):
        with patch(
            "services.research.stance_extractor.extract_stances_from_results",
            new_callable=AsyncMock,
            return_value=[stance],
        ):
            with patch("services.research.scorer.store_stance") as mock_store:
                mock_store.return_value = MagicMock()
                from services.research.searcher import sweep

                result = await sweep()
                assert result["status"] == "complete"
                assert result["results_stored"] == 1
                mock_store.assert_called_once()
