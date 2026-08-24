"""TBSF-оценка исследований (arXiv) для TrendWatcher."""

from __future__ import annotations

import re
from datetime import date, datetime

from .scorer import DeterministicScorer, PaperInput, RepoInfo

_REPO_RX = re.compile(
    r"github\.com/[\w\-]+/[\w\-.]+"
    r"|gitlab\.com/[\w\-]+/[\w\-.]+"
    r"|huggingface\.co/[\w\-]+/[\w\-.]+",
    re.I,
)
_CODE_AVAILABLE_RX = re.compile(
    r"code (is )?(publicly )?available"
    r"|open[- ]source (code|implementation|release)"
    r"|our (code|implementation) (is|will be)"
    r"|artefacts? available"
    r"|artifact available",
    re.I,
)


def _repo_from_text(text: str) -> RepoInfo | None:
    """Эвристика по тексту: репозиторий / «code available» → частичный code-бонус."""
    has_link = bool(_REPO_RX.search(text))
    code_available = bool(_CODE_AVAILABLE_RX.search(text))
    if not has_link and not code_available:
        return None
    low = text.lower()
    license_name = None
    if re.search(r"\bmit license\b|licensed under mit", low):
        license_name = "MIT"
    elif re.search(r"apache[- ]2", low):
        license_name = "Apache-2.0"
    return RepoInfo(
        has_py=True,
        has_readme=has_link,
        has_deps=has_link
        and bool(re.search(r"requirements\.txt|pyproject\.toml|setup\.py|environment\.yml", low)),
        has_launch=has_link
        and bool(re.search(r"dockerfile|docker-compose|\.sh\b|makefile", low)),
        python_stack=bool(re.search(r"\bpython\b|pytorch|tensorflow|jupyter", low)),
        license=license_name,
        reproduction=bool(
            re.search(r"\breproduc|how to run|getting started|to reproduce\b", low)
        ),
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
