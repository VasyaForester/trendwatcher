"""Тип документа по сути заголовка: что это за материал, а не какие слова встретились.

Инцидент — конкретный случай (кто-то взломан, модель вырвалась, раскрытие срыва).
Не инцидент: подход/инструмент, мнение, предупреждение об угрозе «в целом».
"""

from __future__ import annotations

import re

_CVE_RX = re.compile(r"CVE-\d{4}-\d{3,}", re.I)

# Разбор/инструкция/мнение — даже если в тексте есть incident/attack.
_METHOD_OR_COMMENTARY = re.compile(
    r"^\s*(?:"
    r"how\s+(?!an?\s+.+\bbe(?:came|come)\b)"
    r"|why\s+"
    r"|what\s+"
    r"|when\s+the\s+"
    r"|is\s+"
    r"|are\s+"
    r"|\d+\s+(?:ways?|key\s+takeaways|steps?)\b"
    r")"
    r"|i worked at\b"
    r"|here are the\b"
    r"|we need now\b"
    r"|should(?:'?ve| have) been\b"
    r"|warns? of\b.{0,50}\b(?:threat|risk|attacks?|hackers?)\b"
    r"|threat of\b.{0,40}\b(?:persistent\s+)?(?:ai\s+)?(?:cyber[- ]?)?attacks?\b"
    r"|adds? controls?\b"
    r"|for enhanced\b"
    r"|soc workflows?\b"
    r"|guardrails we need\b"
    r"|lessons for\b"
    r"|what actually works\b"
    r"|how to\b"
    r"|ways? (?:ai|you) can\b"
    r"|incident (?:investigation|analysis|response|management)\b"
    r"|uses? ai to\b"
    r"|talks?\b.{0,20}\b(?:hugging|face|phantom|security)\b"
    r"|risk[- ]first ciso\b"
    r"|takeaways from\b"
    r"|newsletter\b"
    r"|roundup\b"
    r"|in soup again\b"
    r"|how worried should we\b"
    r"|governance problem\b"
    r"|is failing\b"
    r"|dictates security operations\b"
    r"|where ai platforms\b"
    r"|choice is a security decision\b"
    r"|why you need\b"
    r"|kill switch\b"
    r"|pump the brakes on ai\b"
    r"|should apologise\b"
    r"|drive union[- ]resistant\b"
    r"|to the bargaining table\b"
    r"|isn'?t autonomous\b"
    r"|human[- ]amplified\b"
    r"|next big governance\b"
    r"|to accelerate incident\b",
    re.I,
)

# How <событие> стало атакой/взломом — пересказ конкретного случая, не how-to.
_RETOLD_EVENT = re.compile(
    r"how\s+(an?\s+)?.{0,90}\b(became|turned into)\b.{0,50}\b"
    r"(cyberattack|cyber-attack|attack|breach|hack)\b",
    re.I,
)

# Конкретный случай: жертва/раскрытие + свершившееся событие.
_SPECIFIC_EVENT = re.compile(
    r"security incident (?:disclosure|during|at|involving)"
    r"|incident disclosure"
    r"|real[- ]world incidents?"
    r"|escaped? (?:its |the )?(?:testing |eval(?:uation)? )?"
    r"(?:sandbox|containment|environment)"
    r"|(?:hacked|breached|broke into|broke out of) .{0,50}"
    r"(?:hugging\s?face|production|organization|organisations?|company|servers?"
    r"|ministry|gym|startup|computers?)"
    r"|(?:hugging\s?face|anthropic|openai).{0,60}"
    r"(?:breach|hacked|security incident|broke into|escaped)"
    r"|cyberattack on "
    r"|(?:was|were) hit by\b"
    r"|confirms? breach"
    r"|breach affects?"
    r"|hacked hugging face"
    r"|models? hacked\b"
    r"|went rogue during (?:testing|evaluation|security testing)"
    r"|targeted (?:with|by) .{0,40}(?:agent|attack|hades)"
    r"|attack on (?:taiwan|hugging|asian government|thai ministry)"
    r"|autonomous attack on "
    r"|broke into computers?"
    r"|hacked organizations?"
    r"|investigating .{0,40}incidents? in our"
    r"|third[- ]party cyber evaluations involving"
    r"|unsanctioned.? actions"
    r"|resorted to deception in .{0,20}(?:cyber|incidents?)"
    r"|created fake online identities"
    r"|using stolen identities"
    r"|gain [0-9.]+m installs"
    r"|in the wild\b.{0,30}attack"
    r"|now target .{0,40}ransomware"
    r"|weaponizes? .{0,50}to attack"
    r"|agent drives? espionage"
    r"|rogue (?:ai )?(?:agent|model).{0,40}(?:hacked|broke|escaped|attack)"
    r"|ai agent hacks\b"
    r"|gym booking task turns into"
    r"|china[- ]linked hackers? use"
    r"|hacker shows ai capabilities in .{0,20}attack"
    r"|hacker uses .{0,30}to autonomously attack"
    r"|incidents of .{0,40}going rogue"
    r"|taiwan says .{0,80}(?:cyber[- ]?attack|attack)"
    r"|cyberattacks? targeting\b"
    r"|targeted real (?:people|systems)"
    r"|agents ran amok",
    re.I,
)

# Возможная техника / «could let» — не свершившийся инцидент.
_HYPOTHETICAL = re.compile(
    r"\bcould (?:let|allow|enable|be)\b"
    r"|\bvulnerable to\b"
    r"|\bthwarting\b"
    r"|\bnew risk for\b"
    r"|\bexposes? a new risk\b",
    re.I,
)

_LAUNCH = re.compile(
    r"\b(?:launches?|unveils?|introducing|debuts?)\b"
    r"|\b(?:released?|releases)\b.{0,40}\b(?:model|gemini|gpt|chatgpt|claude|tool|framework|agent)\b"
    r"|\bnew (?:tools?|capabilities|guidance)\b.{0,30}\b(?:to secure|ai agents|devsecops)\b",
    re.I,
)

_NOT_A_LAUNCH = re.compile(
    r"\bexploring sale\b"
    r"|\bwarns? of\b"
    r"|\bpreprint\b"
    r"|\bcisa warns\b"
    r"|\bannounced multiple\b"
    r"|\bslow(?:s|ing)? (?:scaling|development|advanced)\b",
    re.I,
)

_REGULATION = re.compile(
    r"\b(?:eu\s+)?ai act\b"
    r"|\bexecutive order\b"
    r"|\blawmakers?\b"
    r"|\blegislat(?:e|ion|ive)\b"
    r"|\bcongress\b"
    r"|\bcompliance deadline\b"
    r"|\bregulat(?:e|es|ing|ion|ions)\b.{0,40}\b(?:ai|models?|industry)\b"
    r"|\b(?:ai|models?).{0,30}\bregulat(?:e|es|ing|ion|ions)\b"
    r"|\billegal content\b"
    r"|\bcourt ban\b"
    r"|\blegally responsible\b",
    re.I,
)


def _title(text: str) -> str:
    return (text or "").split("\n", 1)[0].strip()


def _is_method_or_commentary(title: str) -> bool:
    if _RETOLD_EVENT.search(title):
        return False
    return bool(_METHOD_OR_COMMENTARY.search(title))


def _is_specific_event(title: str) -> bool:
    if _HYPOTHETICAL.search(title) and not _SPECIFIC_EVENT.search(title):
        return False
    return bool(_SPECIFIC_EVENT.search(title) or _RETOLD_EVENT.search(title))


def _is_product_launch(title: str) -> bool:
    if _NOT_A_LAUNCH.search(title):
        return False
    return bool(_LAUNCH.search(title))


def classify_doc_type(text: str, source_type: str) -> str:
    """Определяет жанр материала по источнику и сути заголовка."""
    if source_type == "research":
        return "research"
    if source_type == "vulnerability" or _CVE_RX.search(text or ""):
        return "vulnerability"

    title = _title(text)

    if _is_method_or_commentary(title):
        if _is_product_launch(title):
            return "tool_release"
        return "news"

    if _REGULATION.search(title):
        return "regulation"

    if source_type == "standards" and re.search(
        r"\b(framework|guidance|standard|guideline|profile)\b", title, re.I
    ):
        return "framework"

    if _is_specific_event(title):
        return "incident"

    if _is_product_launch(title):
        return "tool_release"

    return "news"
