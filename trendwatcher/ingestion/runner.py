"""Раннер ingestion: обходит источники, фильтрует, дедуплицирует, обогащает, пишет в БД."""

import logging

from sqlalchemy import select

from ..config import SourceConfig, load_sources
from ..db import Document, get_session, init_db
from ..enrichment.candidates import load_trend_candidates
from ..enrichment.tagger import enrich
from ..relevance.editorial import cluster_event_key
from ..relevance.triage import log_reject, triage_document
from ..tbsf.batch import apply_tbsf
from . import arxiv, bingnews, gnews, hn, html_article, nvd, rss, telegram, watch, x
from .dedup import normalize_url
from .health import record_fetch
from .resolve import is_aggregator_url


log = logging.getLogger("trendwatcher.ingest")

CONNECTORS = {
    "rss": rss.fetch,
    "arxiv": arxiv.fetch,
    "nvd": nvd.fetch,
    "gnews": gnews.fetch,
    "bingnews": bingnews.fetch,
    "hn": hn.fetch,
    "telegram": telegram.fetch,
    "x": x.fetch,
    "html": html_article.fetch,
    "watch": watch.fetch,
}


def ingest_source(source: SourceConfig, session) -> tuple[int, int]:
    """Возвращает (новых документов, всего получено)."""
    if not source.enabled:
        log.info("[%s] skipped (disabled)", source.id)
        return 0, 0
    if source.type not in CONNECTORS:
        log.error("[%s] unknown connector %s", source.id, source.type)
        record_fetch(source.id, fetched=0, accepted=0, rejected=0, error=f"unknown type {source.type}")
        return 0, 0
    try:
        items = CONNECTORS[source.type](source)
    except Exception as exc:
        record_fetch(source.id, fetched=0, accepted=0, rejected=0, error=str(exc))
        raise
    # Один и тот же URL не грузим дважды. Похожие заголовки сохраняем и связываем event_key.
    existing_urls = {normalize_url(u) for u in session.scalars(select(Document.url)).all() if u}
    known_titles = [
        ((row[0] or ""), (row[1] or ""))
        for row in session.execute(select(Document.title, Document.event_key)).all()
        if row and row[0]
    ]
    added = 0
    rejected = 0
    duplicates = 0
    reviews = 0
    for item in items:
        if is_aggregator_url(item["url"]):
            continue
        url = normalize_url(item["url"])
        if not url or is_aggregator_url(url) or url in existing_urls:
            duplicates += 1
            continue
        text = f"{item['title']}\n{item['summary']}"
        decision, reason = triage_document(
            text,
            role=source.resolved_role(),
            source_name=source.name,
            source_id=source.id,
            filter_ai=source.filter_ai,
        )
        if decision == "reject":
            rejected += 1
            log_reject(
                url=url,
                title=item["title"],
                summary=item.get("summary") or "",
                source_id=source.id,
                role=source.resolved_role(),
                reason=reason,
                published_at=str(item.get("published_at") or ""),
            )
            continue
        meta = enrich(item["title"], item["summary"], source.source_type, source.id)
        severity = meta["severity"]
        if item.get("cvss") is not None:
            severity = max(severity, item["cvss"] / 10.0)
        event_key = cluster_event_key(item["title"], item.get("summary") or "", known_titles)
        doc = Document(
            source_id=source.id,
            source_name=(item.get("source_name") or source.name)[:128],
            source_type=source.source_type,
            doc_type=meta["doc_type"],
            url=url or item["url"],
            title=item["title"],
            summary=item["summary"],
            published_at=item["published_at"],
            trust=source.trust,
            severity=round(severity, 3),
            event_key=event_key,
            gate=decision,
        )
        doc.tags = meta["tags"]
        doc.entities = meta["entities"]
        # Fulltext только в score-tbsf (бюджет/throttle arXiv) — иначе CI тянет PDF по 3с/статью.
        apply_tbsf(doc, fetch_body=False)
        session.add(doc)
        existing_urls.add(url)
        known_titles.append((item["title"], event_key))
        if decision == "review":
            reviews += 1
        added += 1
    session.commit()
    status = getattr(source, "fetch_status", "") or ("empty" if not items else "ok")
    health = record_fetch(
        source.id,
        fetched=len(items),
        accepted=added,
        rejected=rejected,
        duplicates=duplicates,
        reviews=reviews,
        status=status,
    )
    if health.get("review"):
        log.warning("[%s] noise_rate=%.2f — candidate for review", source.id, health["noise_rate"])
    return added, len(items)


def retag_all() -> None:
    """Переразметка всех документов текущей таксономией (после ее обновления)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    with get_session() as session:
        load_trend_candidates(session)
        docs = session.scalars(select(Document)).all()
        for doc in docs:
            meta = enrich(doc.title, doc.summary, doc.source_type, doc.source_id)
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
