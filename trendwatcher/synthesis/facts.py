"""Детерминированный пакет фактов для обзора трендов."""

from __future__ import annotations

from datetime import timedelta

from ..analytics.constants import SIGNAL_WINDOW_WEEKS
from ..analytics.velocity import velocity_label
from ..db import utcnow
from ..enrichment.tag_filter import SIGNAL_AI_TAGS


LEVEL_RANK = {
    "strong": 0,
    "emerging": 1,
    "research": 2,
    "stable": 3,
    "spike": 4,
    "weak": 5,
    "declining": 6,
}


def tag_label(tag: str) -> str:
    return tag.replace("_", " ")


def _signal_summary(s: dict) -> dict:
    return {
        "tag": s["tag"],
        "label": tag_label(s["tag"]),
        "level": s.get("level", "weak"),
        "recent": s.get("recent", 0),
        "prior": s.get("prior", 0),
        "velocity": s.get("velocity", 0.0),
        "velocity_label": velocity_label(s.get("velocity", 0.0), s.get("velocity_source")),
        "reason": s.get("reason", ""),
        "category": s.get("category", "security"),
    }


def _pick_signals(signals: list[dict], category: str | None, limit: int) -> list[dict]:
    filtered = [s for s in signals if category is None or s.get("category") == category]
    # Для security важнее объём упоминаний («чаще всего звучат»), не level.
    if category == "security":
        filtered.sort(
            key=lambda s: (-s.get("recent", 0), LEVEL_RANK.get(s.get("level", "weak"), 99))
        )
    else:
        filtered.sort(
            key=lambda s: (
                LEVEL_RANK.get(s.get("level", "weak"), 99),
                -s.get("recent", 0),
                -(s.get("velocity") or 0),
            )
        )
    return [_signal_summary(s) for s in filtered[:limit]]


def _pick_ai_tech(signals: list[dict], limit: int = 6) -> list[dict]:
    """AI-тренды: whitelist SIGNAL_AI_TAGS + остальные ai_tech из сигналов."""
    pinned = [s for s in signals if s.get("tag") in SIGNAL_AI_TAGS]
    rest = [
        s
        for s in signals
        if s.get("category") == "ai_tech" and s.get("tag") not in SIGNAL_AI_TAGS
    ]
    pinned.sort(key=lambda s: (-s.get("recent", 0), -(s.get("velocity") or 0)))
    rest.sort(
        key=lambda s: (
            LEVEL_RANK.get(s.get("level", "weak"), 99),
            -s.get("recent", 0),
        )
    )
    merged = pinned + rest
    return [_signal_summary(s) for s in merged[:limit]]


def _pick_emerging(signals: list[dict], limit: int = 3) -> list[dict]:
    cand = [
        s
        for s in signals
        if s.get("level") in ("emerging", "research", "strong")
        and (s.get("velocity") or 0) >= 0
    ]
    cand.sort(key=lambda s: (-(s.get("velocity") or 0), -s.get("recent", 0)))
    return [_signal_summary(s) for s in cand[:limit]]


def _pick_declining_but_frequent(signals: list[dict], limit: int = 2) -> list[dict]:
    cand = [
        s
        for s in signals
        if s.get("category") == "security"
        and s.get("recent", 0) >= 5
        and (
            s.get("level") == "declining"
            or (s.get("velocity") or 0) < -0.1
            or s.get("level") == "stable"
        )
    ]
    cand.sort(key=lambda s: (-s.get("recent", 0), s.get("velocity") or 0))
    return [_signal_summary(s) for s in cand[:limit]]


def _pick_papers(top_events: list[dict], limit: int = 6) -> list[dict]:
    out = []
    for e in top_events[:limit]:
        out.append(
            {
                "title": e.get("title", "")[:200],
                "url": e.get("url", ""),
                "source_type": "research",
                "source_name": e.get("source_name", "arXiv"),
                "tags": (e.get("tags") or [])[:5],
                "tbsf_score": e.get("tbsf_score") or e.get("score"),
            }
        )
    return out


def _pick_vendor_news(feed: list[dict], limit: int = 6) -> list[dict]:
    cutoff = utcnow() - timedelta(weeks=SIGNAL_WINDOW_WEEKS)
    vendorish = []
    for d in feed:
        if d.get("source_type") not in ("vendor", "news", "standards"):
            continue
        pub = d.get("published_at")
        if pub:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(str(pub).replace("Z", ""))
                if dt < cutoff:
                    continue
            except ValueError:
                pass
        vendorish.append(d)

    vendorish.sort(
        key=lambda d: (
            0 if d.get("source_type") == "vendor" else 1,
            -_ts(d.get("published_at")),
        )
    )
    out = []
    for d in vendorish[:limit]:
        out.append(
            {
                "title": (d.get("title") or "")[:200],
                "url": d.get("url", ""),
                "source_type": d.get("source_type", "news"),
                "source_name": d.get("source_name", ""),
                "tags": (d.get("tags") or [])[:4],
            }
        )
    return out


def _ts(value) -> float:
    if not value:
        return 0.0
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "")).timestamp()
    except ValueError:
        return 0.0


def build_facts_pack(
    signals: list[dict],
    top_events: list[dict],
    feed: list[dict],
    *,
    window_weeks: int = SIGNAL_WINDOW_WEEKS,
) -> dict:
    """Собирает компактный JSON фактов для промпта и шаблона."""
    ai_tech = _pick_ai_tech(signals)
    security = _pick_signals(signals, "security", limit=8)
    emerging = _pick_emerging(signals)
    mature = _pick_declining_but_frequent(signals)
    papers = _pick_papers(top_events)
    vendor = _pick_vendor_news(feed)

    highlights = []
    seen = set()
    for s in ai_tech + emerging + security[:4]:
        if s["tag"] in seen:
            continue
        seen.add(s["tag"])
        highlights.append(
            {
                "tag": s["tag"],
                "level": s["level"],
                "velocity": s["velocity"],
                "recent": s["recent"],
            }
        )
        if len(highlights) >= 8:
            break

    sources = []
    for item in papers[:4] + vendor[:4]:
        if item.get("url"):
            sources.append(
                {
                    "title": item["title"],
                    "url": item["url"],
                    "source_type": item["source_type"],
                }
            )

    return {
        "window_weeks": window_weeks,
        "ai_tech_signals": ai_tech,
        "security_signals": security,
        "emerging_signals": emerging,
        "mature_or_declining": mature,
        "arxiv_papers": papers,
        "vendor_news": vendor,
        "highlights": highlights,
        "sources": sources,
    }
