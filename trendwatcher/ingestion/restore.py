"""Восстановление компактной SQLite-БД из append-only ledger в Git.

CI не хранит trendwatcher.db (лимит GitHub). Исторический корпус живёт в
data/archive/documents.jsonl — перед ежедневным ingest восстанавливаем БД,
чтобы data.json не сжимался до «свежего хвоста».
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, select

from ..analytics.archive import DOC_LEDGER, MANIFEST, _load_manifest, _save_manifest
from ..db import DB_PATH, Document, get_session, init_db, utcnow
from ..ingestion.compact import SUMMARY_CAP, compact_summary, diet_documents, vacuum_db
from ..tbsf.batch import apply_tbsf

log = logging.getLogger("trendwatcher.restore")


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return utcnow()
    return datetime.fromisoformat(value.replace("Z", ""))


def restore_db_from_ledger(
    ledger_path: Path | None = None,
    *,
    replace: bool = True,
) -> dict:
    """Собирает SQLite из JSONL. replace=True — полная пересборка."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    path = ledger_path or DOC_LEDGER
    if not path.exists():
        raise FileNotFoundError(f"ledger not found: {path}")

    init_db()
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    # Дедуп по URL (последняя запись побеждает).
    by_url: dict[str, dict] = {}
    for row in rows:
        url = (row.get("url") or "").strip()
        if url:
            by_url[url] = row
    rows = list(by_url.values())

    with get_session() as session:
        if replace:
            session.execute(delete(Document))
            session.commit()

        existing = set(session.scalars(select(Document.url)).all())
        added = 0
        for row in rows:
            url = row.get("url") or ""
            if not url or url in existing:
                continue
            doc = Document(
                source_id=row.get("source_id") or "ledger",
                source_name=row.get("source_name") or row.get("source_id") or "ledger",
                source_type=row.get("source_type") or "research",
                doc_type=row.get("doc_type") or "research",
                url=url,
                title=row.get("title") or "",
                summary=compact_summary(row.get("summary") or "", SUMMARY_CAP),
                published_at=_parse_dt(row.get("published_at")),
                fetched_at=_parse_dt(row.get("fetched_at")),
                trust=float(row.get("trust", 0.7)),
                severity=float(row.get("severity", 0.0)),
                full_text=None,
            )
            doc.tags = row.get("tags") or []
            doc.entities = []
            if doc.source_type == "research":
                apply_tbsf(doc, fetch_body=False)
            session.add(doc)
            existing.add(url)
            added += 1
            if added % 500 == 0:
                session.commit()
                log.info("restored %d…", added)
        session.commit()
        diet_documents(session)
        total = session.scalar(select(func.count(Document.id))) or 0
        max_id = session.scalar(select(func.max(Document.id))) or 0

    vacuum_db()
    manifest = _load_manifest()
    manifest["last_doc_id"] = max_id
    manifest["weeks_in_archive"] = manifest.get("weeks_in_archive", 0)
    _save_manifest(manifest)

    size_mb = DB_PATH.stat().st_size / (1024 * 1024) if DB_PATH.exists() else 0.0
    return {
        "ledger_rows": len(rows),
        "added": added,
        "documents": total,
        "size_mb": round(size_mb, 2),
        "db_path": str(DB_PATH),
    }
