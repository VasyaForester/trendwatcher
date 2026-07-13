"""Скоринг топ-событий.

Research (arXiv): ранжирование по TBSF (0–100) + бонус корроборации.
Остальные типы: trust + severity + свежесть + корроборация (без «звёзд» в UI).
"""

from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow


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


def _rank(doc: Document, docs: list[Document], days: int, now) -> tuple[float, int]:
    corr = _corroboration(doc, docs)
    if doc.source_type == "research" and doc.tbsf_score is not None:
        return doc.tbsf_score + min(corr, 5) * 2, corr
    age_days = max((now - doc.published_at).days, 0)
    recency = max(0.0, 1.0 - age_days / days)
    composite = (
        doc.trust * 1.5
        + doc.severity * 2.0
        + min(len(doc.tags), 3) * 0.4
        + recency * 1.0
        + min(corr, 5) * 0.6
    )
    return composite, corr


def top_events(session, days: int = 30, limit: int = 15) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    docs = session.scalars(
        select(Document).where(Document.published_at >= since)
    ).all()
    if not docs:
        return []

    now = utcnow()
    results = []
    for doc in docs:
        rank, corr = _rank(doc, docs, days, now)
        results.append((rank, corr, doc))

    results.sort(key=lambda x: x[0], reverse=True)
    out = []
    for rank, corr, doc in results[:limit]:
        item = {**doc.to_dict(), "corroboration": corr}
        if doc.source_type == "research" and doc.tbsf_score is not None:
            item["score_type"] = "tbsf"
            item["score"] = doc.tbsf_score
            item["score_label"] = doc.tbsf_level or "⚪"
        else:
            item["score_type"] = "composite"
            item["score"] = round(rank, 2)
            item["score_label"] = None
        out.append(item)
    return out
