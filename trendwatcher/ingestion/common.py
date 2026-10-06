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


def interleave(buckets: list[list], cap: int, per_query: int = 4) -> list:
    """Сначала по per_query из каждого запроса, затем добивает остаток. Так узкий дорк не теряется за широким."""
    if cap <= 0:
        return []
    out: list = []

    def take(row_index: int) -> bool:
        progressed = False
        for bucket in buckets:
            if row_index >= len(bucket) or len(out) >= cap:
                continue
            out.append(bucket[row_index])
            progressed = True
            if len(out) >= cap:
                return True
        return progressed

    for i in range(max(per_query, 0)):
        if not take(i):
            break
        if len(out) >= cap:
            return out
    i = per_query
    while len(out) < cap and take(i):
        i += 1
    return out


def struct_time_to_dt(st) -> datetime | None:
    if st is None:
        return None
    return datetime(*st[:6])
