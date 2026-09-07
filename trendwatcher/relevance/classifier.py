"""Relevance-v2: cheap regex → heuristic scores → optional LLM → gates."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from ..enrichment.doc_type import is_top_source
from ..enrichment.tagger import extract_tags, is_ai_related, is_feed_relevant
from ..enrichment.taxonomy import FEED_REJECT_PATTERNS
from .attack_surface import attack_surface_delta
from .corroboration import evidence_score
from .novelty import novelty_score
from .prompts import SYSTEM_PROMPT, user_prompt
from .schema import Relevance
from .scorer import apply_gates

log = logging.getLogger("trendwatcher.relevance")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
LLM_LIMIT_DEFAULT = 40

_REJECT_RX = [re.compile(p, re.I) for p in FEED_REJECT_PATTERNS]

# Дешёвый намёк на новую поверхность (не «ещё одна модель»).
_SURFACE_HINT = re.compile(
    r"model context protocol|\bmcp\b|agent[- ]to[- ]agent|\ba2a\b|"
    r"persistent (agent )?memory|self[- ](replicat|modif|improv)|"
    r"spawn(s|ing)? (other )?agents|arbitrary (external )?tools|"
    r"computer[- ]use|browser agent|shell access|"
    r"delegate.{0,20}agents|rewrite (its )?own (tools|prompt)|"
    r"sandbox escape|containment|production infrastructure|"
    r"zero trust.{0,20}\bai\b|\bai\b.{0,20}zero trust",
    re.I,
)
_AI_SEC_CONSEQUENCE = re.compile(
    r"(\bai\b.{0,50}(secur(?:e|ing|ity)|threat|red[- ]team|zero trust|attack surface))"
    r"|((secur(?:e|ing|ity)|threat|red[- ]team|zero trust).{0,50}\bai\b)",
    re.I,
)
_PRODUCT_NOISE = re.compile(
    r"^introducing (claude|gemini|gpt|llama|sonnet|opus|haiku)\b|"
    r"\b(benchmark|\+\s?\d+%|valuation|per watt|flagship model)\b",
    re.I,
)


def is_cheap_reject(text: str) -> bool:
    return any(rx.search(text or "") for rx in _REJECT_RX)


def is_relevance_candidate(
    text: str,
    tags: list[str] | None = None,
    *,
    source_name: str = "",
    source_id: str = "",
) -> bool:
    """Шире, чем лента: security-событие ИЛИ намёк на новую attack surface."""
    if is_cheap_reject(text):
        return False
    if is_feed_relevant(text, tags, source_name=source_name, source_id=source_id):
        return True
    if not is_ai_related(text):
        return False
    if _PRODUCT_NOISE.search(text or ""):
        return False
    return bool(_SURFACE_HINT.search(text or ""))


def _importance(text: str, attack_surface: float, source_id: str) -> float:
    base = 0.35 + 0.45 * attack_surface
    if is_top_source(source_id):
        base += 0.12
    if re.search(r"\b(protocol|architecture|standard|in the wild)\b", text or "", re.I):
        base += 0.1
    return round(min(1.0, base), 2)


def heuristic_scores(
    text: str,
    *,
    title: str = "",
    tags: list[str] | None = None,
    source_name: str = "",
    source_id: str = "",
    source_type: str = "",
    trust: float = 0.5,
    corpus_titles: list[str] | None = None,
) -> dict[str, Any]:
    tags = tags if tags is not None else extract_tags(text)
    surface, surfaces, surf_reason = attack_surface_delta(text, tags)
    nov = novelty_score(title or text.split("\n", 1)[0], text, corpus_titles=corpus_titles)
    evid = evidence_score(source_id=source_id, source_type=source_type, trust=trust)
    imp = _importance(text, surface, source_id)

    if is_feed_relevant(text, tags, source_name=source_name, source_id=source_id):
        sec = 0.86
        bt = 0.25
        reason = "AI-specific security event or advisory"
        if surf_reason:
            reason = f"AI security event on {surf_reason}"
    elif is_top_source(source_id) and _AI_SEC_CONSEQUENCE.search(text or ""):
        sec = 0.72
        bt = 0.20
        reason = "Primary lab/standards source describes securing AI systems"
        surface = max(surface, 0.65)
    elif _SURFACE_HINT.search(text) and not _PRODUCT_NOISE.search(text):
        sec = 0.15
        # Высокий delta поверхности = структурный сдвиг, не «ещё один агентный фреймворк».
        if surface >= 0.80:
            nov = max(nov, 0.82)
            bt = 0.88
        else:
            bt = 0.88 if nov >= 0.70 and surface >= 0.70 else 0.52
        reason = (
            f"Possible new attack surface ({surf_reason or 'agent/tool capability'})"
        )
    else:
        sec = 0.08
        bt = 0.12
        reason = "Ordinary AI news or incremental capability"
        surface = min(surface, 0.15)

    return {
        "ai_security": sec,
        "breakthrough": bt,
        "novelty": nov,
        "attack_surface": surface,
        "importance": imp,
        "evidence": evid,
        "reason": reason,
        "attack_surfaces": surfaces,
        "tags": tags,
    }


def _clip01(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def call_llm_relevance(
    title: str,
    summary: str,
    *,
    source_name: str = "",
    tags: list[str] | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 25.0,
) -> dict[str, Any] | None:
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        return None
    model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(title, summary, source_name, tags)},
        ],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(OPENAI_URL, headers=headers, json=payload)
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — LLM не должен ронять экспорт
        log.warning("relevance LLM failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    return data


def _needs_llm(scores: dict[str, Any], text: str, result: Relevance) -> bool:
    """Явные инциденты/CVE — без LLM; двусмысленные и breakthrough — с LLM."""
    if result.path == "security" and scores["ai_security"] >= 0.85:
        if re.search(
            r"prompt injection|jailbreak|cve-\d{4}|sandbox escape|containment|"
            r"security incident|in the wild",
            text or "",
            re.I,
        ):
            return False
    if result.decision == "reject" and not _SURFACE_HINT.search(text or ""):
        return False
    return True


def classify(
    title: str,
    summary: str = "",
    *,
    tags: list[str] | None = None,
    source_name: str = "",
    source_id: str = "",
    source_type: str = "",
    trust: float = 0.5,
    corpus_titles: list[str] | None = None,
    use_llm: bool | None = None,
    api_key: str | None = None,
    llm_budget: LlmBudget | None = None,
) -> Relevance:
    text = f"{title}\n{summary}"
    if is_cheap_reject(text) and not is_feed_relevant(
        text, tags, source_name=source_name, source_id=source_id
    ):
        return apply_gates(
            ai_security=0.05,
            breakthrough=0.05,
            novelty=0.1,
            attack_surface=0.05,
            importance=0.1,
            evidence=evidence_score(source_id=source_id, source_type=source_type, trust=trust),
            reason="Rejected by cheap pre-filter (roundup/marketing/non-event)",
            attack_surfaces=[],
            source="heuristic",
        )

    scores = heuristic_scores(
        text,
        title=title,
        tags=tags,
        source_name=source_name,
        source_id=source_id,
        source_type=source_type,
        trust=trust,
        corpus_titles=corpus_titles,
    )
    result = apply_gates(
        ai_security=scores["ai_security"],
        breakthrough=scores["breakthrough"],
        novelty=scores["novelty"],
        attack_surface=scores["attack_surface"],
        importance=scores["importance"],
        evidence=scores["evidence"],
        reason=scores["reason"],
        attack_surfaces=scores["attack_surfaces"],
        source="heuristic",
    )

    want_llm = use_llm
    if want_llm is None:
        want_llm = bool((api_key or os.environ.get("OPENAI_API_KEY", "")).strip())
    if want_llm and _needs_llm(scores, text, result):
        if llm_budget is not None and not llm_budget.allow():
            return result
        llm = call_llm_relevance(
            title,
            summary,
            source_name=source_name,
            tags=scores["tags"],
            api_key=api_key,
        )
        if llm:
            cls = str(llm.get("class") or "").lower()
            sec = _clip01(llm.get("ai_security"), scores["ai_security"])
            bt = _clip01(llm.get("breakthrough"), scores["breakthrough"])
            nov = _clip01(llm.get("novelty"), scores["novelty"])
            surf = _clip01(llm.get("attack_surface"), scores["attack_surface"])
            # Heuristic security event: не даём LLM понизить ниже порога без уверенного noise.
            if result.path == "security" and cls != "noise":
                sec = max(sec, scores["ai_security"])
            if cls == "noise":
                sec = min(sec, 0.4)
                bt = min(bt, 0.55)
            reason = str(llm.get("reason") or scores["reason"])
            result = apply_gates(
                ai_security=sec,
                breakthrough=bt,
                novelty=nov,
                attack_surface=surf,
                importance=scores["importance"],
                evidence=scores["evidence"],
                reason=reason,
                attack_surfaces=scores["attack_surfaces"],
                source="hybrid",
            )
    return result


def classify_document(doc: Any, *, corpus_titles: list[str] | None = None, **kwargs) -> Relevance:
    return classify(
        getattr(doc, "title", "") or "",
        getattr(doc, "summary", "") or "",
        tags=getattr(doc, "tags", None),
        source_name=getattr(doc, "source_name", "") or "",
        source_id=getattr(doc, "source_id", "") or "",
        source_type=getattr(doc, "source_type", "") or "",
        trust=float(getattr(doc, "trust", 0.5) or 0.5),
        corpus_titles=corpus_titles,
        **kwargs,
    )


class LlmBudget:
    """Ограничивает число LLM-вызовов на один прогон экспорта."""

    def __init__(self, limit: int | None = None):
        env = os.environ.get("REL_LLM_LIMIT", "")
        self.limit = limit if limit is not None else int(env or LLM_LIMIT_DEFAULT)
        self.used = 0

    def allow(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True
