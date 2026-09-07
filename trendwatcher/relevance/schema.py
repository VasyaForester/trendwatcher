"""Структурированный результат relevance-v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

CLASSES = ("security", "breakthrough", "noise")
DECISIONS = ("reject", "queue", "feed", "signal")


@dataclass
class Relevance:
    relevance_class: str = "noise"
    decision: str = "reject"
    relevance_score: int = 0
    ai_security: float = 0.0
    breakthrough: float = 0.0
    novelty: float = 0.0
    attack_surface: float = 0.0
    importance: float = 0.0
    evidence: float = 0.0
    reason: str = ""
    attack_surfaces: list[str] = field(default_factory=list)
    path: str = "none"
    source: str = "heuristic"

    def in_feed(self) -> bool:
        return self.decision in ("feed", "signal")

    def to_feed_fields(self) -> dict:
        return {
            "relevance_score": self.relevance_score,
            "relevance_class": self.relevance_class,
            "relevance_reason": self.reason,
            "relevance_decision": self.decision,
            "attack_surfaces": list(self.attack_surfaces),
            "novelty": round(self.novelty, 2),
            "attack_surface_delta": round(self.attack_surface, 2),
        }

    def to_dict(self) -> dict:
        return asdict(self)
