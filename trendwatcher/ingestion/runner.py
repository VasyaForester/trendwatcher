"""Раннер ingestion: обходит источники, фильтрует, дедуплицирует, обогащает, пишет в БД."""

import logging

from sqlalchemy import select

from ..config import SourceConfig, load_sources
from ..db import Document, get_session, init_db
from ..enrichment.tagger import enrich, is_ai_related
from ..tbsf.batch import apply_tbsf
from . import arxiv, nvd, rss

log = logging.getLogger("trendwatcher.ingest")

CONNECTORS = {"rss": rss.fetch, "arxiv": arxiv.fetch, "nvd": nvd.fetch}


def ingest_source(source: SourceConfig, session) -> tuple[int, int]:
    """Возвращает (новых документов, всего получено)."""
    items = CONNECTORS[source.type](source)
    # URL проверяем по всей базе: один документ может прийти из разных источников
    # (например, одна arXiv-статья попадает под security- и general-запросы)
    existing_urls = set(session.scalars(select(Document.url)).all())
    added = 0
    for item in items:
        if item["url"] in existing_urls:
            continue
        text = f"{item['title']}\n{item['summary']}"
        if source.filter_ai and not is_ai_related(text):
            continue
        meta = enrich(item["title"], item["summary"], source.source_type)
        severity = meta["severity"]
        if item.get("cvss") is not None:
            severity = max(severity, item["cvss"] / 10.0)
        doc = Document(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            doc_type=meta["doc_type"],
            url=item["url"],
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
        existing_urls.add(item["url"])
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
            apply_tbsf(doc)
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
