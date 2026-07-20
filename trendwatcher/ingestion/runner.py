"""Раннер ingestion: обходит источники, фильтрует, дедуплицирует, обогащает, пишет в БД."""

import logging

from sqlalchemy import select

from ..config import SourceConfig, load_sources
from ..db import Document, get_session, init_db
from ..enrichment.tagger import enrich, is_feed_relevant
from ..tbsf.batch import apply_tbsf
from . import arxiv, nvd, rss
from .dedup import normalize_url, title_fingerprint

log = logging.getLogger("trendwatcher.ingest")

CONNECTORS = {"rss": rss.fetch, "arxiv": arxiv.fetch, "nvd": nvd.fetch}


def ingest_source(source: SourceConfig, session) -> tuple[int, int]:
    """Возвращает (новых документов, всего получено)."""
    items = CONNECTORS[source.type](source)
    # URL и отпечатки заголовков — по всей базе (перепечатки из разных лент).
    existing_urls = {normalize_url(u) for u in session.scalars(select(Document.url)).all()}
    existing_titles = {
        title_fingerprint(t)
        for t in session.scalars(select(Document.title)).all()
        if title_fingerprint(t)
    }
    added = 0
    for item in items:
        url = normalize_url(item["url"])
        title_key = title_fingerprint(item["title"])
        if not url or url in existing_urls:
            continue
        if title_key and title_key in existing_titles:
            continue
        text = f"{item['title']}\n{item['summary']}"
        meta = enrich(item["title"], item["summary"], source.source_type)
        if source.filter_ai and not is_feed_relevant(
            text, meta["tags"], source_name=source.name
        ):
            continue
        severity = meta["severity"]
        if item.get("cvss") is not None:
            severity = max(severity, item["cvss"] / 10.0)
        doc = Document(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            doc_type=meta["doc_type"],
            url=url or item["url"],
            title=item["title"],
            summary=item["summary"],
            published_at=item["published_at"],
            trust=source.trust,
            severity=round(severity, 3),
        )
        doc.tags = meta["tags"]
        doc.entities = meta["entities"]
        apply_tbsf(doc)
        session.add(doc)
        existing_urls.add(url)
        if title_key:
            existing_titles.add(title_key)
        added += 1
    session.commit()
    return added, len(items)


def retag_all() -> None:
    """Переразметка всех документов текущей таксономией (после ее обновления)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    with get_session() as session:
        docs = session.scalars(select(Document)).all()
        for doc in docs:
            meta = enrich(doc.title, doc.summary, doc.source_type)
            doc.tags = meta["tags"]
            doc.entities = meta["entities"]
            doc.doc_type = meta["doc_type"]
            # severity не понижаем: в ней может сидеть CVSS-компонента с момента ingest
            doc.severity = max(doc.severity, meta["severity"])
            apply_tbsf(doc, fetch_body=False)
        session.commit()
        log.info("retagged %d documents", len(docs))


def run_all() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    sources = load_sources()
    with get_session() as session:
        for source in sources:
            try:
                added, total = ingest_source(source, session)
                log.info("[%s] fetched=%d added=%d", source.id, total, added)
            except Exception as exc:  # noqa: BLE001 — источник не должен ронять весь сбор
                session.rollback()
                log.error("[%s] FAILED: %s", source.id, exc)
