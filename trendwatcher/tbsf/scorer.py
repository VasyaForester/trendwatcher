from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config_loader import RubricConfig, TopicVector, load_rubric, load_topic_vectors, load_yaml, TBSF_ROOT

_SPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = (text or "").lower().replace("–", " ").replace("—", " ")
    t = re.sub(r"[-_/]", " ", t)
    return _SPACE_RE.sub(" ", t).strip()


def keyword_hit(text_norm: str, keyword: str) -> bool:
    kw = normalize(keyword)
    if not kw:
        return False
    if len(kw) <= 4 and re.fullmatch(r"[a-z0-9а-я]+", kw):
        return bool(re.search(rf"\b{re.escape(kw)}\b", text_norm))
    return kw in text_norm


def any_keyword_hit(text_norm: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword_hit(text_norm, k) for k in keywords)


@dataclass
class RepoInfo:
    has_py: bool = False
    has_ipynb: bool = False
    has_readme: bool = False
    has_deps: bool = False
    has_launch: bool = False
    python_stack: bool = False
    license: str | None = None
    reproduction: bool = False
    dataset_size: int = 0
    attack_types: int = 0
    broken_links: bool = False
    outdated_dependencies: bool = False
    code_not_runnable: bool = False
    hidden_module: bool = False
    license_missing: bool = False


@dataclass
class ScoreBreakdown:
    topic: int = 0
    freshness: int = 0
    code: int = 0
    dataset: int = 0
    license: int = 0
    author: int = 0
    venue: int = 0
    penalties: int = 0
    topic_vector: str | None = None
    cyber_risk_bonus: bool = False
    offensive_bonus: bool = False

    @property
    def total(self) -> int:
        raw = (
            self.topic
            + self.freshness
            + self.code
            + self.dataset
            + self.license
            + self.author
            + self.venue
            + self.penalties
        )
        return max(0, min(100, raw))


@dataclass
class PaperInput:
    title: str = ""
    text: str = ""
    url: str = ""
    published: str | date | None = None
    authors: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    venue_hint: str = ""
    repo: RepoInfo | None = None
    author_score: int | None = None
    venue_score: int | None = None
    dataset_override: int | None = None
    topic_base_override: int | None = None
    offensive_override: bool | None = None


def _vector_keywords(vector: TopicVector) -> tuple[str, ...]:
    kws: list[str] = []
    for group in vector.keyword_groups:
        kws.extend(vector.keywords.get(group, ()))
    return tuple(kws)


class DeterministicScorer:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.rubric = load_rubric(root)
        self.vectors = load_topic_vectors(root, active_only=True)
        active_ids = {v.id for v in self.vectors}
        self.fallback_vectors = [
            v
            for v in load_topic_vectors(root, active_only=False)
            if v.id not in active_ids
        ]

    def _evidence_blob(self, paper: PaperInput, limit: int = 2000) -> str:
        """Заголовок + аффилиации + начало текста (без related work)."""
        parts = [
            paper.title,
            " ".join(paper.affiliations),
            " ".join(paper.authors),
            (paper.text or "")[:limit],
        ]
        return " ".join(p for p in parts if p)

    def score_topic(
        self,
        text: str,
        offensive: bool | None = None,
        topic_base_override: int | None = None,
    ) -> tuple[int, str | None, bool, bool, bool]:
        text_norm = normalize(text)
        rubric = self.rubric.raw
        defense_kws = tuple(rubric.get("defense_keywords", []))
        cyber_kws = tuple(rubric.get("cyber_risk_keywords", []))

        is_defense = any_keyword_hit(text_norm, defense_kws)
        has_cyber = any_keyword_hit(text_norm, cyber_kws)

        offensive_kw = (
            "attack",
            "attacks",
            "exploit",
            "jailbreak",
            "hijack",
            "hijacking",
            "poisoning",
            "vulnerability",
            "vulnerabilities",
            "harmful",
            "offensive",
            "red team",
            "red teaming",
            "misevolution",
        )
        is_offensive = (
            offensive
            if offensive is not None
            else any_keyword_hit(text_norm, offensive_kw)
        )

        matched: list[TopicVector] = []
        for vector in self.vectors:
            if any_keyword_hit(text_norm, _vector_keywords(vector)):
                matched.append(vector)

        if topic_base_override is not None:
            base = topic_base_override
            vector_id = matched[0].id if matched else "llm_override"
        elif matched:
            # v3.2: ACTUAL-векторы складываются (агенты + промпт/MCP), не XOR.
            base = min(33, sum(v.score for v in matched))
            vector_id = next(
                (v.id for v in matched if v.id == "agent_security"),
                matched[0].id,
            )
        else:
            base = 0
            vector_id = None
            for vector in self.fallback_vectors:
                if any_keyword_hit(text_norm, _vector_keywords(vector)):
                    base = vector.score
                    vector_id = vector.id
                    break

        bonuses = self._load_bonuses()
        cyber_bonus = bonuses["cyber_risk"] if has_cyber else 0
        off_bonus = bonuses["offensive"] if is_offensive else 0
        topic = min(35, base + cyber_bonus + off_bonus)
        purely_defensive = is_defense and not is_offensive and base == 0
        return (
            topic,
            vector_id,
            has_cyber,
            is_offensive,
            purely_defensive,
        )

    def _load_bonuses(self) -> dict[str, int]:
        root = self.root or TBSF_ROOT
        data = load_yaml(root / "topic_vectors.yaml")
        return {
            "cyber_risk": int(data.get("bonuses", {}).get("cyber_risk", 2)),
            "offensive": int(data.get("bonuses", {}).get("offensive", 1)),
        }

    def score_freshness(self, published: str | date | None, ref: date | None = None) -> int:
        if published is None:
            return 0
        if isinstance(published, str):
            for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
                try:
                    published = datetime.strptime(published, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return 0
        ref = ref or date.today()
        days = (ref - published).days
        if days < 0:
            days = 0
        for bucket in self.rubric.raw.get("freshness", {}).get("buckets", []):
            max_days = bucket.get("max_days")
            if max_days is None or days <= max_days:
                return int(bucket.get("score", 0))
        return 0

    def score_code(self, repo: RepoInfo | None) -> int:
        if repo is None:
            return 0
        cfg = self.rubric.raw.get("code", {})
        score = 0
        has_code = repo.has_py or repo.has_ipynb
        if has_code:
            score += int(cfg.get("non_empty_py_ipynb", 6))
        if repo.has_readme:
            score += int(cfg.get("readme", 4))
        if repo.has_deps:
            score += int(cfg.get("dependencies_file", 3))
        if repo.has_launch:
            score += int(cfg.get("launch_script", 3))
        if repo.python_stack:
            score += int(cfg.get("python_stack_bonus", 2))
        return min(int(self.rubric.raw["formula"]["components"]["code"]["max"]), score)

    def _infer_dataset(self, repo: RepoInfo | None, text: str) -> tuple[int, int]:
        size = repo.dataset_size if repo else 0
        attack_types = repo.attack_types if repo else 0
        if size > 0:
            return size, attack_types
        low = (text or "").lower()
        if not re.search(r"\b(dataset|benchmark|corpus)\b", low):
            return 0, 0
        if re.search(r"\b([1-9]\d{3,}|[1-9]\d{0,2},\d{3})\b", text or ""):
            size = 1000
        else:
            size = 500
        if re.search(r"attack|jailbreak|injection|exploit", low):
            attack_types = max(attack_types, 3)
        return size, attack_types

    def score_dataset(self, repo: RepoInfo | None, text: str = "") -> int:
        cfg = self.rubric.raw.get("dataset", {})
        size, attack_types = self._infer_dataset(repo, text)
        if size <= 0:
            return 0
        score = int(cfg.get("present", 2))
        size_cfg = cfg.get("size", {})
        if size >= size_cfg.get("large", {}).get("min", 1000):
            score += int(size_cfg.get("large", {}).get("score", 3))
        elif size >= size_cfg.get("medium", {}).get("min", 500):
            score += int(size_cfg.get("medium", {}).get("score", 2))
        else:
            score += int(size_cfg.get("small", {}).get("score", 1))
        if attack_types >= 3:
            score += int(cfg.get("attack_diversity_bonus", 2))
        return min(int(self.rubric.raw["formula"]["components"]["dataset"]["max"]), score)

    def score_license(self, repo: RepoInfo | None, text: str = "") -> int:
        cfg = self.rubric.raw.get("license", {})
        score = 0
        lic = ((repo.license if repo else None) or "")
        if not lic and re.search(r"\bmit license\b|apache[- ]2(?:\.0)?|apache license", text or "", re.I):
            lic = "MIT"
        lic_n = lic.upper().replace(" ", "")
        if lic_n in ("MIT", "APACHE-2.0", "APACHE2.0", "APACHE2"):
            score += int(cfg.get("mit_apache", 2))
        elif lic_n:
            score += int(cfg.get("other_open", 1))
        reproduction = bool(repo and repo.reproduction)
        if not reproduction and re.search(
            r"\b(reproduc(e|ible|ibility)|to reproduce|reproduction instructions)\b",
            text or "",
            re.I,
        ):
            reproduction = True
        if reproduction:
            score += int(cfg.get("reproduction_instructions", 2))
        if score == 0:
            return 0
        return min(int(self.rubric.raw["formula"]["components"]["license"]["max"]), score)

    def score_penalties(
        self, repo: RepoInfo | None, purely_defensive: bool = False
    ) -> int:
        cfg = self.rubric.raw.get("penalties", {})
        total = 0
        if purely_defensive:
            total += int(cfg.get("purely_defensive", 0))
        if repo is None:
            max_pen = int(self.rubric.raw.get("formula", {}).get("penalties", {}).get("max", 10))
            return -min(max_pen, total) if total else 0
        if repo.broken_links:
            total += int(cfg.get("broken_links", 2))
        if repo.outdated_dependencies:
            total += int(cfg.get("outdated_dependencies", 2))
        # Штраф за лицензию — только если репозиторий реально проверен.
        if getattr(repo, "license_missing", False):
            total += int(cfg.get("no_license", 3))
        if repo.code_not_runnable:
            total += int(cfg.get("code_not_runnable", 3))
        if repo.hidden_module:
            total += int(cfg.get("hidden_module", 2))
        max_pen = int(self.rubric.raw.get("formula", {}).get("penalties", {}).get("max", 10))
        return -min(max_pen, total) if total else 0

    def score_author_heuristic(self, paper: PaperInput) -> int:
        if paper.author_score is not None:
            return paper.author_score
        rubric = self.rubric.raw.get("author", {})
        top = [i.lower() for i in self.rubric.raw.get("top_institutions", [])]
        blob = normalize(self._evidence_blob(paper))
        hint = normalize(paper.venue_hint)
        for inst in top:
            if inst.lower() in blob:
                if "arxiv" in hint or not hint or hint == "unknown":
                    return int(rubric.get("top_on_arxiv", rubric.get("world_leader", 12)))
                return int(rubric.get("top_institution", 10))
        if re.search(r"\buniversity\b|\binstitute of technology\b|\bdepartment of\b", blob):
            return int(rubric.get("average", 5))
        # arXiv preprint — верифицируемая публикация, не «неизвестный блог».
        if "arxiv" in hint or paper.authors:
            return int(rubric.get("average", 5))
        return int(rubric.get("unverifiable", 0))

    def score_venue_heuristic(self, paper: PaperInput) -> int:
        if paper.venue_score is not None:
            return paper.venue_score
        rubric = self.rubric.raw.get("venue", {})
        hint = normalize(paper.venue_hint)
        head = normalize(self._evidence_blob(paper, limit=800))
        vendor_affil = (
            r"\b(openai|anthropic|google deepmind|deepmind|microsoft research|meta ai)\b"
            r".{0,50}(university|research|lab|institute|inc)"
        )
        if re.search(vendor_affil, head) or re.search(
            r"(researchers? (at|from)|affiliated with).{0,40}"
            r"\b(openai|anthropic|deepmind|microsoft research)\b",
            head,
        ):
            return int(rubric.get("top_vendor", 8))
        conferences = (
            "neurips",
            "iclr",
            "icml",
            "acl",
            "emnlp",
            "ndss",
            "usenix",
            "acm ccs",
            "ieee s&p",
            "oakland",
        )
        blob = normalize(self._evidence_blob(paper) + " " + hint)
        if any(c in blob for c in conferences):
            return int(rubric.get("reputable", 6))
        if "arxiv" in hint and ("journal" in hint or "conference" in hint):
            return int(rubric.get("arxiv_and_journal", 4))
        if "arxiv" in hint or not hint:
            return int(rubric.get("arxiv_only", 2))
        if hint:
            return int(rubric.get("reputable", 6))
        return int(rubric.get("unknown", 0))

    def evaluate(self, paper: PaperInput, ref_date: date | None = None) -> ScoreBreakdown:
        full_text = f"{paper.title}\n{paper.text}"
        topic, vector_id, cyber, offensive, purely_defensive = self.score_topic(
            full_text,
            offensive=paper.offensive_override,
            topic_base_override=paper.topic_base_override,
        )
        bd = ScoreBreakdown(
            topic=topic,
            freshness=self.score_freshness(paper.published, ref_date),
            code=self.score_code(paper.repo),
            dataset=(
                paper.dataset_override
                if paper.dataset_override is not None
                else self.score_dataset(paper.repo, full_text)
            ),
            license=self.score_license(paper.repo, full_text),
            author=self.score_author_heuristic(paper),
            venue=self.score_venue_heuristic(paper),
            penalties=self.score_penalties(paper.repo, purely_defensive=purely_defensive),
            topic_vector=vector_id,
            cyber_risk_bonus=cyber,
            offensive_bonus=offensive,
        )
        return bd

    def rating_emoji(self, total: int) -> str:
        th = self.rubric.raw.get("thresholds", {})
        if total >= int(th.get("priority", 75)):
            return "🔴"
        if total >= int(th.get("reserve_min", 50)):
            return "🟡"
        return "⚪"

    def format_date(self, published: str | date | None) -> str:
        if published is None:
            return ""
        if isinstance(published, date):
            return published.strftime("%d.%m.%Y")
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(published, fmt).strftime("%d.%m.%Y")
            except ValueError:
                continue
        return str(published)
