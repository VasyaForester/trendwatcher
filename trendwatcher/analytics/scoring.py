"""Топ событий: только arXiv-статьи, сортировка по TBSF (убывание)."""

from datetime import timedelta

from sqlalchemy import select

from ..db import Document, utcnow
from ..enrichment.taxonomy import AI_TECH_TAGS, SECURITY_TAGS
from ..tbsf.arxiv_text import is_arxiv_url


def _eligible(doc: Document) -> bool:
    """GenAI security, AI-тренды или хотя бы минимальная TBSF-релевантность."""
    if doc.tbsf_vector:
        return True
    if doc.tags and set(doc.tags) & (SECURITY_TAGS | AI_TECH_TAGS):
        return True
    return (doc.tbsf_score or 0) >= 18


def top_events(session, days: int = 30, limit: int = 15) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    docs = session.scalars(
        select(Document).where(
            Document.published_at >= since,
            Document.source_type == "research",
        )
    ).all()

    papers = [
        d for d in docs
        if is_arxiv_url(d.url)
        and d.tbsf_score is not None
        and _eligible(d)
    ]
    papers.sort(key=lambda d: d.tbsf_score or 0, reverse=True)

    return [
        {
            **doc.to_dict(),
            "score_type": "tbsf",
            "score": doc.tbsf_score,
            "score_label": doc.tbsf_level or "⚪",
            "corroboration": 0,
        }
        for doc in papers[:limit]
    ]
