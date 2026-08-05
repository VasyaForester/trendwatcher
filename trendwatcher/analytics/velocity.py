"""Расчёт относительной динамики (pct_change) для сигналов.

Основная метрика UI — изменение доли тега среди всех отслеживаемых
signal-упоминаний за 90 дней к предыдущим 90 дням.
"""

MAX_VELOCITY = 3.0  # ±300% в UI


def pct_change(current: float, prior: float) -> float | None:
    """Дробное изменение: 0.5 = +50%. None, если prior ≤ 0."""
    if prior <= 0:
        return None
    return (current - prior) / prior


def cap_velocity(value: float | None, max_abs: float = MAX_VELOCITY) -> float:
    if value is None:
        return 0.0
    return round(max(-max_abs, min(max_abs, value)), 3)


def velocity_from_counts(
    recent: int,
    prior: int,
    *,
    max_abs: float = MAX_VELOCITY,
) -> tuple[float, str | None]:
    """Velocity по абсолютным счётчикам 90д/90д."""
    change = pct_change(float(recent), float(prior))
    if change is None:
        return 0.0, None
    return cap_velocity(change, max_abs), "counts_90d"


def velocity_from_shares(
    recent_share: float | None,
    prior_share: float | None,
    *,
    max_abs: float = MAX_VELOCITY,
) -> tuple[float, str | None]:
    """Velocity по долям в выбранном сопоставимом знаменателе."""
    if recent_share is not None and prior_share is not None and prior_share > 0:
        return cap_velocity(pct_change(recent_share, prior_share), max_abs), "share_90d"
    return 0.0, None


def velocity_label(velocity: float, source: str | None) -> str:
    if not source:
        return "н/д"
    pct = round(velocity * 100)
    sign = "+" if velocity > 0 else ""
    if source in {"share_90d", "archive", "baseline"}:
        return f"{sign}{pct}% доли"
    if source == "counts_90d":
        return f"{sign}{pct}% сообщений"
    return f"{sign}{pct}%"

