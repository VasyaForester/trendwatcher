"""Наблюдение за страницей без RSS.

Первый успешный ответ только запоминает хеш. Документ появляется, когда содержимое изменилось.
Неизменившаяся страница не становится новым событием.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from ..config import DATA_DIR, SourceConfig
from ..db import utcnow
from .common import http_get, strip_html

log = logging.getLogger("trendwatcher.watch")

STATE_PATH = DATA_DIR / "archive" / "page_watch.json"
_TITLE_RX = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _load() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch(source: SourceConfig) -> list[dict]:
    if not source.url:
        raise RuntimeError("watch source has no url")
    resp = http_get(source.url, timeout=25.0)
    digest = hashlib.sha256(resp.content).hexdigest()
    state = _load()
    prev = state.get(source.id) or {}
    state[source.id] = {"hash": digest, "url": source.url, "seen_at": utcnow().isoformat()}
    _save(state)
    if not prev or prev.get("hash") == digest:
        return []
    title_m = _TITLE_RX.search(resp.text or "")
    title = strip_html(title_m.group(1)) if title_m else source.name
    return [
        {
            "url": f"{source.url}#changed-{digest[:12]}",
            "title": f"{source.name}: {title}"[:180],
            "summary": f"Page content changed: {source.url}",
            "published_at": utcnow(),
        }
    ]
