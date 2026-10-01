"""Счётчики здоровья источников. Файл в data/ (не в git)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import DATA_DIR

HEALTH_PATH = DATA_DIR / "source_health.json"
REVIEW_NOISE_RATE = 0.90
REVIEW_MIN_FETCHED = 8


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _load() -> dict:
    if not HEALTH_PATH.is_file():
        return {"sources": {}}
    try:
        raw = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sources": {}}
    raw.setdefault("sources", {})
    return raw


def _save(payload: dict) -> None:
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_fetch(
    source_id: str,
    *,
    fetched: int,
    accepted: int,
    rejected: int,
    error: str = "",
) -> dict:
    payload = _load()
    row = payload["sources"].get(source_id) or {}
    row["last_attempt"] = _now()
    row["items_fetched"] = int(fetched)
    row["items_accepted"] = int(accepted)
    row["items_rejected"] = int(rejected)
    denom = fetched or 0
    row["reject_rate"] = round(rejected / denom, 3) if denom else 0.0
    row["noise_rate"] = row["reject_rate"]
    if error:
        row["last_error"] = error[:300]
        row["http_errors"] = int(row.get("http_errors") or 0) + 1
    else:
        row["last_success"] = _now()
        row["last_error"] = ""
    row["review"] = bool(denom >= REVIEW_MIN_FETCHED and row["noise_rate"] > REVIEW_NOISE_RATE)
    payload["sources"][source_id] = row
    _save(payload)
    return row
