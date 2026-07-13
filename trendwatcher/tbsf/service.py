"""TBSF-оценка исследований (arXiv) для TrendWatcher."""

from __future__ import annotations

import re
from datetime import date, datetime

from .scorer import DeterministicScorer, PaperInput, RepoInfo

_GITHUB_RX = re.compile(r"github\.com/[\w\-]+/[\w\-.]+", re.I)


def _repo_from_text(text: str) -> RepoInfo | None:
    """Эвристика по abstract: ссылка на GitHub → частичный code/dataset бонус TBSF."""
    if not _GITHUB_RX.search(text):
        return None
    low = text.lower()
    return RepoInfo(
        has_py=True,
        has_readme=True,
        has_deps=bool(re.search(r"requirements\.txt|pyproject\.toml|setup\.py|environment\.yml", low)),
        has_launch=bool(re.search(r"dockerfile|docker-compose|\.sh\b|makefile", low)),
        python_stack=bool(re.search(r"\bpython\b|pytorch|tensorflow|jupyter", low)),
        reproduction=bool(re.search(r"reproduc|benchmark|how to run|getting started", low)),
        dataset_size=500 if re.search(r"dataset|benchmark|corpus", low) else 0,
        attack_types=3 if re.search(r"attack|jailbreak|injection|exploit", low) else 0,
    )


def score_research_paper(
    title: str,
    summary: str,
    published_at: datetime | None,
    url: str = "",
) -> dict:
    """Возвращает TBSF score 0–100, emoji 🔴/🟡/⚪ и topic vector."""
    scorer = DeterministicScorer()
    pub = published_at.date() if published_at else None
    full_text = f"{title}\n{summary}"
    paper = PaperInput(
        title=title,
        text=summary,
        url=url,
        published=pub,
        venue_hint="arxiv",
        repo=_repo_from_text(full_text),
    )
    bd = scorer.evaluate(paper, ref_date=date.today())
    total = bd.total
    return {
        "tbsf_score": total,
        "tbsf_level": scorer.rating_emoji(total),
        "tbsf_vector": bd.topic_vector,
    }
