from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import PROJECT_ROOT

TBSF_ROOT = PROJECT_ROOT / "config" / "tbsf"


@dataclass(frozen=True)
class RubricConfig:
    raw: dict[str, Any]
    version: str


@dataclass(frozen=True)
class TopicVector:
    id: str
    score: int
    tier: str
    subcategory: str
    keyword_groups: tuple[str, ...]
    keywords: dict[str, tuple[str, ...]]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_rubric(root: Path | None = None) -> RubricConfig:
    root = root or TBSF_ROOT
    raw = load_yaml(root / "rubric.yaml")
    return RubricConfig(raw=raw, version=str(raw.get("version", "0.0.0")))


def load_topic_vectors(root: Path | None = None, active_only: bool = True) -> list[TopicVector]:
    root = root or TBSF_ROOT
    tv_raw = load_yaml(root / "topic_vectors.yaml")
    vectors: list[TopicVector] = []
    for v in tv_raw.get("vectors", []):
        if active_only and v.get("active") is False:
            continue
        kw_file = root / v["keywords_file"]
        kw_data = load_yaml(kw_file)
        groups = kw_data.get("groups", {})
        selected = {g: tuple(groups.get(g, [])) for g in v.get("keyword_groups", [])}
        vectors.append(
            TopicVector(
                id=v["id"],
                score=int(v["score"]),
                tier=v["tier"],
                subcategory=v.get("subcategory", ""),
                keyword_groups=tuple(v.get("keyword_groups", [])),
                keywords=selected,
            )
        )
    return vectors
