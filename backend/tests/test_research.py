"""Research service unit tests.

Dedup moved to Qdrant (semantic) — `_ngram_similarity` is the no-API fallback used
when the vector store is unreachable. These tests cover that fallback.
"""
import pytest

from services.research.scorer import _compute_score, _ngram_similarity
from services.research.searcher import _next_query


def test_ngram_similarity_identical():
    assert _ngram_similarity("machine learning inference", "machine learning inference") == 1.0


def test_ngram_similarity_different():
    sim = _ngram_similarity("kubernetes networking", "python async generators")
    assert sim < 0.2


def test_ngram_similarity_partial():
    sim = _ngram_similarity("kubernetes networking eBPF", "kubernetes networking cilium")
    assert sim > 0.5


def test_compute_score_high_quality():
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
    score = _compute_score(enriched)
    assert score >= 0.8


def test_compute_score_low_quality():
    enriched = {
        "title": "Test",
        "summary": "Vague",
        "domain": "ai_ml",
        "synthesis": {
            "confidence": 3,
            "key_facts": [],
            "trade_offs": "",
        },
    }
    score = _compute_score(enriched)
    assert score < 0.6


def test_query_rotation():
    """Verify queries rotate across multiple calls."""
    first = _next_query("ai_ml")
    second = _next_query("ai_ml")
    assert first != second  # Queries rotate


@pytest.mark.asyncio
async def test_research_sweep_mocked(mock_tavily):
    """Full sweep with mocked external calls should complete without error."""
    from unittest.mock import AsyncMock, patch

    enriched = {
        "title": "Test Article: eBPF in Production",
        "summary": "Test summary",
        "sources": [],
        "domain": "sre_infra",
        "synthesis": {
            "confidence": 8,
            "key_facts": ["fact 1"],
            "trade_offs": "trade-off",
        },
        "from_cache": False,
    }

    with patch(
        "services.research.dedupe.archive_duplicate_topics",
        new_callable=AsyncMock,
        return_value=0,
    ):
        with patch("services.research.deep_dive.enrich_topic", new_callable=AsyncMock, return_value=enriched):
            with patch("services.research.scorer.score_and_store") as mock_store:
                mock_store.return_value = None
                from services.research.searcher import sweep

                result = await sweep()
                assert result["status"] == "complete"
                assert result["results_stored"] >= 0
                assert result["results_skipped"] >= 0
                assert result["results_found"] == result["results_stored"] + result["results_skipped"]
