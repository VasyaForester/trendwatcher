"""Классификация зрелости сигналов.

Уровни:
- strong    — устойчивый рост доли темы, подтвержден несколькими типами источников;
- emerging  — растущая тема, есть корроборация;
- research  — молодая тема, живущая пока только в исследованиях — потенциально
              перспективная технология, стоит наблюдать;
- spike     — всплеск одной недели у долгоиграющей темы: вероятен разовый инфоповод
              или артефакт парсинга, трендом не считается;
- stable    — долгоиграющая тема на своем базовом уровне (фон);
- weak      — единичные упоминания;
- declining — устойчивый спад.

Защита от артефактов сбора данных:
1. Динамика считается по ДОЛЕ темы в корпусе, а не по абсолютным счетчикам —
   абсолютный рост может отражать просто глубину парсинга.
2. Доли считаются только по «стабильному подкорпусу»: источникам, у которых есть
   достаточно документов и в baseline-, и в recent-окне. Иначе свежедобавленный
   источник, заливший архив за пару недель, ломает все пропорции.
3. Возраст темы цензурируется глубиной покрытия ее источников: если тема «появилась»
   там же, где начинается корпус, — она не новая, просто данные не глубже.
4. Для долгоиграющих тем требуется несколько недель выше baseline подряд;
   одиночный всплеск помечается как spike (инфоповод), а не тренд.
"""

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from ..enrichment.tag_filter import SIGNAL_AI_TAGS, is_signal_tag
from ..enrichment.taxonomy import AI_TECH_TAGS
from .archive import archive_tag_windows
from .constants import SIGNAL_WINDOW_DAYS, SIGNAL_WINDOW_WEEKS
from .timeseries import tag_profiles, week_start
from .velocity import cap_velocity, pct_change, velocity_from_counts, velocity_label


LEVEL_ORDER = {
    "strong": 0, "emerging": 1, "research": 2, "spike": 3,
    "weak": 4, "stable": 5, "declining": 6,
}

MATURE_AGE_WEEKS = 26       # возраст темы, после которого она долгоиграющая
MATURE_ACTIVE_WEEKS = 8     # либо столько активных недель в baseline
NEW_TECH_AGE_WEEKS = 16     # моложе этого — кандидат в research-сигнал
CENSOR_MARGIN_WEEKS = 4     # тема должна появиться заметно позже начала покрытия
ACCEL_RATIO = 1.5           # во сколько раз доля должна превышать baseline
SUSTAINED_WEEKS = 2         # недель выше порога для «устойчивого» роста
SPIKE_CONCENTRATION = 0.6   # доля публикаций одной недели => подозрение на вспышку
RESEARCH_SHARE = 0.8        # доля research-источников => research-сигнал
MIN_WEEK_DOCS = 5           # валидная неделя стабильного корпуса
MIN_STABLE_BASE = 10        # документов источника в baseline для «стабильности»
MIN_STABLE_RECENT = 5       # документов источника в recent для «стабильности»


def _window_label(days: int = SIGNAL_WINDOW_DAYS) -> str:
    return "90 дн." if days == SIGNAL_WINDOW_DAYS else f"{days} дн."


def classify_signals(
    session,
    recent_days: int = SIGNAL_WINDOW_DAYS,
    recent_weeks: int | None = None,
    retro_weeks: int = 26,
) -> list[dict]:
    """Классификация сигналов.

    Динамика (velocity) — прирост числа публикаций за последние `recent_days`
    к предыдущим `recent_days` (по умолчанию 90/90).
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
    recent_weeks_buckets = SIGNAL_WINDOW_WEEKS

    def bucket(dt) -> int:
        return (week_start(dt) - first_week).days // 7

    # --- Стабильный подкорпус: источники, живущие в обоих окнах ---
    src_totals: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    for doc in docs:
        b = bucket(doc.published_at)
        if 0 <= b < n_buckets:
            src_totals[doc.source_id][b] += 1

    split = n_buckets - recent_weeks_buckets
    stable_sources = {
        sid
        for sid, t in src_totals.items()
        if sum(t[:split]) >= MIN_STABLE_BASE and sum(t[split:]) >= MIN_STABLE_RECENT
    }
    totals = [
        sum(src_totals[sid][i] for sid in stable_sources) for i in range(n_buckets)
    ]

    # --- Счетчики по тегам: окна ровно 90 / предыдущие 90 дней ---
    recent_from = now - timedelta(days=recent_days)
    prior_from = now - timedelta(days=recent_days * 2)
    tag_series: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    recent_cnt: dict[str, int] = defaultdict(int)
    prior_cnt: dict[str, int] = defaultdict(int)
    src_types: dict[str, set] = defaultdict(set)
    by_src_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for doc in docs:
        b = bucket(doc.published_at)
        in_stable = doc.source_id in stable_sources and 0 <= b < n_buckets
        is_recent = doc.published_at >= recent_from
        for tag in doc.tags:
            if in_stable:
                tag_series[tag][b] += 1
            if is_recent:
                recent_cnt[tag] += 1
                src_types[tag].add(doc.source_type)
                by_src_type[tag][doc.source_type] += 1
            elif doc.published_at >= prior_from:
                prior_cnt[tag] += 1

    def window_share(counts: list[int], tots: list[int]) -> float | None:
        num = sum(c for c, t in zip(counts, tots) if t >= MIN_WEEK_DOCS)
        den = sum(t for t in tots if t >= MIN_WEEK_DOCS)
        return num / den if den else None

    signals = []
    for tag in set(recent_cnt) | set(prior_cnt):
        if not is_signal_tag(tag):
            continue
        r, p = recent_cnt.get(tag, 0), prior_cnt.get(tag, 0)
        if r == 0 and p == 0:
            continue
        meta = tag_meta.get(tag, {})
        age_weeks = meta.get("age_weeks", 0)

        # Цензурирование возраста глубиной покрытия источников темы.
        starts = [source_start[sid] for sid in meta.get("source_ids", []) if sid in source_start]
        coverage_weeks = max(((now - min(starts)).days // 7) if starts else 0, 0)
        genuinely_new = (
            age_weeks <= NEW_TECH_AGE_WEEKS
            and age_weeks <= coverage_weeks - CENSOR_MARGIN_WEEKS
        )

        series = tag_series.get(tag, [0] * n_buckets)
        recent_counts, base_counts = series[split:], series[:split]
        base_active = sum(1 for c in base_counts if c > 0)
        long_running = age_weeks >= MATURE_AGE_WEEKS or base_active >= MATURE_ACTIVE_WEEKS

        recent_share = window_share(recent_counts, totals[split:])
        base_share = window_share(base_counts, totals[:split])
        ratio = recent_share / base_share if recent_share is not None and base_share else None

        sustained = 0
        if base_share:
            sustained = sum(
                1
                for c, t in zip(recent_counts, totals[split:])
                if t >= MIN_WEEK_DOCS and (c / t) >= base_share * ACCEL_RATIO
            )
        week_conc = max(recent_counts) / sum(recent_counts) if sum(recent_counts) else 0.0
        n_types = len(src_types.get(tag, set()))
        research_share = by_src_type[tag].get("research", 0) / r if r else 0.0

        # Динамика UI: прирост числа сообщений 90д / предыдущие 90д.
        velocity, vel_source = velocity_from_counts(r, p)
        vel_label = velocity_label(velocity, vel_source)

        # 1. Research-сигнал: действительно новая тема, живущая в исследованиях.
        if genuinely_new and r >= 2 and meta.get("research_share_alltime", 0) >= RESEARCH_SHARE:
            level = "research"
            reason = (
                f"тема появилась ~{age_weeks} нед. назад (покрытие источников — "
                f"{coverage_weeks} нед.) и пока живет только в исследованиях "
                f"({meta.get('total_alltime', 0)} работ) — потенциально перспективная "
                "технология, наблюдать"
            )
        # 2. Долгоиграющие темы: доля в стабильном подкорпусе vs baseline.
        elif long_running and ratio is not None:
            if ratio >= ACCEL_RATIO and sustained >= SUSTAINED_WEEKS and n_types >= 2:
                level = "strong"
                reason = (
                    f"устойчивый рост доли: {recent_share:.1%} стабильного корпуса против "
                    f"{base_share:.1%} за {retro_weeks} нед. baseline, {sustained} нед. выше "
                    f"порога, {n_types} тип(а) источников"
                )
            elif ratio >= ACCEL_RATIO and week_conc >= SPIKE_CONCENTRATION:
                level = "spike"
                reason = (
                    f"{round(week_conc * 100)}% публикаций пришлись на одну неделю "
                    f"(baseline {base_share:.1%}) — похоже на разовый инфоповод или "
                    "артефакт парсинга, не тренд"
                )
            elif ratio <= 0.5:
                if recent_share == 0 and r >= 3:
                    # Все свежие упоминания — из источников без стабильной глубины
                    # покрытия; вывод о спаде был бы артефактом сбора данных.
                    level = "weak"
                    reason = (
                        f"{r} публ. за {_window_label(recent_days)}, но все из источников с "
                        "недостаточной глубиной покрытия — надежно оценить тренд нельзя"
                    )
                else:
                    level = "declining"
                    reason = f"доля упала до {recent_share:.1%} против {base_share:.1%} baseline"
            else:
                kind = "долгоиграющая тема" if age_weeks >= MATURE_AGE_WEEKS else "тема"
                level = "stable"
                reason = (
                    f"{kind} (~{age_weeks} нед.) на базовом уровне: "
                    f"{recent_share:.1%} корпуса против {base_share:.1%} за {retro_weeks} нед."
                )
        # 3. Молодые темы: period-over-period + корроборация.
        elif r >= 5 and week_conc >= 0.7 and n_types == 1:
            level = "spike"
            reason = (
                f"{round(week_conc * 100)}% публикаций в одной неделе из одного типа "
                "источников — вероятен разовый инфоповод"
            )
        elif r >= 8 and n_types >= 3 and velocity >= 0:
            level = "strong"
            reason = f"{r} публ. за {_window_label(recent_days)}, {n_types} типа источников"
        elif r >= 3 and n_types >= 2 and velocity > 0.25:
            level = "emerging"
            reason = (
                f"{r} публ. за {_window_label(recent_days)}, {vel_label}, "
                f"{n_types} тип(а) источников"
            )
        elif velocity < -0.3 and p >= 5:
            level = "declining"
            reason = f"спад {vel_label} к прошлому периоду ({_window_label(recent_days)})"
        else:
            level = "weak"
            reason = f"{r} публ. за {_window_label(recent_days)}, {n_types} тип(а) источников"

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
                "long_running": long_running,
                "age_weeks": age_weeks,
                "recent_share": round(recent_share, 4) if recent_share is not None else None,
                "baseline_share": round(base_share, 4) if base_share is not None else None,
                "research_share": round(research_share, 2),
                "window_days": recent_days,
                "window_weeks": SIGNAL_WINDOW_WEEKS,
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
