"""Нормализация URL и отпечаток заголовка для дедупликации."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source",
}
_PUNCT_RX = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RX = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    """Канонический URL: без фрагмента, tracking-параметров, лишнего слэша."""
    if not url:
        return ""
    raw = url.strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or ""
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def title_fingerprint(title: str) -> str:
    """Грубый ключ заголовка для ловли перепечаток одной новости."""
    t = (title or "").lower().replace("ё", "е")
    t = _PUNCT_RX.sub(" ", t)
    t = _WS_RX.sub(" ", t).strip()
    return t[:180]
