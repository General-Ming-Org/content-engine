"""Goal progress calculation utilities."""
from datetime import date
from typing import Any


def calculate_projected_completion(
    current_value: float,
    target_value: float,
    target_date: date,
    start_value: float = 0.0,
    start_date: date | None = None,
) -> dict[str, Any]:
    """Calculate progress percentage and projected completion date."""
    if target_value == 0:
        return {"progress_pct": 100.0, "on_track": True, "projected_date": None}

    progress_pct = min(round(current_value / target_value * 100, 1), 100.0)
    today = date.today()
    days_remaining = (target_date - today).days

    if start_date and start_value < current_value:
        days_elapsed = max((today - start_date).days, 1)
        daily_rate = (current_value - start_value) / days_elapsed
        if daily_rate > 0:
            days_to_target = (target_value - current_value) / daily_rate
            from datetime import timedelta
            projected = today + timedelta(days=int(days_to_target))
            on_track = projected <= target_date
        else:
            projected = None
            on_track = False
    else:
        projected = None
        on_track = progress_pct >= (1 - days_remaining / max((target_date - (start_date or today)).days, 1)) * 100

    return {
        "progress_pct": progress_pct,
        "on_track": on_track,
        "projected_date": projected.isoformat() if projected else None,
        "days_remaining": days_remaining,
    }
