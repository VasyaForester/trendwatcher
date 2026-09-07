"""Поиск Bing News RSS. В корпус идёт URL из параметра url=, не apiclick."""

from __future__ import annotations

import logging

import feedparser

from ..config import SourceConfig
from .common import http_get, strip_html, struct_time_to_dt
from .resolve import is_aggregator_url, publisher_label, unwrap_bing_url


log = logging.getLogger("trendwatcher.ingest.bingnews")

SEARCH_URL = "https://www.bing.com/news/search"


def fetch(source: SourceConfig) -> list[dict]:
    queries = source.search_queries()
    if not queries:
        log.warning("[%s] no search queries", source.id)
        return []

    items: list[dict] = []
    seen: set[str] = set()
    cap = max(1, source.max_results)
    for query in queries:
        try:
            resp = http_get(
                SEARCH_URL,
                params={"q": query, "format": "rss"},
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] bing query failed %r: %s", source.id, query, exc)
            continue
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            if len(items) >= cap:
                return items
            dest = unwrap_bing_url(entry.get("link") or "")
            if not dest or is_aggregator_url(dest) or dest in seen:
                continue
            title = strip_html(entry.get("title", ""))
            if not title:
                continue
            published = struct_time_to_dt(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            if published is None:
                continue
            publisher = strip_html(entry.get("news_source") or "")
            seen.add(dest)
            items.append(
                {
                    "url": dest,
                    "title": title,
                    "summary": strip_html(entry.get("summary", ""))[:4000],
                    "published_at": published,
                    "source_name": publisher_label(dest, source.name, publisher),
                }
            )
    return items
