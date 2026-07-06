"""Скоринг топ-событий.

score = доверие источника + severity + теговая насыщенность + свежесть
      + бонус корроборации (другие документы за ±3 дня с пересечением тегов и сущностей).
"""

from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow


def _corroboration(doc: Document, docs: list[Document]) -> int:
    """Число документов из других источников за ±3 дня, разделяющих тег и сущность."""
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
        age_days = max((now - doc.published_at).days, 0)
        recency = max(0.0, 1.0 - age_days / days)
        corr = _corroboration(doc, docs)
        score = (
            doc.trust * 1.5
            + doc.severity * 2.0
            + min(len(doc.tags), 3) * 0.4
            + recency * 1.0
            + min(corr, 5) * 0.6
        )
        results.append((score, corr, doc))

    results.sort(key=lambda x: x[0], reverse=True)
    return [
        {**doc.to_dict(), "score": round(score, 2), "corroboration": corr}
        for score, corr, doc in results[:limit]
    ]
