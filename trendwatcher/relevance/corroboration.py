"""Вес источника как evidence: новость = lead, лаборатория/стандарт = confirmation."""

from __future__ import annotations

from ..enrichment.doc_type import is_top_source

_PRIMARY = frozenset({"nvd_ai", "arxiv_ai_security", "nist_news", "cisa_advisories"})
_EXPERT = frozenset({"krebsonsecurity", "schneier", "sans_isc"})


def evidence_score(
    *,
    source_id: str = "",
    source_type: str = "",
    trust: float = 0.5,
) -> float:
    if is_top_source(source_id) or source_id in _PRIMARY:
        tier = 1.0
    elif source_id in _EXPERT or source_type in {"standards", "vulnerability", "research"}:
        tier = 0.85
    elif source_type == "vendor":
        tier = 0.75
    elif source_type == "news":
        tier = 0.55
    else:
        tier = 0.5
    return round(min(1.0, 0.55 * tier + 0.45 * max(0.0, min(trust, 1.0))), 2)
