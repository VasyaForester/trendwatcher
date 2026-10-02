"""Редакционные правила ленты по разметке 2026-10-02.

В сводку попадает один оригинал события: инцидент, AI-specific уязвимость,
релиз защитного механизма. Не попадают колонки, чужие разборы, учебные стенды,
обычные веб-CVE и повтор той же истории.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_OPINION_RX = re.compile(
    r"\bwebinar\b|"
    r"\bwhy .{0,50}\bmatters\b|"
    r"\bnot security fundamentals\b|"
    r"\bchanging the pace\b|"
    r"\bforensic readiness\b",
    re.I,
)
_LAB_RX = re.compile(
    r"intentionally vulnerable|hands-on lab|\bctf\b|not a real model|rule-based, not",
    re.I,
)
_SECONDARY_TITLE_RX = re.compile(
    r"\bexplained\b|\bguide for\b|\bflaw turns\b|\btop 10 for llm\b",
    re.I,
)
_OWASP_GUIDE_RX = re.compile(r"\bowasp\b", re.I)
_AI_AS_SCANNER_RX = re.compile(
    r"found \d+.{0,80}vulnerabilit.{0,80}(ai agent|using our)|"
    r"(ai agent|using our).{0,80}found \d+.{0,40}vulnerabilit",
    re.I,
)
_CLASSICAL_BUG_RX = re.compile(
    r"\bssrf\b|cross-site scripting|\bxss\b|sql injection|path traversal",
    re.I,
)
_AI_MECHANISM_RX = re.compile(
    r"prompt injection|jailbreak|llm-generated|generated content|"
    r"tool poison|indirect prompt|exfiltrat",
    re.I,
)
_REWRITE_HOSTS = frozenset(
    {
        "cybersecuritynews.com",
        "cybersecuritynews.net",
    }
)
_STORY_ANCHORS = ("divd", "zammad", "echoleak", "carbonato")
_CVE_RX = re.compile(r"cve[-\s]?\d{4}[-\s]?\d+", re.I)


def _host(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def editorial_reject_reason(
    title: str,
    summary: str = "",
    *,
    source_name: str = "",
    source_id: str = "",
    url: str = "",
) -> str | None:
    """None — оставить. Иначе короткая причина отказа."""
    title = title or ""
    summary = summary or ""
    text = f"{title}\n{summary}"
    blob = f"{source_name} {source_id} {url}".lower()

    if _OPINION_RX.search(title):
        return "opinion_or_webinar"
    if _LAB_RX.search(text):
        return "training_lab"
    if _SECONDARY_TITLE_RX.search(title):
        return "secondary_writeup"
    if _OWASP_GUIDE_RX.search(title) and "owasp" not in blob:
        return "owasp_secondary"
    if _AI_AS_SCANNER_RX.search(title) and re.search(
        r"android|chrome|linux|windows|ios", title, re.I
    ):
        return "ai_used_as_scanner"
    if _CVE_RX.search(text) and _CLASSICAL_BUG_RX.search(text) and not _AI_MECHANISM_RX.search(text):
        return "classical_cve"
    if _host(url) in _REWRITE_HOSTS and not re.search(
        r"breach|botnet|attacked|incident", text, re.I
    ):
        return "rewrite_host"
    letters = re.sub(r"\s+", " ", summary).strip()
    if len(letters) < 40 and re.fullmatch(
        r"(prompt injection|jailbreak)( in the wild)?\.?",
        title.strip(),
        flags=re.I,
    ):
        return "title_only"
    return None


def story_key(title: str, summary: str = "") -> str | None:
    """Ключ одной истории: CVE или якорь инцидента. Пусто — не схлопывать."""
    text = f"{title or ''} {summary or ''}"
    cves = sorted({re.sub(r"[-\s]", "", m.lower()) for m in _CVE_RX.findall(text)})
    if cves:
        return "cve:" + "+".join(cves)
    low = text.lower()
    for anchor in _STORY_ANCHORS:
        if anchor in low:
            return "story:" + anchor
    return None
