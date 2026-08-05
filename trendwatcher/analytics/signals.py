"""Классификация зрелости сигналов.

Уровни привязаны к сглаженной динамике числа публикаций за 90д vs пред. 90д:
- strong    — сильный рост + объём/корроборация;
- emerging  — заметный рост;
- research  — молодая тема пока в основном в исследованиях;
- spike     — разовый всплеск одной недели, не тренд;
- stable    — изменение около нуля;
- weak      — мало данных;
- declining — спад (только при отрицательной динамике).

Коэффициент использует абсолютные счётчики с симметричным сглаживанием,
чтобы малые базы не давали экстремальные проценты.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from ..enrichment.tag_filter import SIGNAL_AI_TAGS, is_signal_tag
from ..enrichment.taxonomy import AI_TECH_TAGS
from .constants import SIGNAL_WINDOW_DAYS, SIGNAL_WINDOW_WEEKS
from .timeseries import tag_profiles, week_start
from .velocity import velocity_from_smoothed_counts, velocity_label

LEVEL_ORDER = {
    "strong": 0,
    "emerging": 1,
    "research": 2,
    "spike": 3,
    "weak": 4,
    "stable": 5,
    "declining": 6,
}

NEW_TECH_AGE_WEEKS = 16
CENSOR_MARGIN_WEEKS = 4
RESEARCH_SHARE = 0.8
SPIKE_CONCENTRATION = 0.7

# Пороги силы по сглаженной динамике публикаций (velocity).
STRONG_VEL = 0.50      # +50% и выше
EMERGING_VEL = 0.25    # +25%..+50%
DECLINE_VEL = -0.25    # −25% и ниже
STABLE_BAND = 0.25     # |v| < 25% → stable при достаточном объёме


def _window_label(days: int = SIGNAL_WINDOW_DAYS) -> str:
    return "90 дн." if days == SIGNAL_WINDOW_DAYS else f"{days} дн."


def level_from_velocity(
    *,
    velocity: float,
    vel_source: str | None,
    recent: int,
    prior: int,
    n_types: int,
    week_conc: float,
    genuinely_new: bool,
    research_share_alltime: float,
    age_weeks: int,
    coverage_weeks: int,
) -> tuple[str, str]:
    """Уровень сигнала следует из динамики; declining только при отрицательном приросте."""
    vel_label = velocity_label(velocity, vel_source)

    if genuinely_new and recent >= 2 and research_share_alltime >= RESEARCH_SHARE:
        return (
            "research",
            (
                f"тема появилась ~{age_weeks} нед. назад (покрытие источников — "
                f"{coverage_weeks} нед.) и пока живет в исследованиях — наблюдать"
            ),
        )

    if recent >= 5 and week_conc >= SPIKE_CONCENTRATION and n_types <= 1:
        return (
            "spike",
            (
                f"{round(week_conc * 100)}% публикаций в одной неделе из одного типа "
                "источников — вероятен разовый инфоповод"
            ),
        )

    if vel_source is None:
        return (
            "weak",
            f"{recent} публ. за {_window_label()}, мало данных для сравнения периодов",
        )

    # Главное правило: знак/величина прироста = сила сигнала.
    if velocity >= STRONG_VEL and recent >= 8 and n_types >= 2:
        return (
            "strong",
            f"сильный рост публикаций: {vel_label}, {recent} публ. за {_window_label()}, {n_types} тип(а) источников",
        )
    if velocity >= STRONG_VEL and recent >= 5:
        return (
            "emerging",
            f"рост публикаций {vel_label}, {recent} публ. за {_window_label()} — набирает силу",
        )
    if velocity >= EMERGING_VEL and recent >= 3:
        return (
            "emerging",
            f"рост публикаций {vel_label}, {recent} публ. за {_window_label()}",
        )
    if velocity <= DECLINE_VEL and prior >= 5:
        return (
            "declining",
            f"спад публикаций {vel_label} к предыдущим {_window_label()}",
        )
    if abs(velocity) < STABLE_BAND and recent >= 5:
        return (
            "stable",
            f"динамика стабильна ({vel_label}), {recent} публ. за {_window_label()}",
        )
    return (
        "weak",
        f"{recent} публ. за {_window_label()}, {vel_label}, {n_types} тип(а) источников",
    )


def signal_mention_total(counts: dict[str, int]) -> int:
    """Знаменатель динамики: только упоминания отслеживаемых signal-тегов."""
    return sum(count for tag, count in counts.items() if is_signal_tag(tag))


def classify_signals(
    session,
    recent_days: int = SIGNAL_WINDOW_DAYS,
    recent_weeks: int | None = None,
    retro_weeks: int = 26,
) -> list[dict]:
    """Классификация сигналов.

    Динамика — сглаженное изменение абсолютного числа публикаций за последние
    `recent_days` относительно предыдущих `recent_days` (по умолчанию 90/90).
    """
    if recent_weeks is not None:
        recent_days = recent_weeks * 7
    now = utcnow()
    since = now - timedelta(weeks=retro_weeks)
    docs = session.scalars(
        select(Document).where(Document.published_at >= since)
    ).all()
    profiles = tag_profiles(session)
    tag_meta, source_start = profiles["tags"], profiles["source_start"]

    n_buckets = retro_weeks + 1
    first_week = week_start(since)

    def bucket(dt) -> int:
        return (week_start(dt) - first_week).days // 7

    recent_from = now - timedelta(days=recent_days)
    prior_from = now - timedelta(days=recent_days * 2)

    tag_series: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    recent_cnt: dict[str, int] = defaultdict(int)
    prior_cnt: dict[str, int] = defaultdict(int)
    src_types: dict[str, set] = defaultdict(set)
    by_src_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    corpus_recent = 0
    corpus_prior = 0

    for doc in docs:
        b = bucket(doc.published_at)
        if 0 <= b < n_buckets:
            for tag in doc.tags:
                tag_series[tag][b] += 1
        if doc.published_at >= recent_from:
            corpus_recent += 1
            for tag in doc.tags:
                recent_cnt[tag] += 1
                src_types[tag].add(doc.source_type)
                by_src_type[tag][doc.source_type] += 1
        elif doc.published_at >= prior_from:
            corpus_prior += 1
            for tag in doc.tags:
                prior_cnt[tag] += 1

    signals = []
    signal_mentions_recent = signal_mention_total(recent_cnt)
    signal_mentions_prior = signal_mention_total(prior_cnt)
    for tag in set(recent_cnt) | set(prior_cnt):
        if not is_signal_tag(tag):
            continue
        r, p = recent_cnt.get(tag, 0), prior_cnt.get(tag, 0)
        if r == 0 and p == 0:
            continue
        meta = tag_meta.get(tag, {})
        age_weeks = meta.get("age_weeks", 0)
        starts = [
            source_start[sid]
            for sid in meta.get("source_ids", [])
            if sid in source_start
        ]
        coverage_weeks = max(((now - min(starts)).days // 7) if starts else 0, 0)
        genuinely_new = (
            age_weeks <= NEW_TECH_AGE_WEEKS
            and age_weeks <= coverage_weeks - CENSOR_MARGIN_WEEKS
        )

        series = tag_series.get(tag, [0] * n_buckets)
        week_conc = max(series) / sum(series) if sum(series) else 0.0
        n_types = len(src_types.get(tag, set()))
        research_share = by_src_type[tag].get("research", 0) / r if r else 0.0

        recent_share = (r / signal_mentions_recent) if signal_mentions_recent else None
        prior_share = (p / signal_mentions_prior) if signal_mentions_prior else None
        velocity, vel_source = velocity_from_smoothed_counts(r, p)

        level, reason = level_from_velocity(
            velocity=velocity,
            vel_source=vel_source,
            recent=r,
            prior=p,
            n_types=n_types,
            week_conc=week_conc,
            genuinely_new=genuinely_new,
            research_share_alltime=meta.get("research_share_alltime", 0),
            age_weeks=age_weeks,
            coverage_weeks=coverage_weeks,
        )

        signals.append(
            {
                "tag": tag,
                "recent": r,
                "prior": p,
                "velocity": round(velocity, 3),
                "velocity_source": vel_source,
                "source_types": sorted(src_types.get(tag, set())),
                "by_source_type": dict(by_src_type.get(tag, {})),
                "level": level,
                "reason": reason,
                "category": "ai_tech" if tag in AI_TECH_TAGS else "security",
                "long_running": age_weeks >= 26,
                "age_weeks": age_weeks,
                "recent_share": round(recent_share, 4) if recent_share is not None else None,
                "baseline_share": round(prior_share, 4) if prior_share is not None else None,
                "share_denominator": "signal_mentions",
                "velocity_method": "smoothed_counts",
                "signal_mentions_recent": signal_mentions_recent,
                "signal_mentions_prior": signal_mentions_prior,
                "research_share": round(research_share, 2),
                "window_days": recent_days,
                "window_weeks": SIGNAL_WINDOW_WEEKS,
                "corpus_recent": corpus_recent,
                "corpus_prior": corpus_prior,
            }
        )

    signals.sort(
        key=lambda s: (
            LEVEL_ORDER[s["level"]],
            0 if s["tag"] in SIGNAL_AI_TAGS else 1,
            -s["recent"],
        )
    )
    return signals
