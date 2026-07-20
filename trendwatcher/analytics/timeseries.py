"""Недельные временные ряды по тегам таксономии."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from ..enrichment.tag_filter import TREND_CHART_GENERAL, TREND_CHART_SPECIAL
from .velocity import cap_velocity, pct_change


def week_start(d: datetime) -> date:
    dd = d.date()
    return dd - timedelta(days=dd.weekday())


def _nice_axis_max(peak: float) -> int:
    """Подгоняет верхнюю границу оси Y, чтобы графики выглядели сопоставимо."""
    peak = max(float(peak), 1.0)
    padded = peak * 1.15
    if padded <= 5:
        return 5
    exp = 10 ** max(math.floor(math.log10(padded)) - 1, 0)
    for mult in (1, 2, 2.5, 5, 10):
        step = exp * mult
        candidate = math.ceil(padded / step) * step
        if candidate >= padded:
            return int(candidate)
    return int(math.ceil(padded))


def _chart_bundle(
    series: dict[str, list[float | int]],
    allowed: frozenset[str],
    top_n: int = 7,
) -> dict:
    scored = []
    for tag, arr in series.items():
        if tag not in allowed:
            continue
        total = sum(arr)
        if total <= 0:
            continue
        scored.append((tag, total, max(arr) if arr else 0))
    scored.sort(key=lambda x: (-x[1], x[0]))
    picked = scored[:top_n]
    chart_series = {tag: series[tag] for tag, _, _ in picked}
    peak = max((mx for _, _, mx in picked), default=0)
    return {
        "tags": [tag for tag, _, _ in picked],
        "series": chart_series,
        "y_max": _nice_axis_max(peak),
    }


def weekly_share_series_from_archive(weeks: int = 13) -> dict | None:
    """Недельные доли тегов (%) из архива — сопоставимые графики без raw-bias."""
    from .archive import last_complete_week_start, load_weekly_snapshots

    snaps = {s["week_start"]: s for s in load_weekly_snapshots()}
    if not snaps:
        return None
    last = last_complete_week_start()
    labels = [(last - timedelta(weeks=weeks - 1 - i)).isoformat() for i in range(weeks)]
    # Нужен хотя бы половина недель с данными, иначе fallback на живую БД.
    covered = sum(1 for lab in labels if snaps.get(lab, {}).get("documents", 0) > 0)
    if covered < max(weeks // 2, 3):
        return None

    series: dict[str, list[float]] = defaultdict(lambda: [0.0] * weeks)
    totals = [0] * weeks
    for i, label in enumerate(labels):
        snap = snaps.get(label)
        if not snap:
            continue
        total = int(snap.get("documents", 0) or 0)
        totals[i] = total
        if total <= 0:
            continue
        for tag, meta in snap.get("tags", {}).items():
            if "share" in meta:
                pct = 100.0 * float(meta["share"])
            else:
                pct = 100.0 * float(meta.get("count", 0)) / total
            series[tag][i] = round(pct, 3)

    series_dict = dict(series)
    return {
        "weeks": labels,
        "series": series_dict,
        "totals": totals,
        "unit": "share_pct",
        "charts": {
            "general": _chart_bundle(series_dict, TREND_CHART_GENERAL),
            "special": _chart_bundle(series_dict, TREND_CHART_SPECIAL),
        },
    }


def weekly_tag_counts(session, weeks: int = 13) -> dict:
    """Недельные ряды + чарты. Предпочтительно доли (%) из архива."""
    archived = weekly_share_series_from_archive(weeks=weeks)
    if archived is not None:
        return archived

    since = utcnow() - timedelta(weeks=weeks)
    docs = session.scalars(
        select(Document).where(Document.published_at >= since)
    ).all()

    first_week = week_start(since)
    n_buckets = weeks + 1
    week_labels = [(first_week + timedelta(weeks=i)).isoformat() for i in range(n_buckets)]
    index = {label: i for i, label in enumerate(week_labels)}

    counts: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    totals = [0] * n_buckets
    totals_by_source: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    for doc in docs:
        label = week_start(doc.published_at).isoformat()
        if label not in index:
            continue
        totals[index[label]] += 1
        totals_by_source[doc.source_id][index[label]] += 1
        for tag in doc.tags:
            counts[tag][index[label]] += 1

    # Fallback: доли от живой БД (всё ещё лучше сырых счётчиков при разной плотности).
    series_pct: dict[str, list[float]] = {}
    for tag, arr in counts.items():
        series_pct[tag] = [
            round(100.0 * c / t, 3) if t else 0.0 for c, t in zip(arr, totals)
        ]
    return {
        "weeks": week_labels,
        "series": series_pct,
        "totals": totals,
        "totals_by_source": dict(totals_by_source),
        "unit": "share_pct",
        "charts": {
            "general": _chart_bundle(series_pct, TREND_CHART_GENERAL),
            "special": _chart_bundle(series_pct, TREND_CHART_SPECIAL),
        },
    }


def tag_profiles(session) -> dict:
    """Профили тегов за всю историю корпуса + глубина покрытия источников.

    Возвращает {"tags": {tag: {...}}, "source_start": {source_id: earliest published}}.
    Первое появление темы имеет смысл только относительно глубины покрытия
    источников: если корпус по источнику начинается там же, где тема, — тема
    не «новая», просто данные не глубже.
    """
    docs = session.scalars(select(Document)).all()
    first_seen: dict[str, datetime] = {}
    total: dict[str, int] = defaultdict(int)
    research: dict[str, int] = defaultdict(int)
    tag_sources: dict[str, set] = defaultdict(set)
    source_start: dict[str, datetime] = {}

    for doc in docs:
        prev = source_start.get(doc.source_id)
        if prev is None or doc.published_at < prev:
            source_start[doc.source_id] = doc.published_at
        for tag in doc.tags:
            total[tag] += 1
            tag_sources[tag].add(doc.source_id)
            if doc.source_type == "research":
                research[tag] += 1
            if tag not in first_seen or doc.published_at < first_seen[tag]:
                first_seen[tag] = doc.published_at

    now = utcnow()
    tags = {
        tag: {
            "first_seen": first_seen[tag],
            "age_weeks": max((now - first_seen[tag]).days // 7, 0),
            "research_share_alltime": research[tag] / total[tag],
            "total_alltime": total[tag],
            "source_ids": sorted(tag_sources[tag]),
        }
        for tag in total
    }
    return {"tags": tags, "source_start": source_start}


def tag_stats(session, recent_weeks: int = 4) -> list[dict]:
    """Для каждого тега: количество за последние N недель, за предыдущие N, velocity,
    разнообразие типов источников за последний период."""
    now = utcnow()
    recent_from = now - timedelta(weeks=recent_weeks)
    prior_from = now - timedelta(weeks=recent_weeks * 2)

    docs = session.scalars(
        select(Document).where(Document.published_at >= prior_from)
    ).all()

    recent: dict[str, int] = defaultdict(int)
    prior: dict[str, int] = defaultdict(int)
    source_types: dict[str, set] = defaultdict(set)
    by_source_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for doc in docs:
        bucket = recent if doc.published_at >= recent_from else prior
        for tag in doc.tags:
            bucket[tag] += 1
            if doc.published_at >= recent_from:
                source_types[tag].add(doc.source_type)
                by_source_type[tag][doc.source_type] += 1

    stats = []
    for tag in set(recent) | set(prior):
        r, p = recent.get(tag, 0), prior.get(tag, 0)
        v = pct_change(float(r), float(p))
        velocity = cap_velocity(v) if v is not None else (0.0 if p == 0 else 0.0)
        stats.append(
            {
                "tag": tag,
                "recent": r,
                "prior": p,
                "velocity": round(velocity, 3),
                "source_types": sorted(source_types.get(tag, set())),
                "by_source_type": dict(by_source_type.get(tag, {})),
            }
        )
    stats.sort(key=lambda s: s["recent"], reverse=True)
    return stats
