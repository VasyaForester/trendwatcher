"""Ретроспективный лёгкий backfill arXiv по окнам дат (~3 месяца).

Пишет в SQLite только метаданные (title/summary/tags), без full_text —
чтобы недели были сопоставимы по плотности, а БД не раздувалась.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from ..config import SourceConfig, load_sources
from ..db import Document, get_session, init_db, utcnow
from ..enrichment.tagger import enrich
from ..tbsf.batch import apply_tbsf
from . import arxiv
from .dedup import normalize_url, title_fingerprint

log = logging.getLogger("trendwatcher.backfill")

# Окна по 14 дней: достаточно для равномерного покрытия, меньше лимитов API.
CHUNK_DAYS = 14
CHUNK_PAUSE_SEC = 3.0
# На окно — потолок результатов на источник (лёгкий хвост).
PER_CHUNK_CAP = 250


def _arxiv_sources() -> list[SourceConfig]:
    return [s for s in load_sources() if s.type == "arxiv"]


def _iter_chunks(weeks: int) -> list[tuple[datetime, datetime]]:
    """Список (from, to) полуоткрытых окон от (now - weeks) до now."""
    end = utcnow()
    start = end - timedelta(weeks=weeks)
    chunks: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=CHUNK_DAYS), end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def ingest_items_light(source: SourceConfig, items: list[dict], session) -> int:
    """Как ingest_source, но без скачивания full_text (лёгкий хвост)."""
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
        meta = enrich(item["title"], item["summary"], source.source_type)
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
            severity=round(meta["severity"], 3),
        )
        doc.tags = meta["tags"]
        doc.entities = meta["entities"]
        apply_tbsf(doc, fetch_body=False)
        session.add(doc)
        existing_urls.add(url)
        if title_key:
            existing_titles.add(title_key)
        added += 1
    session.commit()
    return added


def backfill_arxiv_light(weeks: int = 13) -> dict:
    """Заполняет БД лёгкими arXiv-записями за последние `weeks` недель."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    sources = _arxiv_sources()
    chunks = _iter_chunks(weeks)
    total_added = 0
    total_fetched = 0
    with get_session() as session:
        for source in sources:
            for submitted_from, submitted_to in chunks:
                try:
                    items = arxiv.fetch_window(
                        source,
                        submitted_from,
                        submitted_to,
                        max_results=PER_CHUNK_CAP,
                    )
                    total_fetched += len(items)
                    added = ingest_items_light(source, items, session)
                    total_added += added
                    log.info(
                        "[%s] %s..%s fetched=%d added=%d",
                        source.id,
                        submitted_from.date(),
                        submitted_to.date(),
                        len(items),
                        added,
                    )
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    log.error(
                        "[%s] window %s..%s FAILED: %s",
                        source.id,
                        submitted_from.date(),
                        submitted_to.date(),
                        exc,
                    )
                time.sleep(CHUNK_PAUSE_SEC)
    return {
        "weeks": weeks,
        "chunks": len(chunks),
        "sources": len(sources),
        "fetched": total_fetched,
        "added": total_added,
    }
