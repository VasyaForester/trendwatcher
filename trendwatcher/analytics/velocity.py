"""Расчёт относительной динамики (pct_change) для сигналов.

Используем долю тега в корпусе, не абсолютные счётчики — иначе при prior=1
получается +1000%. При prior=0 возвращаем None → в UI 0%, не бесконечность.
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


def velocity_from_shares(
    recent_share: float | None,
    prior_share: float | None,
    *,
    max_abs: float = MAX_VELOCITY,
) -> tuple[float, str | None]:
    """Velocity только по долям. Возвращает (velocity, source_label)."""
    if recent_share is not None and prior_share is not None and prior_share > 0:
        return cap_velocity(pct_change(recent_share, prior_share), max_abs), "archive"
    return 0.0, None


def velocity_label(velocity: float, source: str | None) -> str:
    pct = round(velocity * 100)
    sign = "+" if velocity > 0 else ""
    if source:
        return f"{sign}{pct}% доля"
    return f"{sign}{pct}% (мало данных)"
