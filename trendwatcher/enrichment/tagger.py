"""Baseline-обогащение документов: теги таксономии, тип, сущности, severity.

Работает на правилах/regex — быстро, бесплатно, воспроизводимо.
LLM-обогащение подключается позже как второй слой поверх этого.
"""

import re

from .taxonomy import (
    AI_RELEVANCE_PATTERNS,
    KNOWN_ENTITIES,
    SEVERITY_PATTERNS,
    TAXONOMY,
)

_TAXONOMY_RX = {tag: [re.compile(p, re.I) for p in pats] for tag, pats in TAXONOMY.items()}
_AI_RX = [re.compile(p, re.I) for p in AI_RELEVANCE_PATTERNS]
_SEVERITY_RX = [(re.compile(p, re.I), score) for p, score in SEVERITY_PATTERNS.items()]
_CVE_RX = re.compile(r"CVE-\d{4}-\d{3,}", re.I)
_ENTITY_RX = [(e, re.compile(r"\b" + re.escape(e) + r"\b", re.I)) for e in KNOWN_ENTITIES]


def is_ai_related(text: str) -> bool:
    return any(rx.search(text) for rx in _AI_RX)


def extract_tags(text: str) -> list[str]:
    return [tag for tag, rxs in _TAXONOMY_RX.items() if any(rx.search(text) for rx in rxs)]


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
