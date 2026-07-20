"""Лента новостей: без arXiv; только AI security / breakthrough AI; без повторов."""

from sqlalchemy import select

from .db import Document
from .enrichment.tagger import is_ai_security_or_breakthrough
from .enrichment.taxonomy import BREAKTHROUGH_AI_TAGS, SECURITY_TAGS
from .ingestion.dedup import normalize_url, title_fingerprint
from .tbsf.arxiv_text import is_arxiv_url

FEED_SCAN_LIMIT = 8000


def _feed_eligible(doc: Document) -> bool:
    """В ленту — только AI security или прорывные AI-темы."""
    text = f"{doc.title}\n{doc.summary}"
    tags = doc.tags or []
    tag_set = set(tags)

    if doc.source_type == "vulnerability":
        return is_ai_security_or_breakthrough(text, tags)

    if tag_set & SECURITY_TAGS:
        return True
    if tag_set & BREAKTHROUGH_AI_TAGS:
        return True
    if doc.doc_type in ("vulnerability", "incident", "regulation", "framework"):
        return is_ai_security_or_breakthrough(text, tags)
    return is_ai_security_or_breakthrough(text, tags)


def build_feed(session, limit: int = 600) -> list[dict]:
    docs = session.scalars(
        select(Document).order_by(Document.published_at.desc()).limit(FEED_SCAN_LIMIT)
    ).all()

    out: list[Document] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for d in docs:
        if d.source_type == "research" or is_arxiv_url(d.url):
            continue
        if not _feed_eligible(d):
            continue
        url_key = normalize_url(d.url)
        title_key = title_fingerprint(d.title)
        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        out.append(d)

    out.sort(key=lambda d: d.published_at, reverse=True)
    return [d.to_dict() for d in out[:limit]]
