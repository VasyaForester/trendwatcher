"""Курируемая лента: research с достаточным TBSF, остальное — по дате."""

from sqlalchemy import select

from ..db import Document
from .thresholds import FEED_MIN


def build_feed(session, limit: int = 400) -> list[dict]:
    """Research: только TBSF ≥ FEED_MIN, внутри блока — по убыванию score.
    Остальные типы — по дате публикации. Итог — смешанная лента с приоритетом сильных статей.
    """
    docs = session.scalars(
        select(Document).order_by(Document.published_at.desc()).limit(2000)
    ).all()

    research = [
        d
        for d in docs
        if d.source_type == "research"
        and d.tbsf_score is not None
        and d.tbsf_score >= FEED_MIN
    ]
    research.sort(
        key=lambda d: (d.tbsf_score or 0, d.published_at),
        reverse=True,
    )

    other = [d for d in docs if d.source_type != "research"]
    research_cap = min(len(research), max(limit // 2, limit - 80))
    other_cap = limit - research_cap

    merged: list[Document] = []
    ri, oi = 0, 0
    # Чередуем: каждые 2 other — 1 research (если есть), чтобы лента не была только arXiv
    while len(merged) < limit and (ri < research_cap or oi < other_cap):
        for _ in range(2):
            if oi < other_cap and len(merged) < limit:
                merged.append(other[oi])
                oi += 1
        if ri < research_cap and len(merged) < limit:
            merged.append(research[ri])
            ri += 1
    while oi < other_cap and len(merged) < limit:
        merged.append(other[oi])
        oi += 1
    while ri < research_cap and len(merged) < limit:
        merged.append(research[ri])
        ri += 1

    return [d.to_dict() for d in merged[:limit]]
