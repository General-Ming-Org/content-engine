"""Analytics service unit tests."""
from datetime import date, timedelta

import pytest

from services.analytics.benchmarks import compare_to_benchmark, LINKEDIN_BENCHMARKS
from services.analytics.goals import calculate_projected_completion


def test_benchmark_data_valid():
    bench = LINKEDIN_BENCHMARKS["tech_content"]
    assert bench["avg_engagement_rate_pct"] > 0
    assert bench["median_impressions_per_post"] > 0


def test_compare_above_benchmark():
    result = compare_to_benchmark({"engagement_rate_pct": 3.5})
    assert result["engagement_rate"]["above_benchmark"] is True
    assert result["engagement_rate"]["delta"] > 0


def test_compare_below_benchmark():
    result = compare_to_benchmark({"engagement_rate_pct": 0.5})
    assert result["engagement_rate"]["above_benchmark"] is False


def test_goal_progress_pct():
    result = calculate_projected_completion(
        current_value=500,
        target_value=1000,
        target_date=date.today() + timedelta(days=90),
    )
    assert result["progress_pct"] == 50.0


def test_goal_achieved():
    result = calculate_projected_completion(
        current_value=1000,
        target_value=1000,
        target_date=date.today() + timedelta(days=30),
    )
    assert result["progress_pct"] == 100.0


def test_goal_projection():
    start = date.today() - timedelta(days=30)
    result = calculate_projected_completion(
        current_value=300,
        target_value=1000,
        target_date=date.today() + timedelta(days=180),
        start_value=0,
        start_date=start,
    )
    assert result["projected_date"] is not None
    assert result["days_remaining"] > 0
