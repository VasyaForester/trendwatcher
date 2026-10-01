"""Память гипотез на следующий квартал (Trend candidates).

Фраза запоминается при первом появлении. На сайт попадает только если в текущем
квартале она регулярна (несколько недель) и её доля в корпусе выше, чем в прошлом.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select

from ..config import DATA_DIR
from ..db import Document, utcnow
from .emerging import _is_junk_tag, phrase_discoveries
from .taxonomy import TAXONOMY


log = logging.getLogger("trendwatcher.candidates")

CANDIDATES_PATH = DATA_DIR / "archive" / "trend_candidates.json"
MIN_DOCS = 8
MIN_WEEKS = 3
SHARE_RATIO = 1.2
MAX_SHOW = 12
MAX_DOCS_UI = 25
MAX_MEMORY = 80


def _week_start(d: datetime) -> str:
    dd = d.date()
    return (dd - timedelta(days=dd.weekday())).isoformat()


def candidates_path(path: Path | None = None) -> Path:
    return path or CANDIDATES_PATH


def quarter_id(dt: datetime) -> str:
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def quarter_range(dt: datetime) -> tuple[datetime, datetime, str]:
    q = (dt.month - 1) // 3
    start = datetime(dt.year, q * 3 + 1, 1)
    if start.month == 10:
        end = datetime(dt.year + 1, 1, 1)
    else:
        end = datetime(dt.year, start.month + 3, 1)
    return start, end, quarter_id(dt)


def prior_quarter_range(current_start: datetime) -> tuple[datetime, datetime, str]:
    prev = current_start - timedelta(days=1)
    return quarter_range(prev)


def _pretty_label(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").replace("_", " ")).strip()
    if not s:
        return s
    return s[0].upper() + s[1:]


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def _fields(doc: Any) -> dict:
    if isinstance(doc, dict):
        return {
            "title": doc.get("title") or "",
            "summary": doc.get("summary") or "",
            "url": doc.get("url") or "",
            "published_at": _as_dt(doc.get("published_at")),
            "source_name": doc.get("source_name") or "",
            "doc_type": doc.get("doc_type") or "",
        }
    return {
        "title": getattr(doc, "title", None) or "",
        "summary": getattr(doc, "summary", None) or "",
        "url": getattr(doc, "url", None) or "",
        "published_at": _as_dt(getattr(doc, "published_at", None)),
        "source_name": getattr(doc, "source_name", None) or "",
        "doc_type": getattr(doc, "doc_type", None) or "",
    }


def _promoted(cur_docs: int, cur_weeks: int, cur_share: float, prior_share: float, prior_docs: int) -> bool:
    if cur_docs < MIN_DOCS or cur_weeks < MIN_WEEKS:
        return False
    if prior_docs <= 0 or prior_share <= 0:
        return True
    return cur_share >= prior_share * SHARE_RATIO and cur_share > prior_share


def _pack_docs(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: r["published_at"] or datetime.min, reverse=True)
    seen: set[str] = set()
    out: list[dict] = []
    for rec in rows:
        url = rec["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "title": rec["title"],
                "url": url,
                "published_at": rec["published_at"].isoformat() if rec["published_at"] else None,
                "source_name": rec["source_name"],
                "doc_type": rec["doc_type"],
            }
        )
        if len(out) >= MAX_DOCS_UI:
            break
    return out


def refresh_candidates(
    docs: Iterable[Any],
    *,
    now: datetime | None = None,
    path: Path | None = None,
) -> list[dict]:
    """Обновляет память и возвращает кандидатов для UI (с списками публикаций)."""
    now = now or utcnow()
    mem_path = candidates_path(path)
    cur_start, cur_end, cur_q = quarter_range(now)
    pri_start, pri_end, pri_q = prior_quarter_range(cur_start)

    catalog: dict[str, dict] = {}
    for item in _load_memory(mem_path):
        cid = str(item.get("id") or "")
        if not cid or cid in TAXONOMY:
            continue
        catalog[cid] = item

    stats: dict[str, dict] = defaultdict(
        lambda: {
            "cur": set(),
            "pri": set(),
            "cur_weeks": set(),
            "pri_weeks": set(),
            "rows": [],
            "last": None,
        }
    )
    cur_n = 0
    pri_n = 0
    for doc in docs:
        rec = _fields(doc)
        published = rec["published_at"]
        if published is None:
            continue
        if cur_start <= published < cur_end:
            bucket = "cur"
            cur_n += 1
        elif pri_start <= published < pri_end:
            bucket = "pri"
            pri_n += 1
        else:
            continue
        wk = _week_start(published)
        for disc in phrase_discoveries(rec["title"]):
            cid = disc["id"]
            if cid in TAXONOMY or _is_junk_tag({"tag": cid, "label": disc["label"]}):
                continue
            if cid not in catalog:
                catalog[cid] = {
                    "id": cid,
                    "label": _pretty_label(disc["label"]),
                    "first_seen": published.date().isoformat(),
                    "patterns": disc["patterns"],
                }
            else:
                catalog[cid].setdefault("patterns", disc["patterns"])
                catalog[cid].setdefault("label", _pretty_label(disc["label"]))
                seen = catalog[cid].get("first_seen")
                iso = published.date().isoformat()
                if not seen or iso < seen:
                    catalog[cid]["first_seen"] = iso
            st = stats[cid]
            key = rec["url"] or rec["title"]
            st[bucket].add(key)
            st[f"{bucket}_weeks"].add(wk)
            if bucket == "cur" and rec["url"]:
                st["rows"].append(rec)
            if st["last"] is None or published > st["last"]:
                st["last"] = published

    memory: list[dict] = []
    promoted: list[dict] = []
    for cid, item in catalog.items():
        st = stats.get(cid)
        if not st:
            continue
        cur_docs, pri_docs = len(st["cur"]), len(st["pri"])
        if cur_docs == 0 and pri_docs == 0:
            continue
        cur_weeks = len(st["cur_weeks"])
        cur_share = (cur_docs / cur_n) if cur_n else 0.0
        prior_share = (pri_docs / pri_n) if pri_n else 0.0
        last_pub = st["last"]
        first_seen = item.get("first_seen")
        if first_seen is None and last_pub:
            first_seen = last_pub.date().isoformat()
        stored = {
            "id": cid,
            "label": _pretty_label(item.get("label") or cid),
            "first_seen": first_seen,
            "last_seen": last_pub.date().isoformat() if last_pub else first_seen,
            "patterns": item.get("patterns") or [],
            "quarters": {
                pri_q: {"docs": pri_docs, "weeks_hit": len(st["pri_weeks"])},
                cur_q: {"docs": cur_docs, "weeks_hit": cur_weeks},
            },
        }
        memory.append(stored)
        if not _promoted(cur_docs, cur_weeks, cur_share, prior_share, pri_docs):
            continue
        promoted.append(
            {
                "id": cid,
                "label": stored["label"],
                "count": cur_docs,
                "prior_count": pri_docs,
                "weeks": cur_weeks,
                "quarter": cur_q,
                "prior_quarter": pri_q,
                "docs": _pack_docs(st["rows"]),
            }
        )

    memory.sort(key=lambda it: (-(it.get("quarters") or {}).get(cur_q, {}).get("docs", 0), it["id"]))
    memory = memory[:MAX_MEMORY]
    _save_memory(memory, mem_path)

    promoted.sort(key=lambda it: (-it["count"], it["label"]))
    seen_labels: set[str] = set()
    unique: list[dict] = []
    for item in promoted:
        key = item["label"].lower()
        if any(key in s or s in key for s in seen_labels):
            continue
        seen_labels.add(key)
        unique.append(item)
        if len(unique) >= MAX_SHOW:
            break
    log.info("trend candidates: %s", [c["id"] for c in unique])
    return unique


def _load_memory(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = list(raw.get("items") or [])
    return [it for it in items if not _is_junk_tag({"tag": it.get("id"), "label": it.get("label")})]


def _save_memory(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": utcnow().isoformat(), "items": items}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_trend_candidates(session, *, now: datetime | None = None, path: Path | None = None) -> list[dict]:
    """Считает кандидатов по документам текущей БД и обновляет память."""
    now = now or utcnow()
    cur_start, cur_end, _ = quarter_range(now)
    pri_start, _, _ = prior_quarter_range(cur_start)
    docs = session.scalars(
        select(Document).where(
            Document.published_at >= pri_start,
            Document.published_at < cur_end,
        )
    ).all()
    return refresh_candidates(docs, now=now, path=path)
