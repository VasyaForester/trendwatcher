"""Архив корпуса: замороженные недельные снимки + append-only реестр публикаций.

Проблема: при каждом ingest в БД доезжают «старые» arXiv/RSS и меняется разметка —
пересчёт по живой БД даёт нереалистичный velocity (+1000%).

Решение: фиксируем снимок корпуса за каждую завершённую неделю в Git (immutable).
Динамика сравнивается с архивом, а не с пересчитанной историей в SQLite.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ..config import DATA_DIR
from ..db import Document, utcnow
from .constants import SIGNAL_WINDOW_WEEKS
from .timeseries import week_start
from .velocity import pct_change

ARCHIVE_DIR = DATA_DIR / "archive"
WEEKLY_STATS = ARCHIVE_DIR / "weekly_stats.json"
DOC_LEDGER = ARCHIVE_DIR / "documents.jsonl"
MANIFEST = ARCHIVE_DIR / "manifest.json"


def _ensure_dirs() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"last_doc_id": 0}
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(manifest: dict) -> None:
    _ensure_dirs()
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def _load_weekly_stats() -> dict:
    if not WEEKLY_STATS.exists():
        return {"version": 1, "weeks": {}}
    with open(WEEKLY_STATS, encoding="utf-8") as f:
        return json.load(f)


def _save_weekly_stats(data: dict) -> None:
    _ensure_dirs()
    data["updated_at"] = utcnow().isoformat()
    with open(WEEKLY_STATS, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def week_snapshot(session, week: date) -> dict:
    """Снимок корпуса за календарную неделю (пн–вс) по published_at."""
    start = week
    end = week + timedelta(days=7)
    docs = session.scalars(
        select(Document).where(
            Document.published_at >= datetime.combine(start, datetime.min.time()),
            Document.published_at < datetime.combine(end, datetime.min.time()),
        )
    ).all()

    tag_counts: dict[str, int] = defaultdict(int)
    by_source_type: dict[str, int] = defaultdict(int)
    for doc in docs:
        by_source_type[doc.source_type] += 1
        for tag in doc.tags:
            tag_counts[tag] += 1

    total = len(docs)
    tags = {
        tag: {"count": cnt, "share": round(cnt / total, 6) if total else 0.0}
        for tag, cnt in sorted(tag_counts.items())
    }
    return {
        "week_start": start.isoformat(),
        "captured_at": utcnow().isoformat(),
        "documents": total,
        "by_source_type": dict(by_source_type),
        "tags": tags,
    }


def last_complete_week_start(now: datetime | None = None) -> date:
    now = now or utcnow()
    return week_start(now) - timedelta(days=7)


def iter_weeks_between(first: date, last: date):
    cur = first
    while cur <= last:
        yield cur
        cur += timedelta(days=7)


def backfill_weekly_snapshots(session, max_weeks: int = 104) -> int:
    """Добавляет снимки завершённых недель, которых ещё нет. Старые недели не перезаписываются."""
    stats = _load_weekly_stats()
    existing = stats.get("weeks", {})

    first_pub = session.scalar(select(Document.published_at).order_by(Document.published_at).limit(1))
    if not first_pub:
        return 0
    first_week = week_start(first_pub)
    last_week = last_complete_week_start()
    # Не углубляемся дальше max_weeks — для трендов хватает ~2 лет архива
    earliest = max(first_week, last_week - timedelta(weeks=max_weeks))

    written = 0
    for week in iter_weeks_between(earliest, last_week):
        key = week.isoformat()
        if key in existing:
            continue
        snap = week_snapshot(session, week)
        if snap["documents"] == 0:
            continue
        existing[key] = snap
        written += 1

    stats["weeks"] = existing
    _save_weekly_stats(stats)
    return written


def rebuild_weekly_snapshots(session, weeks: int = 52) -> int:
    """Перезаписывает снимки последних N завершённых недель (после signal backfill)."""
    stats = _load_weekly_stats()
    existing = stats.get("weeks", {})
    last = last_complete_week_start()
    earliest = last - timedelta(weeks=weeks - 1)
    written = 0
    for week in iter_weeks_between(earliest, last):
        snap = week_snapshot(session, week)
        if snap["documents"] == 0:
            continue
        existing[week.isoformat()] = snap
        written += 1
    stats["weeks"] = existing
    _save_weekly_stats(stats)
    return written


def load_weekly_snapshots() -> list[dict]:
    stats = _load_weekly_stats()
    weeks = stats.get("weeks", {})
    return [weeks[k] for k in sorted(weeks)]


def append_document_ledger(session) -> int:
    """Append-only экспорт новых документов с тегами."""
    from sqlalchemy import func

    _ensure_dirs()
    manifest = _load_manifest()
    last_id = manifest.get("last_doc_id", 0)
    max_id = session.scalar(select(func.max(Document.id))) or 0
    if last_id > max_id:
        if DOC_LEDGER.exists():
            DOC_LEDGER.write_text("", encoding="utf-8")
        last_id = 0
    docs = session.scalars(
        select(Document).where(Document.id > last_id).order_by(Document.id)
    ).all()
    if not docs:
        return 0
    with open(DOC_LEDGER, "a", encoding="utf-8") as f:
        for doc in docs:
            row = {
                "id": doc.id,
                "url": doc.url,
                "title": doc.title,
                "summary": doc.summary[:500],
                "published_at": doc.published_at.isoformat(),
                "fetched_at": doc.fetched_at.isoformat(),
                "source_id": doc.source_id,
                "source_type": doc.source_type,
                "doc_type": doc.doc_type,
                "tags": doc.tags,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            last_id = doc.id
    manifest["last_doc_id"] = last_id
    manifest["weeks_in_archive"] = len(_load_weekly_stats().get("weeks", {}))
    _save_manifest(manifest)
    return len(docs)


def archive_tag_windows(recent_weeks: int = SIGNAL_WINDOW_WEEKS) -> dict[str, dict]:
    snaps = load_weekly_snapshots()
    need = recent_weeks * 2
    if len(snaps) < need:
        return {}

    recent_snaps = snaps[-recent_weeks:]
    prior_snaps = snaps[-need:-recent_weeks]

    def aggregate(week_list: list[dict]) -> tuple[dict[str, int], int]:
        tags: dict[str, int] = defaultdict(int)
        total = 0
        for snap in week_list:
            total += snap.get("documents", 0)
            for tag, meta in snap.get("tags", {}).items():
                tags[tag] += meta.get("count", 0)
        return dict(tags), total

    recent_tags, recent_total = aggregate(recent_snaps)
    prior_tags, prior_total = aggregate(prior_snaps)

    out: dict[str, dict] = {}
    for tag in set(recent_tags) | set(prior_tags):
        r, p = recent_tags.get(tag, 0), prior_tags.get(tag, 0)
        recent_share = r / recent_total if recent_total else None
        prior_share = p / prior_total if prior_total else None
        share_velocity = pct_change(recent_share, prior_share) if (
            recent_share is not None and prior_share is not None
        ) else None
        out[tag] = {
            "recent": r,
            "prior": p,
            "recent_share": recent_share,
            "prior_share": prior_share,
            "share_velocity": share_velocity,
            "archive_weeks": len(snaps),
        }
    return out


def update_archive(session, *, rebuild_weeks: int | None = None) -> dict:
    ledger = append_document_ledger(session)
    if rebuild_weeks:
        weeks = rebuild_weekly_snapshots(session, weeks=rebuild_weeks)
    else:
        weeks = backfill_weekly_snapshots(session)
    snaps = load_weekly_snapshots()
    return {
        "ledger_appended": ledger,
        "weeks_written": weeks,
        "weeks_total": len(snaps),
        "rebuilt": bool(rebuild_weeks),
    }
