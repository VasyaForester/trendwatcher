"""Три исхода до записи в БД: include, review, reject.

Reject не стирает след: ограниченный журнал в data/archive/reject_sample.jsonl.
Review сохраняется в БД, но в публичную ленту попадает только после classify().
"""

from __future__ import annotations

import hashlib
import json

from ..config import DATA_DIR
import re

from ..enrichment.tagger import is_ai_related
from .classifier import _PRODUCT_NOISE, _SURFACE_HINT, is_cheap_reject, is_relevance_candidate
from .materiality import passes_materiality, supported_language

_ATTACKISH_RX = re.compile(
    r"exploit|vulnerabilit|proof of concept|\bpoc\b|exfiltrat|bypass|0-click|zero-day|sandbox escape",
    re.I,
)
_AIISH_RX = re.compile(
    r"\b(ai|llm|gpt|model|agent|mcp|skill|prompt|guardrail|owasp|nist)\b",
    re.I,
)

REJECT_LOG = DATA_DIR / "archive" / "reject_sample.jsonl"
MAX_REJECT_LINES = 400


def triage_document(
    text: str,
    *,
    role: str,
    source_name: str = "",
    source_id: str = "",
    tags: list[str] | None = None,
    filter_ai: bool = True,
) -> tuple[str, str]:
    if not filter_ai:
        return "include", "source_unfiltered"
    if not supported_language(text):
        return "reject", "language"
    if _PRODUCT_NOISE.search(text or "") or (
        is_cheap_reject(text)
        and not is_relevance_candidate(text, tags, source_name=source_name, source_id=source_id)
    ):
        return "reject", "obvious_noise"
    candidate = is_relevance_candidate(
        text, tags, source_name=source_name, source_id=source_id
    )
    material = passes_materiality(
        text, role=role, source_name=source_name, source_id=source_id
    )
    if candidate and material:
        return "include", "confirmed"
    borderline = bool(
        _SURFACE_HINT.search(text or "")
        or (_ATTACKISH_RX.search(text or "") and _AIISH_RX.search(text or ""))
        or (role in {"primary", "expert"} and is_ai_related(text))
    )
    if candidate or borderline:
        return "review", "borderline"
    return "reject", "off_topic"


def log_reject(
    *,
    url: str,
    title: str,
    summary: str,
    source_id: str,
    role: str,
    reason: str,
    published_at: str = "",
) -> None:
    """Первичные источники пишем всегда, общие — стратифицированная выборка."""
    if role != "primary":
        digest = hashlib.sha256((url or title).encode("utf-8")).hexdigest()
        if int(digest[:2], 16) % 5 != 0:
            return
    REJECT_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "url": url,
        "title": (title or "")[:180],
        "snippet": (summary or "")[:240],
        "source_id": source_id,
        "role": role,
        "reason": reason,
        "published_at": published_at,
    }
    lines: list[str] = []
    if REJECT_LOG.is_file():
        lines = REJECT_LOG.read_text(encoding="utf-8").splitlines()
    lines.append(json.dumps(row, ensure_ascii=False))
    REJECT_LOG.write_text("\n".join(lines[-MAX_REJECT_LINES:]) + "\n", encoding="utf-8")
