"""Пакетная TBSF-оценка research-документов в БД."""

from sqlalchemy import select

from ..db import Document, get_session
from .service import score_research_paper


def apply_tbsf(doc: Document) -> None:
    if doc.source_type != "research":
        doc.tbsf_score = None
        doc.tbsf_level = None
        doc.tbsf_vector = None
        return
    result = score_research_paper(
        doc.title, doc.summary, doc.published_at, doc.url
    )
    doc.tbsf_score = result["tbsf_score"]
    doc.tbsf_level = result["tbsf_level"]
    doc.tbsf_vector = result["tbsf_vector"]


def rescore_all(session) -> int:
    docs = session.scalars(
        select(Document).where(Document.source_type == "research")
    ).all()
    for doc in docs:
        apply_tbsf(doc)
    session.commit()
    return len(docs)
