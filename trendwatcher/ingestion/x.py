"""X/Twitter: официальный API, затем Nitter RSS, затем HTML. Отказ не роняет ingest."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import feedparser

from ..config import SourceConfig, load_x_backends
from ..db import utcnow
from .common import http_get, strip_html, struct_time_to_dt

log = logging.getLogger("trendwatcher.x")

_STATUS_RX = re.compile(r'href="(?:https://(?:twitter|x)\.com)?/?[^"]*/status/(\d+)"', re.I)
_TWEET_TEXT_RX = re.compile(
    r'class="tweet-content[^"]*"[^>]*>(.*?)</div>|data-testid="tweetText"[^>]*>(.*?)</div>',
    re.S,
)
_LINK_RX = re.compile(r'href="(https?://[^"]+)"', re.I)
_SKIP = ("twitter.com", "x.com", "nitter", "t.co/")


def _external_url(text: str, fallback: str) -> str:
    for href in _LINK_RX.findall(text or ""):
        if any(host in href for host in _SKIP):
            continue
        return href
    return fallback


def _from_api(username: str, token: str, limit: int) -> list[dict]:
    import httpx

    headers = {"Authorization": f"Bearer {token}", "User-Agent": "TrendWatcher/0.1"}
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        user_resp = client.get(f"https://api.x.com/2/users/by/username/{username}")
        user_resp.raise_for_status()
        uid = user_resp.json()["data"]["id"]
        tw = client.get(
            f"https://api.x.com/2/users/{uid}/tweets",
            params={
                "max_results": max(5, min(limit, 20)),
                "tweet.fields": "created_at,entities",
                "exclude": "retweets,replies",
            },
        )
        tw.raise_for_status()
        payload = tw.json()
    items = []
    for tweet in payload.get("data") or []:
        text = tweet.get("text") or ""
        if text.startswith("RT @"):
            continue
        tid = str(tweet.get("id") or "")
        permalink = f"https://x.com/{username}/status/{tid}"
        urls = [
            u.get("expanded_url") or u.get("url")
            for u in ((tweet.get("entities") or {}).get("urls") or [])
        ]
        external = next((u for u in urls if u and "twitter.com" not in u and "x.com" not in u), "")
        created = tweet.get("created_at")
        published = utcnow()
        if created:
            try:
                published = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                published = utcnow()
        items.append(
            {
                "url": external or permalink,
                "title": text[:180],
                "summary": text if not external else f"{text}\n\nvia {permalink}",
                "published_at": published,
            }
        )
    return items


def _from_rss(base: str, username: str) -> list[dict]:
    resp = http_get(f"{base.rstrip('/')}/{username}/rss", timeout=15.0)
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        title = strip_html(entry.get("title", ""))
        link = entry.get("link") or ""
        if not title:
            continue
        published = struct_time_to_dt(entry.get("published_parsed") or entry.get("updated_parsed")) or utcnow()
        summary = strip_html(entry.get("summary", ""))[:4000]
        items.append(
            {
                "url": _external_url(summary, link),
                "title": title[:180],
                "summary": summary or title,
                "published_at": published,
            }
        )
    return items


def _from_html(base: str, username: str) -> list[dict]:
    resp = http_get(f"{base.rstrip('/')}/{username}", timeout=15.0)
    html = resp.text
    items = []
    for mid in dict.fromkeys(_STATUS_RX.findall(html)):
        permalink = f"https://x.com/{username}/status/{mid}"
        items.append(
            {
                "url": permalink,
                "title": f"Post {mid} by @{username}",
                "summary": permalink,
                "published_at": utcnow(),
            }
        )
    return items


def fetch(source: SourceConfig) -> list[dict]:
    username = (source.username or "").lstrip("@").strip()
    if not username:
        log.warning("[%s] x username missing", source.id)
        return []
    limit = source.max_results or 15
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    errors: list[str] = []
    if token:
        try:
            items = _from_api(username, token, limit)
            if items:
                return items[:limit]
            errors.append("api empty")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"api {exc}")
            log.info("[%s] x api failed: %s", source.id, exc)
    backends = load_x_backends()
    for base in backends["nitter"]:
        try:
            items = _from_rss(base, username)
            if items:
                return items[:limit]
            errors.append(f"rss empty {base}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"rss {base} {exc}")
            log.info("[%s] nitter %s failed: %s", source.id, base, exc)
    for base in backends["html"]:
        try:
            items = _from_html(base, username)
            if items:
                return items[:limit]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"html {base} {exc}")
            log.info("[%s] x html %s failed: %s", source.id, base, exc)
    log.warning("[%s] x backends unavailable (%s)", source.id, "; ".join(errors) or "none configured")
    return []
