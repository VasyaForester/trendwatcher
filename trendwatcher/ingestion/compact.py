"""Компактное хранение корпуса для сигналов (без раздувания SQLite).

Правила:
- full_text никогда не храним для ретроспективы сигналов;
- summary обрезаем до SUMMARY_CAP (теггеру хватает);
- entities не храним;
- в tags оставляем только SIGNAL_TAGS.
"""

from __future__ import annotations

from sqlalchemy import func, select, text

from ..db import Document, engine, get_session, init_db
from ..enrichment.tag_filter import SIGNAL_TAGS, is_signal_tag

SUMMARY_CAP = 500


def compact_summary(text: str, limit: int = SUMMARY_CAP) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def signal_tags_only(tags: list[str]) -> list[str]:
    return [t for t in tags if is_signal_tag(t)]


def has_signal_tag(tags: list[str]) -> bool:
    return any(is_signal_tag(t) for t in tags)


def diet_documents(session, *, summary_cap: int = SUMMARY_CAP) -> dict:
    """Сжимает уже лежащие документы: без full_text, короткий summary, без entities."""
    docs = session.scalars(select(Document)).all()
    changed = 0
    dropped_ft = 0
    for doc in docs:
        dirty = False
        if doc.full_text:
            doc.full_text = None
            dropped_ft += 1
            dirty = True
        compact = compact_summary(doc.summary, summary_cap)
        if compact != doc.summary:
            doc.summary = compact
            dirty = True
        if doc.entities_json and doc.entities_json != "[]":
            doc.entities = []
            dirty = True
        # Исторический research для сигналов — оставляем только SIGNAL_TAGS,
        # если после фильтра тег ещё есть; лента/новости не трогаем по тегам.
        if doc.source_type == "research" and doc.tags:
            slim = signal_tags_only(doc.tags)
            if slim and slim != doc.tags:
                doc.tags = slim
                dirty = True
        if dirty:
            changed += 1
    session.commit()
    return {"changed": changed, "dropped_full_text": dropped_ft, "total": len(docs)}


def vacuum_db() -> None:
    """Пересобирает файл SQLite после диеты."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("VACUUM"))


def db_size_mb() -> float:
    from ..db import DB_PATH

    if not DB_PATH.exists():
        return 0.0
    return DB_PATH.stat().st_size / (1024 * 1024)


def compact_stats() -> dict:
    init_db()
    with get_session() as session:
        total = session.scalar(select(func.count(Document.id))) or 0
        with_ft = (
            session.scalar(
                select(func.count(Document.id)).where(Document.full_text.is_not(None))
            )
            or 0
        )
        research = (
            session.scalar(
                select(func.count(Document.id)).where(Document.source_type == "research")
            )
            or 0
        )
    return {
        "documents": total,
        "research": research,
        "with_full_text": with_ft,
        "size_mb": round(db_size_mb(), 2),
        "signal_tags": sorted(SIGNAL_TAGS),
    }
