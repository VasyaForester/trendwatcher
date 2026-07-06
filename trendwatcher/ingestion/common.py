import re
from datetime import datetime, timezone

import httpx

USER_AGENT = "TrendWatcher/0.1 (AI security trend monitoring; research use)"
_TAG_RX = re.compile(r"<[^>]+>")
_WS_RX = re.compile(r"\s+")


def http_get(url: str, params: dict | None = None, timeout: float = 30.0) -> httpx.Response:
    resp = httpx.get(
        url,
        params=params,
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp


def strip_html(text: str) -> str:
    return _WS_RX.sub(" ", _TAG_RX.sub(" ", text or "")).strip()


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def struct_time_to_dt(st) -> datetime | None:
    if st is None:
        return None
    return datetime(*st[:6])
