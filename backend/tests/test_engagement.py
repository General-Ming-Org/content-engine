"""Engagement service unit tests."""
import pytest

from services.engagement.safety import should_skip_comment, validate_reply

GOOD_COMMENTS = [
    "We had the same cardinality issue with OpenTelemetry. Switched to exemplars-only for high-volume spans.",
    "Curious how you handled the migration from Prometheus to OpenMetrics — was the cardinality model different?",
    "The tail-based approach works but you need a buffer that can hold spans for 30+ seconds. How do you size that?",
]

BAD_COMMENTS = [
    "Follow me for more tips! https://bit.ly/spam",
    "Check out my crypto investment opportunity",
    "Trump is ruining the tech industry",
    "lol",
    "👍",
]


@pytest.mark.parametrize("comment", GOOD_COMMENTS)
def test_good_comments_not_skipped(comment):
    skip, _ = should_skip_comment(comment)
    assert skip is False, f"Good comment incorrectly skipped: {comment[:50]}"


@pytest.mark.parametrize("comment", BAD_COMMENTS)
def test_bad_comments_skipped(comment):
    skip, reason = should_skip_comment(comment)
    assert skip is True, f"Bad comment not skipped: {comment[:50]}"


def test_valid_reply():
    reply = (
        "The buffer sizing question is the hard part. We ended up with 30s retention "
        "and a 4GB heap per collector replica. The key insight: size for tail latency, "
        "not average. Your p99 service latency determines minimum buffer depth."
    )
    valid, _ = validate_reply(reply)
    assert valid is True


def test_reply_too_short():
    valid, reason = validate_reply("Yes exactly.")
    assert valid is False
    assert "too_short" in reason
