"""Дешёвая новизна без эмбеддингов: повтор сюжета vs корпус заголовков."""

from __future__ import annotations

import re

from ..ingestion.dedup import title_fingerprint, titles_near_duplicate

_INCREMENTAL = re.compile(
    r"\b(another|yet another|expanding|improved?|improving|better coding|"
    r"benchmark|leaderboard|\+\s?\d+%|percent (better|higher)|"
    r"flagship model|new (llm|model|image model)|agentic framework|"
    r"managed agents)\b",
    re.I,
)
_STRUCTURAL = re.compile(
    r"\b(protocol|architecture|standard|self[- ]replicat|agent[- ]to[- ]agent|"
    r"model context protocol|persistent memory|arbitrary tools?)\b",
    re.I,
)

_STOP = frozenset("the a an and or of to for in on with from new ai llm agent agents".split())


def _tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (title or "").lower()) if t not in _STOP}


def novelty_score(
    title: str,
    text: str = "",
    *,
    corpus_titles: list[str] | None = None,
) -> float:
    """1.0 = первый сюжет в корпусе; 0.0 = десятая перепечатка той же концепции."""
    blob = f"{title}\n{text}"
    if _INCREMENTAL.search(blob) and not _STRUCTURAL.search(blob):
        base = 0.18
    elif _STRUCTURAL.search(blob):
        base = 0.86
    else:
        base = 0.55

    titles = [t for t in (corpus_titles or []) if t and t != title]
    if not titles:
        return round(base, 2)

    fp = title_fingerprint(title)
    near = sum(1 for prev in titles if titles_near_duplicate(title, prev))
    if near:
        return round(max(0.05, base - 0.35 - 0.1 * min(near, 3)), 2)

    tok = _tokens(title)
    if not tok:
        return round(base, 2)
    overlaps = []
    for prev in titles[:400]:
        pt = _tokens(prev)
        if not pt:
            continue
        overlaps.append(len(tok & pt) / len(tok | pt))
    if not overlaps:
        return round(base, 2)
    max_sim = max(overlaps)
    # Похожие заголовки в корпусе снижают novelty.
    adjusted = base * (1.0 - 0.75 * max_sim)
    if fp:
        pass
    return round(max(0.05, min(0.98, adjusted)), 2)
