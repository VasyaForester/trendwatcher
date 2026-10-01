"""Универсальный разбор HTML-индекса и статьи (JSON-LD / Open Graph).

Отдельный сайт не получает свой парсер: источник с type: html указывает index URL.
ETag хранится в data/http_cache.json и не коммитится.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from ..config import DATA_DIR, SourceConfig
from ..db import utcnow
from .common import strip_html

log = logging.getLogger("trendwatcher.html_article")

_CACHE = DATA_DIR / "http_cache.json"
_HREF_RX = re.compile(r'href="([^"]+)"', re.I)
_META_RX = re.compile(
    r'<meta[^>]+(?:property|name)="(?P<key>[^"]+)"[^>]+content="(?P<val>[^"]*)"',
    re.I,
)
_JSONLD_RX = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(?P<body>.*?)</script>',
    re.S | re.I,
)
_TIME_RX = re.compile(r"<time[^>]+datetime=\"([^\"]+)\"", re.I)


def article_links(html: str, base_url: str, limit: int = 20) -> list[str]:
    host = urlparse(base_url).netloc
    out: list[str] = []
    for href in _HREF_RX.findall(html or ""):
        if href.startswith("#") or href.startswith("mailto:"):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.netloc != host:
            continue
        if parsed.path.rstrip("/") in {"", "/"}:
            continue
        if abs_url not in out:
            out.append(abs_url)
        if len(out) >= limit:
            break
    return out


def parse_article(html: str, url: str) -> dict | None:
    meta = {m.group("key").lower(): m.group("val") for m in _META_RX.finditer(html or "")}
    title = meta.get("og:title") or ""
    summary = meta.get("og:description") or meta.get("description") or ""
    published_raw = meta.get("article:published_time") or ""
    for block in _JSONLD_RX.findall(html or ""):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            kind = str(node.get("@type") or "")
            if kind not in {"Article", "NewsArticle", "BlogPosting"} and "Article" not in kind:
                continue
            title = title or str(node.get("headline") or "")
            summary = summary or str(node.get("description") or "")
            published_raw = published_raw or str(node.get("datePublished") or "")
    if not title:
        time_m = _TIME_RX.search(html or "")
        if time_m and not published_raw:
            published_raw = time_m.group(1)
        return None
    published = utcnow()
    if published_raw:
        try:
            published = datetime.fromisoformat(published_raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            published = utcnow()
    return {
        "url": url,
        "title": strip_html(title)[:300],
        "summary": strip_html(summary)[:4000],
        "published_at": published,
    }


def fetch(source: SourceConfig) -> list[dict]:
    """Index → article pages. Ошибка одной страницы не роняет источник."""
    import httpx

    from .common import USER_AGENT

    if not source.url:
        return []
    cache = {}
    if _CACHE.is_file():
        try:
            cache = json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    headers = {"User-Agent": USER_AGENT}
    etag = (cache.get(source.url) or {}).get("etag")
    if etag:
        headers["If-None-Match"] = etag
    items: list[dict] = []
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
            index = client.get(source.url)
            if index.status_code == 304:
                return []
            index.raise_for_status()
            if index.headers.get("etag"):
                cache[source.url] = {"etag": index.headers["etag"]}
                _CACHE.parent.mkdir(parents=True, exist_ok=True)
                _CACHE.write_text(json.dumps(cache), encoding="utf-8")
            for link in article_links(index.text, str(index.url), limit=source.max_results or 15):
                try:
                    page = client.get(link)
                    page.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    log.info("[%s] skip %s: %s", source.id, link, exc)
                    continue
                parsed = parse_article(page.text, str(page.url))
                if parsed:
                    items.append(parsed)
    except Exception as exc:  # noqa: BLE001
        log.warning("[%s] html fetch failed: %s", source.id, exc)
        return []
    return items
