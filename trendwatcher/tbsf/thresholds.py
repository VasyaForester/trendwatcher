"""Пороги TBSF из rubric.yaml."""

from .config_loader import load_rubric

_cached: dict | None = None


def thresholds() -> dict[str, int]:
    global _cached
    if _cached is None:
        th = load_rubric().raw.get("thresholds", {})
        _cached = {
            "priority": int(th.get("priority", 75)),
            "reserve_min": int(th.get("reserve_min", 50)),
            "reject_max": int(th.get("reject_max", 49)),
        }
    return _cached


# Минимум TBSF для попадания research в ленту / топ (ниже reject — не показываем)
FEED_MIN = 42
# Целевой минимум для топ-событий (с fallback, см. scoring.top_events)
TOP_MIN_TARGET = thresholds()["reserve_min"]
