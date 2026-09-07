"""Разворачивание агрегаторских ссылок до URL издателя.

Google News / Bing News / HN используем только как поиск. В корпус
попадает страница статьи, не SERP и не обёртка news.google.com.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx


log = logging.getLogger("trendwatcher.ingest.resolve")

GNEWS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TrendWatcher/0.1; "
        "+https://aitrendwatcher.ru) AppleWebKit/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://news.google.com/",
}
GNEWS_COOKIES = {
    "CONSENT": "YES+cb.20210420-08-p0.en+FX+111",
    "SOCS": "CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyzBg",
}
_BATCH_EXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_SIG_RX = re.compile(r'data-n-a-sg="([^"]+)"')
_TS_RX = re.compile(r'data-n-a-ts="([^"]+)"')
_GART_RX = re.compile(r'garturlres","(https?://[^\\"]+)"')

# Хосты, которые нельзя сохранять как итоговый URL документа.
_BLOCKED_HOSTS = {
    "news.google.com",
    "consent.google.com",
    "hn.algolia.com",
}


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_http_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_aggregator_url(url: str | None) -> bool:
    """True, если ссылка ведёт на выдачу/обёртку, а не на статью издателя."""
    if not url or not is_http_url(url):
        return True
    host = _host(url)
    path = urlparse(url).path.lower()
    if host in _BLOCKED_HOSTS:
        return True
    if host in {"google.com", "google.ru"} and path.startswith(
        ("/url", "/search", "/rss")
    ):
        return True
    if host.endswith("bing.com") and (
        "apiclick" in path or path.startswith("/news") or "/news/" in path
    ):
        return True
    if host == "news.ycombinator.com" and path.startswith("/item"):
        return True
    return False


def unwrap_bing_url(url: str) -> str | None:
    """Достаёт publisher URL из bing.com/news/apiclick.aspx?url=..."""
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if not host.endswith("bing.com"):
        return url if is_http_url(url) and not is_aggregator_url(url) else None
    dest = parse_qs(parsed.query).get("url", [None])[0]
    if not dest:
        return None
    dest = unquote(dest)
    return dest if is_http_url(dest) and not is_aggregator_url(dest) else None


def strip_publisher_suffix(title: str, publisher: str | None) -> str:
    title = (title or "").strip()
    pub = (publisher or "").strip()
    if pub:
        for sep in (" - ", " — ", " | "):
            suffix = f"{sep}{pub}"
            if title.endswith(suffix):
                return title[: -len(suffix)].strip()
    return title


def publisher_label(url: str, fallback: str, rss_source: str | None = None) -> str:
    name = (rss_source or "").strip()
    if name:
        return name[:128]
    host = _host(url)
    return (host or fallback)[:128]


def _parse_garturlres(body: str) -> str | None:
    text = body or ""
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[-1]
    text = text.lstrip()
    head, _, tail = text.partition("\n")
    if head.strip().isdigit():
        text = tail
    try:
        envelopes = json.loads(text)
    except json.JSONDecodeError:
        match = _GART_RX.search(body or "")
        return match.group(1) if match else None
    rows = envelopes if isinstance(envelopes, list) else []
    for env in rows:
        if not (isinstance(env, list) and len(env) >= 3):
            continue
        if env[0] != "wrb.fr" or env[1] != "Fbv4je":
            continue
        payload = env[2]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                match = _GART_RX.search(payload)
                return match.group(1) if match else None
        if isinstance(payload, list) and payload and payload[0] == "garturlres":
            dest = payload[1] if len(payload) > 1 else None
            if isinstance(dest, str) and is_http_url(dest):
                return dest
    match = _GART_RX.search(body or "")
    return match.group(1) if match else None


def gnews_client() -> httpx.Client:
    return httpx.Client(
        headers=GNEWS_HEADERS,
        cookies=GNEWS_COOKIES,
        follow_redirects=True,
        timeout=20.0,
    )


def resolve_google_news_url(
    url: str,
    client: httpx.Client | None = None,
) -> str | None:
    """CBMi-обёртка Google News → URL статьи. None, если развернуть не удалось."""
    if not url:
        return None
    if not is_aggregator_url(url):
        return url
    if _host(url) != "news.google.com":
        return None
    article_id = url.rstrip("/").split("/")[-1].split("?")[0]
    if not article_id:
        return None

    own_client = client is None
    http = client or gnews_client()
    try:
        page = http.get(url)
        sig = _SIG_RX.search(page.text or "")
        ts = _TS_RX.search(page.text or "")
        if not sig or not ts:
            log.debug("gnews: no signature for %s", article_id[:24])
            return None
        rpc_inner = json.dumps(
            [
                "garturlreq",
                [
                    [
                        "X",
                        "X",
                        ["X", "X"],
                        None,
                        None,
                        1,
                        1,
                        "US:en",
                        None,
                        1,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        1,
                    ],
                    "X",
                    "X",
                    1,
                    [1, 1, 1],
                    1,
                    1,
                    None,
                    0,
                    0,
                    None,
                    0,
                ],
                article_id,
                int(ts.group(1)),
                sig.group(1),
            ],
            separators=(",", ":"),
        )
        f_req = json.dumps(
            [[["Fbv4je", rpc_inner, None, "generic"]]], separators=(",", ":")
        )
        post = http.post(
            _BATCH_EXECUTE_URL,
            data={"f.req": f_req},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": GNEWS_HEADERS["User-Agent"],
                "Referer": "https://news.google.com/",
            },
        )
        dest = _parse_garturlres(post.text or "")
        if dest and not is_aggregator_url(dest):
            return dest
        log.debug("gnews: unresolved %s", article_id[:24])
        return None
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        log.debug("gnews: resolve failed %s: %s", article_id[:24], exc)
        return None
    finally:
        if own_client:
            http.close()
