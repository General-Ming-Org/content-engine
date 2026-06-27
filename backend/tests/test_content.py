"""Content generation unit tests."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.content.prompts import BANNED_PHRASES
from services.content.linkedin import _validate_post, generate_post

_MOCK_POST = (
    "The real cost of distributed tracing isn't the tooling — it's the cardinality explosion "
    "that hits you at 100 services.\n\nWe spent $40k/month on trace storage before switching "
    "to tail-based sampling. Three things that actually helped:\n\n1. Sample at the edge, "
    "not the collector\n2. Drop spans below 10ms unless they fail\n3. Aggregate by service "
    "pair, not individual trace IDs\n\nTail-based sampling with a 1% floor cut storage 85% "
    "while keeping all error traces.\n\nWhat sampling strategy are you running in prod?\n\n"
    "#Observability #SRE #DistributedSystems #OpenTelemetry"
)


def test_validate_post_too_short():
    issues = _validate_post("Short post. #tech #ai #ml")
    assert any("Too short" in i for i in issues)


def test_validate_post_banned_phrase():
    long_post = "X" * 1200 + "\n\nIn today's rapidly evolving landscape... #tech #ai #software #engineering #cloud"
    issues = _validate_post(long_post)
    assert any("rapidly evolving" in i for i in issues)


def test_validate_post_too_few_hashtags():
    post = "A" * 1300 + "\n#tech"
    issues = _validate_post(post)
    assert any("hashtags" in i.lower() for i in issues)


def test_validate_post_valid():
    # Construct a valid post
    content = "The real cost of distributed systems isn't the network — it's the cognitive load on the team maintaining it.\n\n"
    content += "We migrated from a monolith to microservices in 2022. Latency improved 40ms. Incident rate doubled.\n\n"
    content += "Three things we missed in our cost model:\n\n"
    content += "1. Each service needs its own deploy pipeline, runbook, and on-call rotation\n"
    content += "2. Cross-service tracing requires tooling investment that compounds over time\n"
    content += "3. The blast radius of a shared dependency failure is now unpredictable\n\n"
    content += "The latency win was real. The operational cost wasn't in our spreadsheet.\n\n"
    content += "What did your architecture migration cost that you didn't anticipate?\n\n"
    content += "#SoftwareEngineering #Microservices #SRE #DistributedSystems"
    # Pad to minimum length
    while len(content) < 1200:
        content = content.replace("#SoftwareEngineering", "#SoftwareEngineering #Architecture")

    issues = _validate_post(content)
    assert not any("Too short" in i or "Too long" in i for i in issues)


def test_banned_phrases_list_not_empty():
    assert len(BANNED_PHRASES) >= 10


@pytest.mark.asyncio
async def test_generate_post_mocked():
    """Post generation with mocked LLM should return structured output."""
    with patch("services.content.linkedin.generate", new_callable=AsyncMock, return_value=_MOCK_POST):
        result = await generate_post(
            user_id=uuid.uuid4(),
            title="Distributed Tracing Cost",
            domain="sre_infra",
            voice_style="analytical",
            key_facts=["tail-based sampling reduces cost 85%", "cardinality explosion at 100+ services"],
            why_it_matters="Engineers waste $40k/month on trace storage without proper sampling",
            trade_offs="Sampling always trades completeness for cost",
        )
    assert "content" in result
    assert "hashtags" in result
