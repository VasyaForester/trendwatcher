from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class SourceConfig:
    id: str
    name: str
    type: str
    source_type: str
    trust: float = 0.5
    url: str | None = None
    query: str | None = None
    keywords: list[str] = field(default_factory=list)
    filter_ai: bool = False
    max_results: int = 200
    days_back: int = 120


def load_sources(path: Path = CONFIG_PATH) -> list[SourceConfig]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return [SourceConfig(**item) for item in raw["sources"]]
