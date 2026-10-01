"""Rule-based topic + concreteness gate.

Отсекает разговоры об AI security без наблюдаемого изменения.
Не заменяет relevance-v2: только запрещает попадание в корпус и ленту.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import load_filtering


# Конкретная тема AI security / security-relevant change, не «AI» само по себе.
_TOPIC_RX = re.compile(
    r"prompt injection|indirect prompt|jailbreak|system prompt|data injection|"
    r"tool poison|goal hijack|agent hijack|memory poison|rag poison|"
    r"model extraction|model inversion|model theft|supply[- ]chain|"
    r"malicious (model|checkpoint|skill|tool)|unsafe serialization|"
    r"\bmcp\b|model context protocol|agent skill|sandbox escape|containment|"
    r"data exfiltration|credential exfiltration|guardrail bypass|"
    r"membership inference|training data extraction|adversarial (attack|example)|"
    r"data poisoning|model backdoor|fine[- ]tun\w+ attack|"
    r"\bdasf\b|owasp|mitre atlas|\batlas\b|ai rmf|eu ai act|ai act|"
    r"least privilege|tool binding|arbitrary external tools|"
    r"persistent agent memory|spawn(s|ing)? (other )?agents|"
    r"production infrastructure|rewrite (its )?own tools|"
    r"agent-to-agent|delegated credentials|"
    r"cyber (capability|evaluation)|vulnerability discovery",
    re.I,
)

_GENERIC_RX = re.compile(
    r"biggest threat|top\s+\d+|what is ai security|why ai security matters|"
    r"future of (ai |agentic )?security|ways to secure your ai|"
    r"\braised\b.{0,40}(\$|\d+\s*m)|partnered with|"
    r"conference recap|thought leadership|becoming more common|"
    r"becoming popular|transforming enterprise|"
    r"why businesses need|ai is changing cybersecurity|"
    r"the future of agentic",
    re.I,
)

# Наблюдаемое изменение: класс → паттерн. Один класс уже выше порога expert.
_CLASSES: list[tuple[str, re.Pattern[str]]] = [
    (
        "INCIDENT",
        re.compile(
            r"security incident|incident disclosure|real-world incidents?|in the wild|exploited|"
            r"escaped containment|data breach|unauthorized access|"
            r"hacked .{0,40}(during|while|in)",
            re.I,
        ),
    ),
    (
        "VULNERABILITY_RESEARCH",
        re.compile(
            r"\bvulnerabilit|\bcve-\d{4}|affected versions?|sandbox escape|"
            r"\brce\b|privilege escalation|root cause",
            re.I,
        ),
    ),
    (
        "ATTACK_TECHNIQUE",
        re.compile(
            r"(prompt injection|jailbreak|poisoned|poisoning).{0,80}"
            r"(attack|causes?|plants?|demonstrat|exfiltrat|bypass|poc|proof of concept)|"
            r"(demonstrat|poc|proof of concept|exploit).{0,80}"
            r"(prompt injection|jailbreak|exfiltrat|guardrail|mcp|agent)",
            re.I,
        ),
    ),
    (
        "SECURITY_RESEARCH",
        re.compile(
            r"success rate|attack success|\d+\s*%|"
            r"benchmark.{0,40}(vulnerab|security|cyber|cve)|"
            r"(vulnerab|cve).{0,40}benchmark|"
            r"\d+\s*(previously unknown|cves|vulnerabilities)",
            re.I,
        ),
    ),
    (
        "FRAMEWORK_UPDATE",
        re.compile(
            r"(\bdasf\b|owasp|mitre atlas|ai rmf|genai security).{0,80}"
            r"(v?\d|version|adds|added|released|update|control|standard|component)|"
            r"(v?\d|version|released|update|adds|control|standard).{0,60}"
            r"(\bdasf\b|owasp|atlas|ai rmf)|"
            r"least privilege|tool binding|agent control standard",
            re.I,
        ),
    ),
    (
        "REGULATION",
        re.compile(
            r"implementing act|delegated act|enters into force|enforcement action|"
            r"eu ai act.{0,60}(guidan|requirement|obligation|adopt)|"
            r"(guidan|requirement|adopt).{0,40}eu ai act",
            re.I,
        ),
    ),
    (
        "SECURITY_CAPABILITY_BREAKTHROUGH",
        re.compile(
            r"autonomous(ly)?.{0,40}(vulnerabilit|exploit|discover)|"
            r"(vulnerabilit|cve).{0,40}(discover|found).{0,30}(model|agent)|"
            r"arbitrary external tools|persistent agent memory|"
            r"spawn(s|ing)? (other )?agents|production infrastructure|"
            r"rewrite (its )?own tools|agent-to-agent|"
            r"delegated credentials|model context protocol",
            re.I,
        ),
    ),
]

# Название конкретной техники само по себе — изменение, если это не обзор.
_DIRECT_TECHNIQUE_RX = re.compile(
    r"prompt injection|indirect prompt|jailbreak|data injection|memory poison|tool poison|"
    r"rag poison|sandbox escape|containment escape|model extraction|"
    r"membership inference",
    re.I,
)

_EVIDENCE_RX = re.compile(
    r"\bpoc\b|proof of concept|reproduct|exploit|affected version|\d+\s*%|\bv\d",
    re.I,
)

_PRIMARY_ORIGINS = re.compile(
    r"openai|anthropic|hugging\s?face|nist|owasp|deepmind|microsoft|meta",
    re.I,
)


@dataclass(frozen=True)
class Materiality:
    topic_relevance: float
    concreteness: float
    classes: tuple[str, ...]
    accept: bool
    reason: str


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def topic_relevance(text: str, *, source_name: str = "", source_id: str = "") -> float:
    if _TOPIC_RX.search(text or ""):
        return 0.86
    origin = f"{source_name} {source_id}"
    if _PRIMARY_ORIGINS.search(origin) and re.search(
        r"incident|vulnerabilit|security|containment|advisory|control", text or "", re.I
    ):
        return 0.78
    if re.search(r"\bai\b|llm|agent", text or "", re.I) and re.search(
        r"security|threat|vulnerabilit", text or "", re.I
    ):
        return 0.48
    return 0.15


def concreteness(text: str) -> tuple[float, tuple[str, ...]]:
    names = [name for name, rx in _CLASSES if rx.search(text or "")]
    if (
        "ATTACK_TECHNIQUE" not in names
        and _DIRECT_TECHNIQUE_RX.search(text or "")
        and not _GENERIC_RX.search(text or "")
    ):
        names.append("ATTACK_TECHNIQUE")
    found = tuple(names)
    if not found:
        if _GENERIC_RX.search(text or ""):
            return 0.08, found
        return 0.2, found
    score = 0.60 + 0.12 * (len(found) - 1)
    if _EVIDENCE_RX.search(text or ""):
        score += 0.10
    if _GENERIC_RX.search(text or "") and len(found) == 1 and "FRAMEWORK_UPDATE" not in found:
        # Риторика («biggest threat») не должна проходить на одном слабом совпадении.
        if found == ("ATTACK_TECHNIQUE",) or found == ("SECURITY_RESEARCH",):
            pass
        else:
            score -= 0.35
    return _clip(score), found


def min_concreteness(role: str, filtering: dict | None = None) -> float:
    cfg = filtering if filtering is not None else load_filtering()
    if role == "discovery":
        return float(cfg["discovery_min_concreteness"])
    if role == "primary":
        return float(cfg["primary_min_concreteness"])
    return float(cfg["min_concreteness"])


def assess(
    text: str,
    *,
    role: str = "expert",
    source_name: str = "",
    source_id: str = "",
    filtering: dict | None = None,
) -> Materiality:
    cfg = filtering if filtering is not None else load_filtering()
    topic = topic_relevance(text, source_name=source_name, source_id=source_id)
    score, classes = concreteness(text)
    if classes and re.search(r"agent|llm|\bmcp\b|model|owasp|\bdasf\b|ai act", text or "", re.I):
        topic = max(topic, 0.82)
    topic_min = float(cfg["min_topic_relevance"])
    conc_min = min_concreteness(role, cfg)
    if topic < topic_min:
        return Materiality(topic, score, classes, False, "topic_relevance below threshold")
    if score < conc_min:
        return Materiality(topic, score, classes, False, "concreteness below threshold")
    label = ",".join(classes) if classes else "concrete"
    return Materiality(topic, score, classes, True, label)


def supported_language(text: str) -> bool:
    """Латиница и кириллица. Иные письменности не берём в корпус."""
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) < 12:
        return True
    ok = sum(
        1
        for c in letters
        if ("a" <= c.lower() <= "z") or ("\u0400" <= c <= "\u04ff")
    )
    return ok / len(letters) >= 0.5


def passes_materiality(
    text: str,
    *,
    role: str = "expert",
    source_name: str = "",
    source_id: str = "",
) -> bool:
    return assess(
        text, role=role, source_name=source_name, source_id=source_id
    ).accept
