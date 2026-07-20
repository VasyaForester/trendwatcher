"""Baseline-обогащение документов: теги таксономии, тип, сущности, severity.

Работает на правилах/regex — быстро, бесплатно, воспроизводимо.
LLM-обогащение подключается позже как второй слой поверх этого.
"""

import re

from .tag_filter import normalize_tags
from .taxonomy import (
    AI_RELEVANCE_PATTERNS,
    BREAKTHROUGH_AI_PATTERNS,
    BREAKTHROUGH_AI_TAGS,
    FEED_AI_ANCHOR_PATTERNS,
    FEED_EVENT_PATTERNS,
    FEED_REJECT_PATTERNS,
    KNOWN_ENTITIES,
    SECURITY_TAGS,
    SEVERITY_PATTERNS,
    TAXONOMY,
)

_TAXONOMY_RX = {tag: [re.compile(p, re.I) for p in pats] for tag, pats in TAXONOMY.items()}
_AI_RX = [re.compile(p, re.I) for p in AI_RELEVANCE_PATTERNS]
_BREAKTHROUGH_RX = [re.compile(p, re.I) for p in BREAKTHROUGH_AI_PATTERNS]
_FEED_EVENT_RX = [re.compile(p, re.I) for p in FEED_EVENT_PATTERNS]
_FEED_REJECT_RX = [re.compile(p, re.I) for p in FEED_REJECT_PATTERNS]
_FEED_AI_RX = [re.compile(p, re.I) for p in FEED_AI_ANCHOR_PATTERNS]
_SEVERITY_RX = [(re.compile(p, re.I), score) for p, score in SEVERITY_PATTERNS.items()]
_CVE_RX = re.compile(r"CVE-\d{4}-\d{3,}", re.I)
_ENTITY_RX = [(e, re.compile(r"\b" + re.escape(e) + r"\b", re.I)) for e in KNOWN_ENTITIES]


def is_ai_related(text: str) -> bool:
    return any(rx.search(text) for rx in _AI_RX)


def is_ai_security_or_breakthrough(text: str, tags: list[str] | None = None) -> bool:
    """Широкий «интересный AI» (ingest legacy). Для ленты используйте is_feed_relevant."""
    tag_set = set(tags) if tags is not None else set(extract_tags(text))
    if tag_set & SECURITY_TAGS:
        return True
    if tag_set & BREAKTHROUGH_AI_TAGS:
        return True
    return any(rx.search(text) for rx in _BREAKTHROUGH_RX)


def is_feed_relevant(
    text: str,
    tags: list[str] | None = None,
    *,
    source_name: str = "",
) -> bool:
    """Лента: только AI-security события/артефакты (по разметке batch1).

    Нужны: AI-якорь + event-сигнал (инцидент/CVE/jailbreak/prompt injection/…).
    Отвергаем: opinion, product launch, scorecard, обзоры «N kinds of».
    """
    if any(rx.search(text) for rx in _FEED_REJECT_RX):
        return False

    tag_set = set(tags) if tags is not None else set(extract_tags(text))
    # Высокосигнальные security-теги (не privacy/governance сами по себе)
    hard_sec = tag_set & {
        "prompt_injection",
        "indirect_prompt_injection",
        "jailbreak",
        "agent_security",
        "mcp_security",
        "data_poisoning",
        "model_supply_chain",
        "malware_abuse",
        "red_teaming",
        "vulnerability_cve",
        "inference_integrity",
        "agent_identity_trust",
        "agent_permissions",
        "agent_swarm_security",
        "agent_memory_security",
        "tool_calling_security",
        "ai_codegen_security",
        "autonomous_cyber_offense",
        "model_context_poisoning",
        "multimodal_injection",
        "rag_security",
        "data_exfiltration",
        "model_theft",
    }

    has_ai = bool(tag_set & (SECURITY_TAGS | BREAKTHROUGH_AI_TAGS)) or any(
        rx.search(text) for rx in _FEED_AI_RX
    )
    if not has_ai and source_name:
        if re.search(
            r"hugging\s?face|openai|anthropic|google|microsoft|nvidia|nist|owasp|cisa",
            source_name,
            re.I,
        ):
            # Vendor/standards blog: AI-контекст из источника, если есть security-event
            has_ai = True
    if not has_ai:
        return False

    has_event = bool(hard_sec) or any(rx.search(text) for rx in _FEED_EVENT_RX)
    if _CVE_RX.search(text):
        has_event = True

    return has_event


def extract_tags(text: str) -> list[str]:
    raw = [tag for tag, rxs in _TAXONOMY_RX.items() if any(rx.search(text) for rx in rxs)]
    return normalize_tags(raw)


def extract_entities(text: str) -> list[str]:
    entities = [e for e, rx in _ENTITY_RX if rx.search(text)]
    entities += sorted({m.upper() for m in _CVE_RX.findall(text)})
    return entities


def severity_score(text: str) -> float:
    return max((score for rx, score in _SEVERITY_RX if rx.search(text)), default=0.0)


def classify_doc_type(text: str, source_type: str) -> str:
    t = text.lower()
    if source_type == "research":
        return "research"
    if source_type == "vulnerability" or _CVE_RX.search(text):
        return "vulnerability"
    if re.search(r"ai act|regulation|executive order|law|legislation|compliance deadline", t):
        return "regulation"
    if source_type == "standards" and re.search(r"framework|guidance|standard|guideline|profile", t):
        return "framework"
    if re.search(r"breach|hacked|compromised|incident|attack (on|against)|leaked", t):
        return "incident"
    if re.search(r"attack.{0,40}(ai|llm|agent|model)|ai agents?.{0,25}attack", t):
        return "incident"
    if re.search(r"releases?|launch(es|ed)?|announc(es|ed)|open[- ]sourc|introduc(es|ed)|new tool", t):
        return "tool_release"
    return "news"


def enrich(title: str, summary: str, source_type: str) -> dict:
    text = f"{title}\n{summary}"
    return {
        "tags": extract_tags(text),
        "entities": extract_entities(text),
        "severity": severity_score(text),
        "doc_type": classify_doc_type(text, source_type),
    }
