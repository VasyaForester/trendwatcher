"""Коннектор arXiv API (Atom) для исследований по AI security."""

import feedparser

from ..config import SourceConfig
from .common import http_get, strip_html, struct_time_to_dt

API_URL = "http://export.arxiv.org/api/query"


def fetch(source: SourceConfig) -> list[dict]:
    resp = http_get(
        API_URL,
        params={
            "search_query": " ".join(source.query.split()),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": source.max_results,
        },
        timeout=60.0,
    )
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        published = struct_time_to_dt(entry.get("published_parsed"))
        if published is None:
            continue
        items.append(
            {
                "url": entry.get("link"),
                "title": strip_html(entry.get("title", "")),
                "summary": strip_html(entry.get("summary", ""))[:4000],
                "published_at": published,
            }
        )
    return items
