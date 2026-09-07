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
    queries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    filter_ai: bool = False
    top: bool = False
    max_results: int = 200
    days_back: int = 120

    def search_queries(self) -> list[str]:
        """Уникальные поисковые запросы: `query` плюс список `queries`."""
        out: list[str] = []
        for q in [self.query, *self.queries]:
            q = (q or "").strip()
            if q and q not in out:
                out.append(q)
        return out


def load_sources(path: Path = CONFIG_PATH) -> list[SourceConfig]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return [SourceConfig(**item) for item in raw["sources"]]
