"""Лента новостей: без arXiv, GenAI-релевантные публикации из других источников, по дате."""

from sqlalchemy import select

from .db import Document
from .enrichment.tagger import is_ai_related
from .enrichment.taxonomy import AI_TECH_TAGS, SECURITY_TAGS
from .tbsf.arxiv_text import is_arxiv_url

FEED_SCAN_LIMIT = 8000


def _feed_eligible(doc: Document) -> bool:
    """Широкий фильтр: лучше показать лишнее, чем пропустить важное (MemGhost и т.п.)."""
    if doc.source_type == "vulnerability":
        return True
    text = f"{doc.title}\n{doc.summary}"
    if is_ai_related(text):
        return True
    if doc.tags and set(doc.tags) & (SECURITY_TAGS | AI_TECH_TAGS):
        return True
    if doc.doc_type in ("vulnerability", "incident", "regulation", "framework"):
        return True
    if doc.severity >= 0.3:
        return True
    return False


def build_feed(session, limit: int = 600) -> list[dict]:
    docs = session.scalars(
        select(Document).order_by(Document.published_at.desc()).limit(FEED_SCAN_LIMIT)
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
