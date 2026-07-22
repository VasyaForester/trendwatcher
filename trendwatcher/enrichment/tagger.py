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
    FEED_SOFT_AI_PATTERNS,
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
_FEED_SOFT_AI_RX = [re.compile(p, re.I) for p in FEED_SOFT_AI_PATTERNS]
_SEVERITY_RX = [(re.compile(p, re.I), score) for p, score in SEVERITY_PATTERNS.items()]
_CVE_RX = re.compile(r"CVE-\d{4}-\d{3,}", re.I)
_VULN_TEXT_RX = re.compile(
    r"cve-\d{4}-\d+|vulnerabilit|\brce\b|remote code execution|zero[- ]day|0[- ]day",
    re.I,
)
# Голое «AI» рядом с security-смыслом (не surveillance — он в reject).
_AI_SOFT_SECURITY_RX = re.compile(
    r"(\bai\b.{0,60}(attack|defense|threat|vulnerab|security|breach|hack|exploit|"
    r"inject|jailbreak|malware|red[- ]team|incident|compromis))"
    r"|((attack|defense|threat|vulnerab|security|breach|hack|exploit|"
    r"inject|jailbreak|malware|red[- ]team|incident|compromis).{0,60}\bai\b)",
    re.I,
)
_ENTITY_RX = [(e, re.compile(r"\b" + re.escape(e) + r"\b", re.I)) for e in KNOWN_ENTITIES]

# Теги, которые сами по себе означают AI-security поверхность (не NuGet typosquat).
_AI_NATIVE_TAGS = {
    "prompt_injection",
    "indirect_prompt_injection",
    "jailbreak",
    "agent_security",
    "mcp_security",
    "data_poisoning",
    "red_teaming",
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
    "model_theft",
    "guardrails_defense",
    "model_drift",
}


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
    """Лента: только AI-security события/артефакты.

    Сильный AI-якорь (LLM/агент/платформа) + security-событие — ок.
    Голое «AI» — только вместе с AI-native событием (prompt injection и т.п.),
    не с классическим CVE/malware и не с surveillance/privacy.
    """
    if any(rx.search(text) for rx in _FEED_REJECT_RX):
        return False

    tag_set = set(tags) if tags is not None else set(extract_tags(text))
    ai_native = tag_set & _AI_NATIVE_TAGS

    has_strong_ai = bool(ai_native | (tag_set & BREAKTHROUGH_AI_TAGS)) or any(
        rx.search(text) for rx in _FEED_AI_RX
    )
    if not has_strong_ai and source_name:
        if re.search(r"hugging\s?face|openai|anthropic|nist|owasp", source_name, re.I):
            has_strong_ai = True

    has_soft_ai = any(rx.search(text) for rx in _FEED_SOFT_AI_RX)
    if not has_strong_ai and not has_soft_ai:
        return False

    # Не доверяем тегу vulnerability_cve без CVE/vuln в тексте (ложные теги в БД).
    vuln_in_text = bool(_VULN_TEXT_RX.search(text))
    classic_sec_tags = tag_set & {
        "vulnerability_cve",
        "malware_abuse",
        "model_supply_chain",
        "data_exfiltration",
    }
    if "vulnerability_cve" in classic_sec_tags and not vuln_in_text:
        classic_sec_tags = classic_sec_tags - {"vulnerability_cve"}

    # AI-native события: теги + характерные паттерны (не любой breach/CVE).
    ai_event_hint = re.compile(
        r"prompt injection|jailbreak|ai agent|agentic|mcp\b|model (poison|theft|supply)|"
        r"hugging\s?face|llm|data poisoning|red[- ]team.{0,20}(ai|llm|model)|"
        r"ai (threats?|security|red team)|system prompt",
        re.I,
    )
    has_ai_native_event = (
        bool(ai_native)
        or bool(ai_event_hint.search(text))
        or bool(_AI_SOFT_SECURITY_RX.search(text))
    )

    has_classic_event = bool(classic_sec_tags) or vuln_in_text or any(
        rx.search(text) for rx in _FEED_EVENT_RX
    )
    if _CVE_RX.search(text):
        has_classic_event = True

    if has_strong_ai and (has_ai_native_event or has_classic_event):
        return True
    # Голое «AI»: только AI-native security, не кампусное surveillance и не SharePoint.
    if has_soft_ai and has_ai_native_event:
        return True
    return False


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
