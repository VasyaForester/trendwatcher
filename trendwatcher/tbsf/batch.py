"""Пакетная TBSF-оценка research-документов в БД."""

from sqlalchemy import select

from ..db import Document, utcnow
from .arxiv_text import (
    arxiv_id_from_url,
    fetch_fulltext,
    is_arxiv_url,
    scoring_text,
)
from .service import score_research_paper

FULLTEXT_DAYS = 35  # полный текст — для окна топ-событий (~30 дней)
MAX_FULLTEXT_FETCH = 100  # за один прогон (ingest/CI), остальное — инкрементально

_fulltext_budget = MAX_FULLTEXT_FETCH


def _reset_fulltext_budget(budget: int = MAX_FULLTEXT_FETCH) -> None:
    global _fulltext_budget
    _fulltext_budget = budget


def _ensure_fulltext(doc: Document) -> None:
    global _fulltext_budget
    if doc.full_text or not is_arxiv_url(doc.url):
        return
    if (utcnow() - doc.published_at).days > FULLTEXT_DAYS:
        return
    if _fulltext_budget <= 0:
        return
    aid = arxiv_id_from_url(doc.url)
    if not aid:
        return
    doc.full_text = fetch_fulltext(aid) or None
    _fulltext_budget -= 1


def apply_tbsf(doc: Document, fetch_body: bool = True) -> None:
    if doc.source_type != "research":
        doc.tbsf_score = None
        doc.tbsf_level = None
        doc.tbsf_vector = None
        return
    if fetch_body:
        _ensure_fulltext(doc)
    text = scoring_text(doc.title, doc.summary, doc.full_text)
    result = score_research_paper(
        doc.title, text, doc.published_at, doc.url
    )
    doc.tbsf_score = result["tbsf_score"]
    doc.tbsf_level = result["tbsf_level"]
    doc.tbsf_vector = result["tbsf_vector"]


def diet_full_text(session) -> int:
    """Удаляет full_text у документов старше окна топ-событий — диета БД."""
    docs = session.scalars(
        select(Document).where(Document.full_text.is_not(None))
    ).all()
    dropped = 0
    for doc in docs:
        if (utcnow() - doc.published_at).days > FULLTEXT_DAYS:
            doc.full_text = None
            dropped += 1
    session.commit()
    return dropped


def rescore_all(session, fetch_fulltext: bool = True) -> int:
    if fetch_fulltext:
        _reset_fulltext_budget()
    docs = session.scalars(
        select(Document)
        .where(Document.source_type == "research")
        .order_by(Document.published_at.desc())
    ).all()
    total = len(docs)
    for i, doc in enumerate(docs, 1):
        apply_tbsf(doc, fetch_body=fetch_fulltext)
        if i % 25 == 0 or i == total:
            session.commit()
            print(f"  TBSF: {i}/{total}", flush=True)
    session.commit()
    return total
