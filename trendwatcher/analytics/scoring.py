"""Скоринг топ-событий.

Research (arXiv): только TBSF ≥ порога (цель — reserve 50%, fallback 45/42).
Остальные типы: trust + severity + свежесть + корроборация.
"""

from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from ..tbsf.thresholds import FEED_MIN, TOP_MIN_TARGET


def _corroboration(doc: Document, docs: list[Document]) -> int:
    tags, entities = set(doc.tags), set(doc.entities)
    if not tags:
        return 0
    count = 0
    for other in docs:
        if other.id == doc.id or other.source_id == doc.source_id:
            continue
        if abs((other.published_at - doc.published_at).days) > 3:
            continue
        if tags & set(other.tags) and (not entities or entities & set(other.entities)):
            count += 1
    return count


def _composite(doc: Document, docs: list[Document], days: int, now) -> float:
    corr = _corroboration(doc, docs)
    age_days = max((now - doc.published_at).days, 0)
    recency = max(0.0, 1.0 - age_days / days)
    return (
        doc.trust * 1.5
        + doc.severity * 2.0
        + min(len(doc.tags), 3) * 0.4
        + recency * 1.0
        + min(corr, 5) * 0.6
    )


def _research_min_for_pool(docs: list[Document]) -> int:
    """Выбирает минимальный порог: стремимся к reserve (50), но не опустошаем топ."""
    research = [
        d for d in docs
        if d.source_type == "research" and d.tbsf_score is not None
    ]
    for floor in (TOP_MIN_TARGET, 48, FEED_MIN):
        if sum(1 for d in research if d.tbsf_score >= floor) >= 3:
            return floor
    return FEED_MIN


def _format_event(doc: Document, corr: int, rank: float) -> dict:
    item = {**doc.to_dict(), "corroboration": corr}
    if doc.source_type == "research" and doc.tbsf_score is not None:
        item["score_type"] = "tbsf"
        item["score"] = doc.tbsf_score
        item["score_label"] = doc.tbsf_level or "⚪"
    else:
        item["score_type"] = "composite"
        item["score"] = round(rank, 2)
        item["score_label"] = None
    return item


def top_events(session, days: int = 30, limit: int = 15) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    docs = session.scalars(
        select(Document).where(Document.published_at >= since)
    ).all()
    if not docs:
        return []

    now = utcnow()
    min_tbsf = _research_min_for_pool(docs)

    research = [
        d for d in docs
        if d.source_type == "research"
        and d.tbsf_score is not None
        and d.tbsf_score >= min_tbsf
    ]
    research.sort(
        key=lambda d: (d.tbsf_score + min(_corroboration(d, docs), 5) * 2),
        reverse=True,
    )

    non_research = sorted(
        [d for d in docs if d.source_type != "research"],
        key=lambda d: _composite(d, docs, days, now),
        reverse=True,
    )

    out: list[dict] = []
    research_slots = min(len(research), max(limit // 2 + 2, 6))
    for doc in research[:research_slots]:
        corr = _corroboration(doc, docs)
        out.append(_format_event(doc, corr, doc.tbsf_score or 0))

    for doc in non_research:
        if len(out) >= limit:
            break
        corr = _corroboration(doc, docs)
        rank = _composite(doc, docs, days, now)
        out.append(_format_event(doc, corr, rank))

    ri = research_slots
    while len(out) < limit and ri < len(research):
        doc = research[ri]
        corr = _corroboration(doc, docs)
        out.append(_format_event(doc, corr, doc.tbsf_score or 0))
        ri += 1

    return out[:limit]
