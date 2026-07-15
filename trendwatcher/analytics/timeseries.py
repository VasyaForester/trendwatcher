"""Недельные временные ряды по тегам таксономии."""

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from .velocity import cap_velocity, pct_change


def week_start(d: datetime) -> date:
    dd = d.date()
    return dd - timedelta(days=dd.weekday())


def weekly_tag_counts(session, weeks: int = 13) -> dict:
    """Возвращает {"weeks": [...], "series": {tag: [count, ...]}, "totals": [count, ...]}.

    totals — общее число документов в корпусе за неделю: нужно для нормализации,
    потому что глубина выборки по неделям неравномерна (RSS отдают только хвост,
    arXiv — последние N статей).
    """
    since = utcnow() - timedelta(weeks=weeks)
    docs = session.scalars(
        select(Document).where(Document.published_at >= since)
    ).all()

    first_week = week_start(since)
    n_buckets = weeks + 1
    week_labels = [(first_week + timedelta(weeks=i)).isoformat() for i in range(n_buckets)]
    index = {label: i for i, label in enumerate(week_labels)}

    series: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    totals = [0] * n_buckets
    totals_by_source: dict[str, list[int]] = defaultdict(lambda: [0] * n_buckets)
    for doc in docs:
        label = week_start(doc.published_at).isoformat()
        if label not in index:
            continue
        totals[index[label]] += 1
        totals_by_source[doc.source_id][index[label]] += 1
        for tag in doc.tags:
            series[tag][index[label]] += 1

    return {
        "weeks": week_labels,
        "series": dict(series),
        "totals": totals,
        "totals_by_source": dict(totals_by_source),
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
