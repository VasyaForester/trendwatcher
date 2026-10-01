from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"
DATA_DIR = PROJECT_ROOT / "data"


# Общие СМИ и поисковые витрины: только lead, не самостоятельный сильный сигнал.
DISCOVERY_SOURCE_IDS = frozenset(
    {
        "nyt_technology",
        "guardian_technology",
        "bbc_technology",
        "cnn_technology",
        "washingtonpost_technology",
        "cbc_technology",
        "economictimes_tech",
        "wired",
        "theverge",
        "techcrunch",
        "zdnet_ai",
        "techxplore_ai",
        "sciencedaily_ai",
        "mit_news_ai",
        "aibusiness",
        "cio",
        "gnews_ai_security",
        "bing_ai_security",
        "hn_ai_security",
    }
)

_FILTERING_DEFAULTS = {
    "min_topic_relevance": 0.70,
    "min_concreteness": 0.55,
    "discovery_min_concreteness": 0.65,
    "primary_min_concreteness": 0.48,
    "generic_overview_penalty": 0.45,
}


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
    role: str = ""
    username: str | None = None
    parser: str = ""
    topic_profile: list[str] = field(default_factory=list)
    enabled: bool = True

    def resolved_role(self) -> str:
        role = (self.role or "").strip().lower()
        if role in {"primary", "expert", "discovery"}:
            return role
        if self.id in DISCOVERY_SOURCE_IDS or self.type in {"gnews", "bingnews", "hn", "x"}:
            return "discovery"
        if self.top or self.source_type in {"standards", "vulnerability", "research"}:
            return "primary"
        if self.type == "telegram":
            return "expert"
        return "expert"

    def search_queries(self) -> list[str]:
        """Уникальные поисковые запросы: `query` плюс список `queries`."""
        out: list[str] = []
        for q in [self.query, *self.queries]:
            q = (q or "").strip()
            if q and q not in out:
                out.append(q)
        return out


def _load_raw(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw


def load_x_backends(path: Path = CONFIG_PATH) -> dict:
    raw = _load_raw(path).get("x_backends") or {}
    return {
        "nitter": [str(u).rstrip("/") for u in (raw.get("nitter") or []) if str(u).strip()],
        "html": [str(u).rstrip("/") for u in (raw.get("html") or []) if str(u).strip()],
    }


_sources_cache: list[SourceConfig] | None = None
_filtering_cache: dict | None = None


def load_filtering(path: Path = CONFIG_PATH) -> dict:
    global _filtering_cache
    if path == CONFIG_PATH and _filtering_cache is not None:
        return _filtering_cache
    raw = _load_raw(path).get("filtering") or {}
    out = dict(_FILTERING_DEFAULTS)
    for key in _FILTERING_DEFAULTS:
        if key in raw and raw[key] is not None:
            out[key] = float(raw[key])
    if path == CONFIG_PATH:
        _filtering_cache = out
    return out


def role_for_source(source_id: str) -> str:
    if not source_id:
        return "expert"
    for src in load_sources():
        if src.id == source_id:
            return src.resolved_role()
    if source_id in DISCOVERY_SOURCE_IDS:
        return "discovery"
    return "expert"


def load_sources(path: Path = CONFIG_PATH) -> list[SourceConfig]:
    global _sources_cache
    if path == CONFIG_PATH and _sources_cache is not None:
        return _sources_cache
    raw = _load_raw(path)
    known = {f.name for f in fields(SourceConfig)}
    out: list[SourceConfig] = []
    for item in raw.get("sources") or []:
        kwargs = {k: v for k, v in item.items() if k in known}
        out.append(SourceConfig(**kwargs))
    if path == CONFIG_PATH:
        _sources_cache = out
    return out
