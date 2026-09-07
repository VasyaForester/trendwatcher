"""Поиск Hacker News (Algolia). В корпус идёт url статьи, не страница HN."""

from __future__ import annotations

import logging
from datetime import timedelta

from dateutil import parser as dateparser

from ..config import SourceConfig
from ..db import utcnow
from .common import http_get, strip_html, to_naive_utc
from .resolve import is_aggregator_url, publisher_label


log = logging.getLogger("trendwatcher.ingest.hn")

API_URL = "https://hn.algolia.com/api/v1/search_by_date"


def fetch(source: SourceConfig) -> list[dict]:
    queries = source.search_queries()
    if not queries:
        log.warning("[%s] no search queries", source.id)
        return []

    since = int((utcnow() - timedelta(days=max(1, source.days_back))).timestamp())
    items: list[dict] = []
    seen: set[str] = set()
    cap = max(1, source.max_results)
    per_query = max(5, min(50, cap))
    for query in queries:
        try:
            resp = http_get(
                API_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": per_query,
                    "numericFilters": f"created_at_i>{since}",
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] hn query failed %r: %s", source.id, query, exc)
            continue
        for hit in resp.json().get("hits") or []:
            if len(items) >= cap:
                return items
            dest = (hit.get("url") or "").strip()
            title = strip_html(hit.get("title") or "")
            if not dest or not title or is_aggregator_url(dest) or dest in seen:
                continue
            created = hit.get("created_at")
            if not created:
                continue
            published = to_naive_utc(dateparser.parse(created))
            seen.add(dest)
            items.append(
                {
                    "url": dest,
                    "title": title,
                    "summary": strip_html(hit.get("story_text") or "")[:4000],
                    "published_at": published,
                    "source_name": publisher_label(dest, source.name),
                }
            )
    return items
