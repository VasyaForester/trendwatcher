"""Ретроспектива публикаций по темам блока «Сигналы».

Пишет в SQLite компактные записи (title + short summary + signal tags),
без full_text — чтобы покрыть весь год и не упереться в лимит ~100 MB.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from ..config import SourceConfig
from ..db import Document, get_session, init_db, utcnow
from ..enrichment.tagger import enrich
from ..tbsf.batch import apply_tbsf
from . import arxiv
from .compact import (
    SUMMARY_CAP,
    compact_stats,
    compact_summary,
    diet_documents,
    has_signal_tag,
    signal_tags_only,
    vacuum_db,
)
from .dedup import normalize_url, title_fingerprint

log = logging.getLogger("trendwatcher.backfill")

CHUNK_DAYS = 14
CHUNK_PAUSE_SEC = 3.0
PER_CHUNK_CAP = 250

# Узкий запрос под SIGNAL_TAGS — меньше мусора, меньше строк в БД.
SIGNAL_ARXIV_QUERY = """
(cat:cs.CR OR cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.MA) AND (
  abs:"prompt injection" OR abs:"jailbreak" OR abs:"LLM security" OR
  abs:"indirect prompt injection" OR abs:"data poisoning" OR
  abs:"model extraction" OR abs:"model theft" OR abs:"model stealing" OR
  abs:"red teaming" OR abs:"guardrail" OR abs:"agent security" OR
  abs:"multi-agent" OR abs:"agent swarm" OR abs:"RAG security" OR
  abs:"retrieval-augmented" OR abs:"model supply chain" OR abs:"MCP server" OR
  abs:"model context protocol" OR abs:"computer-use agent" OR
  abs:"self-evolving" OR abs:"self-improving agent" OR abs:"long context" OR
  abs:"agent memory" OR abs:"tool calling" OR abs:"tool-using agent" OR
  abs:"code generation security" OR abs:"autonomous cyber" OR
  abs:"multimodal injection" OR abs:"data exfiltration" OR
  abs:"model drift" OR abs:"agent identity" OR abs:"agent permissions" OR
  abs:"context poisoning" OR abs:"AI governance"
)
"""


def _signal_source() -> SourceConfig:
    return SourceConfig(
        id="arxiv_signal_backfill",
        name="arXiv — Signal topics (compact)",
        type="arxiv",
        source_type="research",
        trust=0.9,
        max_results=PER_CHUNK_CAP,
        query=SIGNAL_ARXIV_QUERY,
    )


def _year_bounds(year: int) -> tuple[datetime, datetime]:
    start = datetime(year, 1, 1)
    end = utcnow()
    year_end = datetime(year, 12, 31, 23, 59, 59)
    if end > year_end:
        end = year_end
    if end < start:
        raise ValueError(f"year {year} is in the future")
    return start, end


def _iter_chunks(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    chunks: list[tuple[datetime, datetime]] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=CHUNK_DAYS), end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def ingest_signal_items(source: SourceConfig, items: list[dict], session) -> tuple[int, int]:
    """Добавляет только документы с SIGNAL_TAGS; компактные поля."""
    existing_urls = {normalize_url(u) for u in session.scalars(select(Document.url)).all()}
    existing_titles = {
        title_fingerprint(t)
        for t in session.scalars(select(Document.title)).all()
        if title_fingerprint(t)
    }
    added = 0
    skipped_no_signal = 0
    for item in items:
        url = normalize_url(item["url"])
        title_key = title_fingerprint(item["title"])
        if not url or url in existing_urls:
            continue
        if title_key and title_key in existing_titles:
            continue
        summary = compact_summary(item.get("summary", ""), SUMMARY_CAP)
        meta = enrich(item["title"], summary, source.source_type)
        if not has_signal_tag(meta["tags"]):
            skipped_no_signal += 1
            continue
        doc = Document(
            source_id=source.id,
            source_name=source.name,
            source_type=source.source_type,
            doc_type=meta["doc_type"],
            url=url or item["url"],
            title=item["title"],
            summary=summary,
            published_at=item["published_at"],
            trust=source.trust,
            severity=round(meta["severity"], 3),
            full_text=None,
        )
        doc.tags = signal_tags_only(meta["tags"])
        doc.entities = []
        apply_tbsf(doc, fetch_body=False)
        session.add(doc)
        existing_urls.add(url)
        if title_key:
            existing_titles.add(title_key)
        added += 1
    session.commit()
    return added, skipped_no_signal


def backfill_signal_year(year: int = 2026) -> dict:
    """Заполняет БД компактными signal-публикациями за календарный год."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    start, end = _year_bounds(year)
    chunks = _iter_chunks(start, end)
    source = _signal_source()
    # Узкий SIGNAL-запрос один раз — без дублей с arxiv_ai_* из sources.yaml.
    total_fetched = 0
    total_added = 0
    total_skipped = 0
    before = compact_stats()

    with get_session() as session:
        diet_documents(session)
        for submitted_from, submitted_to in chunks:
            try:
                items = arxiv.fetch_window(
                    source,
                    submitted_from,
                    submitted_to,
                    max_results=PER_CHUNK_CAP,
                    summary_cap=SUMMARY_CAP,
                )
                total_fetched += len(items)
                added, skipped = ingest_signal_items(source, items, session)
                total_added += added
                total_skipped += skipped
                log.info(
                    "[%s] %s..%s fetched=%d added=%d no_signal=%d",
                    source.id,
                    submitted_from.date(),
                    submitted_to.date(),
                    len(items),
                    added,
                    skipped,
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                log.error(
                    "[%s] %s..%s FAILED: %s",
                    source.id,
                    submitted_from.date(),
                    submitted_to.date(),
                    exc,
                )
            time.sleep(CHUNK_PAUSE_SEC)
        diet_documents(session)

    vacuum_db()
    after = compact_stats()
    return {
        "year": year,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "chunks": len(chunks),
        "fetched": total_fetched,
        "added": total_added,
        "skipped_no_signal": total_skipped,
        "before": before,
        "after": after,
    }
