"""TBSF-рейтинг arXiv и отдельный рейтинг событий AI Security TI."""

from datetime import timedelta
import re

from sqlalchemy import select

from ..db import Document, utcnow
from ..enrichment.taxonomy import AI_TECH_TAGS, SECURITY_TAGS
from ..relevance.classifier import classify_document
from ..relevance.editorial import editorial_reject_reason
from ..tbsf.arxiv_text import is_arxiv_url

_INCIDENT_RX = re.compile(
    r"breach|incident|compromis|exfiltrat|0-click|zero-day|exploited in the wild|in the wild",
    re.I,
)
_FRAMEWORK_RX = re.compile(r"\bowasp\b|\bnist\b|\bdasf\b|mitre atlas|taxonomy|framework", re.I)
_VULN_RX = re.compile(r"\bcve-\d{4}-\d+\b", re.I)


def _eligible(doc: Document) -> bool:
    """GenAI security, AI-тренды или хотя бы минимальная TBSF-релевантность."""
    if doc.tbsf_vector:
        return True
    if doc.tags and set(doc.tags) & (SECURITY_TAGS | AI_TECH_TAGS):
        return True
    return (doc.tbsf_score or 0) >= 18


def top_events(session, days: int = 30, limit: int = 15) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    docs = session.scalars(
        select(Document).where(
            Document.published_at >= since,
            Document.source_type == "research",
        )
    ).all()

    papers = [
        d for d in docs
        if is_arxiv_url(d.url)
        and d.tbsf_score is not None
        and _eligible(d)
    ]
    papers.sort(key=lambda d: d.tbsf_score or 0, reverse=True)

    return [
        {
            **doc.to_dict(),
            "score_type": "tbsf",
            "score": doc.tbsf_score,
            "score_label": doc.tbsf_level or "⚪",
            "corroboration": 0,
        }
        for doc in papers[:limit]
    ]


def _ti_score(doc: Document) -> tuple[int, list[str]]:
    text = f"{doc.title or ''}\n{doc.summary or ''}"
    score = 8
    reasons: list[str] = []
    if _INCIDENT_RX.search(text):
        score += 30
        reasons.append("incident_or_exploitation")
    if _VULN_RX.search(text):
        score += 22
        reasons.append("vulnerability")
    if _FRAMEWORK_RX.search(text):
        score += 18
        reasons.append("framework_or_standard")
    if doc.source_type in {"standards", "vulnerability"} or (doc.trust or 0) >= 0.85:
        score += 12
        reasons.append("authoritative_source")
    if is_arxiv_url(doc.url or "") and not reasons:
        score -= 6
    return score, reasons


def ti_events(session, days: int = 45, limit: int = 12) -> list[dict]:
    """События TI: инцидент, уязвимость или фреймворк, не только arXiv."""
    since = utcnow() - timedelta(days=days)
    docs = session.scalars(select(Document).where(Document.published_at >= since)).all()
    best: dict[str, tuple[int, list[str], Document]] = {}
    for doc in docs:
        if editorial_reject_reason(
            doc.title or "",
            doc.summary or "",
            source_name=doc.source_name or "",
            source_id=doc.source_id or "",
            url=doc.url or "",
        ):
            continue
        rel = classify_document(doc, use_llm=False)
        if not rel.in_feed():
            continue
        score, reasons = _ti_score(doc)
        if score < 20 or not reasons:
            continue
        key = (getattr(doc, "event_key", None) or "").strip() or (doc.url or "")
        current = best.get(key)
        if current is None or score > current[0]:
            best[key] = (score, reasons, doc)
    ranked = sorted(best.values(), key=lambda row: (row[0], row[2].published_at), reverse=True)
    out = []
    for score, reasons, doc in ranked[:limit]:
        out.append(
            {
                **doc.to_dict(),
                "score_type": "ti",
                "score": score,
                "score_label": "",
                "score_reasons": reasons,
                "event_key": getattr(doc, "event_key", "") or "",
                "corroboration": 0,
            }
        )
    return out
