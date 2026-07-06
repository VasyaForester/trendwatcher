"""Коннектор RSS/Atom-лент (новости, блоги вендоров, advisories)."""

import feedparser

from ..config import SourceConfig
from .common import http_get, strip_html, struct_time_to_dt


def fetch(source: SourceConfig) -> list[dict]:
    resp = http_get(source.url)
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        url = entry.get("link")
        title = strip_html(entry.get("title", ""))
        if not url or not title:
            continue
        published = struct_time_to_dt(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        if published is None:
            continue
        items.append(
            {
                "url": url,
                "title": title,
                "summary": strip_html(entry.get("summary", ""))[:4000],
                "published_at": published,
            }
        )
    return items
