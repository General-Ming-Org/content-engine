"""Safety filters for engagement replies — block inappropriate reply targets."""
import re
from typing import Any

POLITICAL_KEYWORDS = {
    "democrat", "republican", "liberal", "conservative", "trump", "biden",
    "election", "vote", "abortion", "gun control", "immigration policy",
    "socialist", "fascist", "woke", "maga",
}

SPAM_PATTERNS = [
    r"https?://\S+",           # URLs in comments
    r"follow me",
    r"check out my",
    r"dm me",
    r"free \w+",
    r"\$\d+",                  # Dollar amounts
    r"crypto|bitcoin|nft",
    r"make money",
    r"earn from home",
]

INFLAMMATORY_PATTERNS = [
    r"\b(idiot|stupid|dumb|moron|loser|pathetic)\b",
    r"\b(hate|disgusting|trash|garbage)\b",
    r"you(\'re| are) wrong",  # Not inflammatory on its own, but combined with others
]

REPLY_ANTI_PATTERNS = [
    "thanks for sharing",
    "great point",
    "couldn't agree more",
    "well said",
    "so true",
    "absolutely",
    "exactly",
    "100%",
]


def should_skip_comment(comment: str) -> tuple[bool, str]:
    """Return (should_skip, reason). True = do not reply."""
    comment_lower = comment.lower()

    # Political content
    for keyword in POLITICAL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", comment_lower):
            return True, f"political_content: '{keyword}'"

    # Spam
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, comment_lower):
            return True, f"spam_pattern: '{pattern}'"

    # Highly inflammatory
    inflammatory_hits = sum(
        1 for p in INFLAMMATORY_PATTERNS if re.search(p, comment_lower)
    )
    if inflammatory_hits >= 2:
        return True, "inflammatory_comment"

    # Too short to reply meaningfully (single emoji, punctuation, etc.)
    if len(comment.strip()) < 10:
        return True, "too_short"

    return False, ""


def validate_reply(reply: str) -> tuple[bool, str]:
    """Return (is_valid, reason). False = do not post this reply."""
    reply_lower = reply.lower()

    for pattern in REPLY_ANTI_PATTERNS:
        if reply_lower.strip().startswith(pattern):
            return False, f"anti_pattern opener: '{pattern}'"

    if len(reply.split()) < 10:
        return False, f"reply_too_short: {len(reply.split())} words"

    if len(reply) > 1200:
        return False, f"reply_too_long: {len(reply)} chars"

    return True, ""
