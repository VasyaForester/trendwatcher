"""Поиск Google News RSS. В корпус идёт URL издателя, не обёртка Google."""

from __future__ import annotations

import logging
import time

import feedparser

from ..config import SourceConfig
from .common import strip_html, struct_time_to_dt
from .resolve import (
    GNEWS_COOKIES,
    GNEWS_HEADERS,
    gnews_client,
    is_aggregator_url,
    publisher_label,
    resolve_google_news_url,
    strip_publisher_suffix,
)


log = logging.getLogger("trendwatcher.ingest.gnews")

SEARCH_URL = "https://news.google.com/rss/search"
RESOLVE_PAUSE_SEC = 0.25


def fetch(source: SourceConfig) -> list[dict]:
    queries = source.search_queries()
    if not queries:
        log.warning("[%s] no search queries", source.id)
        return []

    raw: list[dict] = []
    seen_wrappers: set[str] = set()
    client = gnews_client()
    try:
        for query in queries:
            try:
                resp = client.get(
                    SEARCH_URL,
                    params={
                        "q": query,
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    },
                    headers=GNEWS_HEADERS,
                    cookies=GNEWS_COOKIES,
                )
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s] gnews query failed %r: %s", source.id, query, exc)
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                wrapper = (entry.get("link") or "").strip()
                title = strip_html(entry.get("title", ""))
                if not wrapper or not title or wrapper in seen_wrappers:
                    continue
                published = struct_time_to_dt(
                    entry.get("published_parsed") or entry.get("updated_parsed")
                )
                if published is None:
                    continue
                seen_wrappers.add(wrapper)
                src = entry.get("source") or {}
                publisher = ""
                if isinstance(src, dict):
                    publisher = src.get("title") or ""
                else:
                    publisher = getattr(src, "title", "") or str(src)
                raw.append(
                    {
                        "wrapper": wrapper,
                        "title": title,
                        "summary": strip_html(entry.get("summary", ""))[:4000],
                        "published_at": published,
                        "publisher": publisher.strip(),
                    }
                )

        items: list[dict] = []
        cap = max(1, source.max_results)
        for i, row in enumerate(raw):
            if len(items) >= cap:
                break
            if i:
                time.sleep(RESOLVE_PAUSE_SEC)
            dest = resolve_google_news_url(row["wrapper"], client=client)
            if not dest or is_aggregator_url(dest):
                continue
            title = strip_publisher_suffix(row["title"], row["publisher"])
            items.append(
                {
                    "url": dest,
                    "title": title,
                    "summary": row["summary"],
                    "published_at": row["published_at"],
                    "source_name": publisher_label(
                        dest, source.name, row["publisher"]
                    ),
                }
            )
        return items
    finally:
        client.close()
