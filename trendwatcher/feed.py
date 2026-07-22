"""Лента новостей: без arXiv; только AI-security события; дедуп + разнообразие."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from .db import Document
from .enrichment.tagger import is_feed_relevant
from .ingestion.dedup import normalize_url, title_fingerprint, titles_near_duplicate
from .tbsf.arxiv_text import is_arxiv_url

FEED_SCAN_LIMIT = 8000
# Доля CVE/vulnerability в выдаче — не больше четверти (иначе NVD забивает ленту).
MAX_CVE_SHARE = 0.25


def _feed_eligible(doc: Document) -> bool:
    text = f"{doc.title}\n{doc.summary}"
    return is_feed_relevant(text, doc.tags or [], source_name=doc.source_name or "")


def _is_cve_like(doc: Document) -> bool:
    if doc.source_type == "vulnerability" or doc.doc_type == "vulnerability":
        return True
    title = (doc.title or "").lstrip()
    return title.upper().startswith("CVE-")


def _round_robin_by_source(docs: list[Document]) -> list[Document]:
    """Чередует источники, внутри источника — свежие первыми."""
    buckets: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        key = d.source_id or d.source_name or "unknown"
        buckets[key].append(d)
    for key in buckets:
        buckets[key].sort(key=lambda x: x.published_at, reverse=True)

    out: list[Document] = []
    while buckets:
        for key in list(buckets.keys()):
            out.append(buckets[key].pop(0))
            if not buckets[key]:
                del buckets[key]
    return out


def diversify_feed(docs: list[Document], limit: int) -> list[Document]:
    """Смешивает новости/инциденты с CVE: квота CVE и round-robin по источникам."""
    if limit <= 0:
        return []
    cves = [d for d in docs if _is_cve_like(d)]
    others = [d for d in docs if not _is_cve_like(d)]
    cves.sort(key=lambda d: d.published_at, reverse=True)
    others = _round_robin_by_source(others)

    max_cves = max(1, int(limit * MAX_CVE_SHARE)) if cves else 0
    # Если не-CVE мало — не оставляем ленту пустой: можно чуть поднять потолок CVE.
    if len(others) < limit * 0.5:
        max_cves = max(max_cves, min(len(cves), limit - len(others)))

    result: list[Document] = []
    oi = ci = 0
    while len(result) < limit and (oi < len(others) or ci < min(len(cves), max_cves)):
        for _ in range(3):
            if oi < len(others) and len(result) < limit:
                result.append(others[oi])
                oi += 1
        if ci < len(cves) and ci < max_cves and len(result) < limit:
            result.append(cves[ci])
            ci += 1
        if oi >= len(others) and (ci >= min(len(cves), max_cves) or ci >= len(cves)):
            break
        # Только CVE остались
        if oi >= len(others):
            while ci < len(cves) and ci < max_cves and len(result) < limit:
                result.append(cves[ci])
                ci += 1
            break
    return result


def build_feed(session, limit: int = 600) -> list[dict]:
    docs = session.scalars(
        select(Document).order_by(Document.published_at.desc()).limit(FEED_SCAN_LIMIT)
    ).all()

    eligible: list[Document] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_title_raw: list[str] = []
    for d in docs:
        if d.source_type == "research" or is_arxiv_url(d.url):
            continue
        if not _feed_eligible(d):
            continue
        url_key = normalize_url(d.url)
        title_key = title_fingerprint(d.title)
        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if any(titles_near_duplicate(d.title, prev) for prev in seen_title_raw):
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        seen_title_raw.append(d.title or "")
        eligible.append(d)

    mixed = diversify_feed(eligible, limit)
    return [d.to_dict() for d in mixed]
