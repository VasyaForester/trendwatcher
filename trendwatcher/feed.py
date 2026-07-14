"""Лента новостей: без arXiv, GenAI security из других источников, по дате."""

from sqlalchemy import select

from .db import Document
from .enrichment.tagger import is_ai_related
from .enrichment.taxonomy import SECURITY_TAGS
from .tbsf.arxiv_text import is_arxiv_url


def _feed_eligible(doc: Document) -> bool:
    text = f"{doc.title}\n{doc.summary}"
    if not is_ai_related(text):
        return False
    tags = set(doc.tags)
    if tags & SECURITY_TAGS:
        return True
    if doc.doc_type in ("vulnerability", "incident", "regulation", "framework"):
        return True
    if doc.source_type == "vulnerability":
        return True
    if doc.severity >= 0.3:
        return True
    return False


def build_feed(session, limit: int = 400) -> list[dict]:
    docs = session.scalars(
        select(Document).order_by(Document.published_at.desc()).limit(2500)
    ).all()

    out: list[Document] = []
    for d in docs:
        if d.source_type == "research" or is_arxiv_url(d.url):
            continue
        if not _feed_eligible(d):
            continue
        out.append(d)

    out.sort(key=lambda d: d.published_at, reverse=True)
    return [d.to_dict() for d in out[:limit]]
