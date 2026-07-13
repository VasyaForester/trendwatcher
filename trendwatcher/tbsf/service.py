"""TBSF-оценка исследований (arXiv) для TrendWatcher."""

from __future__ import annotations

from datetime import date, datetime

from .scorer import DeterministicScorer, PaperInput


def score_research_paper(
    title: str,
    summary: str,
    published_at: datetime | None,
    url: str = "",
) -> dict:
    """Возвращает TBSF score 0–100, emoji 🔴/🟡/⚪ и topic vector."""
    scorer = DeterministicScorer()
    pub = published_at.date() if published_at else None
    paper = PaperInput(
        title=title,
        text=summary,
        url=url,
        published=pub,
        venue_hint="arxiv",
    )
    bd = scorer.evaluate(paper, ref_date=date.today())
    total = bd.total
    return {
        "tbsf_score": total,
        "tbsf_level": scorer.rating_emoji(total),
        "tbsf_vector": bd.topic_vector,
    }
