"""Счётчики здоровья источников. Файл в data/ (не в git)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..config import DATA_DIR

HEALTH_PATH = DATA_DIR / "source_health.json"
ARCHIVE_HEALTH_PATH = DATA_DIR / "archive" / "source_health.json"
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
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    HEALTH_PATH.write_text(text, encoding="utf-8")
    ARCHIVE_HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_HEALTH_PATH.write_text(text, encoding="utf-8")


def record_fetch(
    source_id: str,
    *,
    fetched: int,
    accepted: int,
    rejected: int,
    error: str = "",
    duplicates: int = 0,
    reviews: int = 0,
    status: str = "",
) -> dict:
    payload = _load()
    row = payload["sources"].get(source_id) or {}
    row["last_attempt"] = _now()
    row["items_fetched"] = int(fetched)
    row["items_accepted"] = int(accepted)
    row["items_rejected"] = int(rejected)
    row["items_duplicates"] = int(duplicates)
    row["items_review"] = int(reviews)
    denom = fetched or 0
    row["reject_rate"] = round(rejected / denom, 3) if denom else 0.0
    row["noise_rate"] = row["reject_rate"]
    if error:
        row["status"] = "error"
        row["last_error"] = error[:300]
        row["http_errors"] = int(row.get("http_errors") or 0) + 1
    elif status in {"empty", "unavailable"} or fetched == 0:
        row["status"] = status or "empty"
        row["last_error"] = "" if row["status"] == "empty" else row.get("last_error") or "no usable items"
    else:
        row["status"] = status or "ok"
        row["last_success"] = _now()
        row["last_error"] = ""
    row["review"] = bool(denom >= REVIEW_MIN_FETCHED and row["noise_rate"] > REVIEW_NOISE_RATE)
    payload["sources"][source_id] = row
    _save(payload)
    return row


def public_report() -> dict:
    """Сводка для data.json. Без секретов и служебных конфигов."""
    payload = _load()
    if not payload.get("sources") and ARCHIVE_HEALTH_PATH.is_file():
        try:
            payload = json.loads(ARCHIVE_HEALTH_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"sources": {}}
    sources = []
    for source_id, row in sorted((payload.get("sources") or {}).items()):
        sources.append(
            {
                "source_id": source_id,
                "status": row.get("status") or "",
                "last_attempt": row.get("last_attempt") or "",
                "last_success": row.get("last_success") or "",
                "last_error": row.get("last_error") or "",
                "items_fetched": row.get("items_fetched") or 0,
                "items_accepted": row.get("items_accepted") or 0,
                "items_rejected": row.get("items_rejected") or 0,
                "items_duplicates": row.get("items_duplicates") or 0,
                "items_review": row.get("items_review") or 0,
            }
        )
    return {"sources": sources}
