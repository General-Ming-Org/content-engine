"""
LinkedIn benchmark reference data for tech/professional content.

Sources:
- Socialinsider LinkedIn Benchmarks Report 2024 (tech industry segment)
- Hootsuite Social Media Trends 2024
- LinkedIn internal data published in their Engineering Blog, 2024

These are hardcoded initial values. Update quarterly by reviewing the sources above.
Last updated: 2025-01-01
"""
from typing import Any

LINKEDIN_BENCHMARKS: dict[str, Any] = {
    "last_updated": "2025-01-01",
    "sources": [
        "Socialinsider LinkedIn Benchmarks Report 2024",
        "Hootsuite Social Media Trends 2024",
    ],
    "tech_content": {
        "avg_engagement_rate_pct": 1.1,       # Likes + comments + shares / impressions
        "avg_comment_rate_pct": 0.35,         # Comments / impressions
        "avg_share_rate_pct": 0.18,           # Shares / impressions
        "avg_click_through_rate_pct": 2.4,    # Clicks / impressions (articles)
        "median_impressions_per_post": 1200,  # For accounts 1k-10k followers
        "top_quartile_impressions": 4500,     # Top 25% in tech
        "avg_follower_growth_per_month_pct": 2.5,  # Monthly follower growth rate
    },
    "substack": {
        "avg_open_rate_pct": 38.0,           # Industry avg for tech newsletters
        "top_quartile_open_rate_pct": 55.0,
        "avg_click_rate_pct": 4.2,
        "avg_subscriber_growth_per_month_pct": 3.5,
    },
    "notes": (
        "Engagement rate = (likes + comments + shares) / impressions * 100. "
        "These are averages — personal creator accounts in tech typically beat brand accounts. "
        "Accounts with strong personal brands see 2-5x these averages."
    ),
}


def compare_to_benchmark(my_metrics: dict[str, float]) -> dict[str, Any]:
    """Return a comparison dict of my metrics vs benchmarks."""
    bench = LINKEDIN_BENCHMARKS["tech_content"]
    comparisons = {}

    if "engagement_rate_pct" in my_metrics:
        my_val = my_metrics["engagement_rate_pct"]
        benchmark = bench["avg_engagement_rate_pct"]
        comparisons["engagement_rate"] = {
            "mine": round(my_val, 2),
            "benchmark": benchmark,
            "delta": round(my_val - benchmark, 2),
            "above_benchmark": my_val > benchmark,
        }

    if "impressions" in my_metrics:
        my_val = my_metrics["impressions"]
        benchmark = bench["median_impressions_per_post"]
        comparisons["impressions_per_post"] = {
            "mine": round(my_val),
            "benchmark": benchmark,
            "delta": round(my_val - benchmark),
            "above_benchmark": my_val > benchmark,
        }

    return comparisons
