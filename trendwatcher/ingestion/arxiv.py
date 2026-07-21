"""Коннектор arXiv API (Atom) для исследований по AI security."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import feedparser

from ..config import SourceConfig
from .common import http_get, strip_html, struct_time_to_dt
from .compact import SUMMARY_CAP, compact_summary

log = logging.getLogger("trendwatcher.ingest.arxiv")

API_URL = "https://export.arxiv.org/api/query"
PAGE_SIZE = 100
PAGE_PAUSE_SEC = 3.0


def _fmt_arxiv_ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def _parse_entries(feed, *, summary_cap: int = SUMMARY_CAP) -> list[dict]:
    items = []
    for entry in feed.entries:
        published = struct_time_to_dt(entry.get("published_parsed"))
        if published is None:
            continue
        items.append(
            {
                "url": entry.get("link"),
                "title": strip_html(entry.get("title", "")),
                "summary": compact_summary(
                    strip_html(entry.get("summary", "")), summary_cap
                ),
                "published_at": published,
            }
        )
    return items


def _query_page(
    search_query: str,
    *,
    start: int,
    max_results: int,
    summary_cap: int = SUMMARY_CAP,
    timeout: float = 60.0,
) -> list[dict]:
    resp = http_get(
        API_URL,
        params={
            "search_query": " ".join(search_query.split()),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": start,
            "max_results": max_results,
        },
        timeout=timeout,
    )
    return _parse_entries(feedparser.parse(resp.content), summary_cap=summary_cap)


def fetch(source: SourceConfig) -> list[dict]:
    """Свежий хвост: последние max_results (ежедневный ingest)."""
    return _query_page(
        source.query or "",
        start=0,
        max_results=source.max_results,
        summary_cap=4000,  # дневной ingest может держать длиннее до диеты
    )


def fetch_window(
    source: SourceConfig,
    submitted_from: datetime,
    submitted_to: datetime,
    *,
    max_results: int | None = None,
    summary_cap: int = SUMMARY_CAP,
) -> list[dict]:
    """Лёгкий хвост за окно дат — для ретроспективы сигналов."""
    base = (source.query or "").strip()
    date_clause = (
        f"submittedDate:[{_fmt_arxiv_ts(submitted_from)} TO {_fmt_arxiv_ts(submitted_to)}]"
    )
    search = f"({base}) AND {date_clause}" if base else date_clause
    limit = max_results if max_results is not None else source.max_results
    collected: list[dict] = []
    start = 0
    while start < limit:
        page = min(PAGE_SIZE, limit - start)
        batch = _query_page(search, start=start, max_results=page, summary_cap=summary_cap)
        if not batch:
            break
        collected.extend(batch)
        if len(batch) < page:
            break
        start += page
        time.sleep(PAGE_PAUSE_SEC)
    log.info(
        "[%s] window %s..%s fetched=%d",
        source.id,
        submitted_from.date(),
        submitted_to.date(),
        len(collected),
    )
    return collected
