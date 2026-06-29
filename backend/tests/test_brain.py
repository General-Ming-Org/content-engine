"""Tests for Research Brain service."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.brain.queries import build_linkedin_queries, focus_area_to_domain
from services.content.tone import DEFAULT_TONE, tone_system_constraints, validate_hashtags


def test_build_linkedin_queries():
    queries = build_linkedin_queries(["RAG and retrieval systems"])
    assert len(queries) >= 3
    assert any("linkedin" in q.lower() for q in queries)


def test_focus_area_to_domain():
    assert focus_area_to_domain("MLOps") == "data_eng"


def test_tone_system_constraints():
    text = tone_system_constraints({"emoji_max": 1, "hashtag_min": 2, "hashtag_max": 4})
    assert "0-1 emojis" in text
    assert "2-4 hashtags" in text


def test_validate_hashtags():
    content = "Hello world " + "#tag1 #tag2"
    issues = validate_hashtags(content, DEFAULT_TONE)
    assert any("Too few hashtags" in i for i in issues)


@pytest.mark.asyncio
async def test_novelty_gate_returns_structure():
    from services.brain.novelty_gate import check_novelty

    with patch("services.brain.novelty_gate.get_vector_store") as mock_store:
        mock_store.return_value.search = AsyncMock(return_value=[])
        with patch("services.ai.claude_client.generate_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "novelty_score": 8,
                "value_additions": ["specific angle"],
                "suggested_angle": "",
            }
            result = await check_novelty(
                uuid.uuid4(),
                "RAG is overrated for most products",
                "Most teams don't need RAG. They need better retrieval hygiene." * 20,
                "data_eng",
            )
    assert "warnings" in result
    assert result["metadata"]["novelty_score"] == 8
