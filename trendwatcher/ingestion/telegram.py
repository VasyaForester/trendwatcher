"""Публичные посты Telegram через t.me/s/<channel>. Без Bot API."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from ..config import SourceConfig
from ..db import utcnow
from .common import http_get, strip_html

log = logging.getLogger("trendwatcher.telegram")

_MSG_RX = re.compile(
    r'data-post="(?P<chan>[^"/]+)/(?P<mid>\d+)".*?'
    r'(?P<body><div class="tgme_widget_message_text[^"]*"[^>]*>.*?</div>)',
    re.S,
)
_TIME_RX = re.compile(r'<time[^>]+datetime="([^"]+)"', re.S)
_HREF_RX = re.compile(r'href="(https?://[^"]+)"', re.I)
_SKIP_HOSTS = ("t.me", "telegram.me", "telegram.org")


def parse_channel_html(html: str, username: str) -> list[dict]:
    items: list[dict] = []
    for match in _MSG_RX.finditer(html or ""):
        mid = int(match.group("mid"))
        chunk = html[match.start() : match.end() + 800]
        text = strip_html(match.group("body"))
        if not text:
            continue
        time_m = _TIME_RX.search(chunk)
        published = utcnow()
        if time_m:
            try:
                published = datetime.fromisoformat(time_m.group(1).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                published = utcnow()
        permalink = f"https://t.me/{username}/{mid}"
        external = ""
        for href in _HREF_RX.findall(match.group("body")):
            if any(host in href for host in _SKIP_HOSTS):
                continue
            external = href
            break
        url = external or permalink
        summary = text[:4000]
        if external:
            summary = f"{summary}\n\nvia https://t.me/{username}/{mid}"
        items.append(
            {
                "url": url,
                "title": text[:180],
                "summary": summary,
                "published_at": published,
                "message_id": mid,
            }
        )
    items.sort(key=lambda it: it["message_id"], reverse=True)
    return items


def fetch(source: SourceConfig) -> list[dict]:
    username = (source.username or "").lstrip("@").strip()
    if not username:
        log.warning("[%s] telegram username missing", source.id)
        return []
    url = source.url or f"https://t.me/s/{username}"
    try:
        resp = http_get(url, timeout=20.0)
    except Exception as exc:  # noqa: BLE001 — один канал не должен ронять ingest
        log.warning("[%s] telegram fetch failed: %s", source.id, exc)
        return []
    return parse_channel_html(resp.text, username)[: source.max_results or 30]
