"""Автотеги: новые тренды из корпуса, которых ещё нет в фиксированной таксономии."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import httpx

from ..analytics.constants import SIGNAL_WINDOW_DAYS
from ..config import DATA_DIR
from ..db import utcnow
from .taxonomy import TAXONOMY

log = logging.getLogger("trendwatcher.emerging")

EMERGING_PATH = DATA_DIR / "archive" / "emerging_tags.json"
MAX_TAGS = 12
MIN_RECENT = 3
MAX_PRIOR = 1

_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:[-'][a-z0-9]+)?", re.I)
_STOP = frozenset(
    """
    a an the and or of to for in on with from by as at into over after before
    new using based paper study towards toward via how why what this that its
    their our your they them we you it is are was were be been being not no
    more most than then also into over under first second results show shows
    toward towards across within without into onto from into
    large language model models llm ai gen generative intelligence system
    systems data training open source company companies research
    can cannot can't could should would will shall may might must
    do does did doing have has had having
    when while if but yet so nor vs versus per
    these those which who whom whose here there where
    such both each every other another
    """.split()
)
# Служебные глаголы: «agents can…» — не тема, а синтаксис заголовка.
_AUX = frozenset(
    """
    can cannot can't could should would will shall may might must
    do does did have has had
    """.split()
)
_LIGHT_TAIL = frozenset(
    """
    support supports supporting enable enables enabling
    help helps helping become becomes becoming
    allow allows allowing use uses used
    make makes made prove proves proved
    need needs needed show shows showing
    """.split()
)
_GENERIC_CONTENT = frozenset(
    "agent agents llm llms model models ai system systems data paper study research".split()
)
_JUNK_SLUG_RX = re.compile(
    r"(^|_)(can|cannot|cant|could|should|would|will|shall|may|might|must)(_|$)"
)
_SEED_EXACT = frozenset({"a2a", "mcp", "rag", "rce", "ssrf"})
_SEED_PREFIX = (
    "agent", "protocol", "memory", "sandbox", "jailbreak", "inject", "poison",
    "swarm", "harness", "skill", "permission", "browser", "credential", "delegat",
    "autonom", "replicat", "orchestr", "plugin", "contain", "guardrail",
    "multimodal", "exfiltrat", "hijack", "tool", "identity", "eval",
    "redteam", "supply", "chain", "prompt", "context",
)

_TAX_RX = {
    tag: [re.compile(p, re.I) for p in pats]
    for tag, pats in TAXONOMY.items()
}

_cache: list[dict] | None = None
_overlay_rx: list[tuple[str, list[re.Pattern[str]]]] | None = None

LLM_PROMPT = """You name emerging AI-security trends from candidate phrases.

Return JSON: {"tags":[{"tag":"snake_case","keep":true,"category":"security"|"ai_tech","patterns":["regex"],"label":"short name"}]}

Rules:
- keep only phrases that are a NEW attack surface / protocol / agent capability, not a product or benchmark
- tag: lowercase snake_case, ascii, max 40 chars
- patterns: 1-3 regexes matching the phrase in titles (case-insensitive)
- drop duplicates of known topics: prompt injection, jailbreak, MCP security, RAG, generic agentic
- precision over recall; at most 8 tags
"""


def emerging_path(path: Path | None = None) -> Path:
    return path or EMERGING_PATH


def clear_emerging_cache() -> None:
    global _cache, _overlay_rx
    _cache = None
    _overlay_rx = None


def load_emerging_tags(path: Path | None = None) -> list[dict]:
    global _cache
    if path is None and _cache is not None:
        return _cache
    p = emerging_path(path)
    if not p.is_file():
        items: list[dict] = []
    else:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            items = list(raw.get("tags") or [])
        except (OSError, json.JSONDecodeError):
            items = []
    items = [t for t in items if not _is_junk_tag(t)]
    if path is None:
        _cache = items
    return items


def emerging_tag_ids(path: Path | None = None) -> frozenset[str]:
    return frozenset(str(t.get("tag") or "") for t in load_emerging_tags(path) if t.get("tag"))


def save_emerging_tags(items: list[dict], path: Path | None = None) -> Path:
    p = emerging_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    items = [t for t in items if not _is_junk_tag(t)][:MAX_TAGS]
    payload = {
        "generated_at": utcnow().isoformat(),
        "tags": items,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if path is None:
        clear_emerging_cache()
        _cache_set(items)
    return p


def _cache_set(items: list[dict]) -> None:
    global _cache
    _cache = items


def overlay_matchers(path: Path | None = None) -> list[tuple[str, list[re.Pattern[str]]]]:
    global _overlay_rx
    if path is None and _overlay_rx is not None:
        return _overlay_rx
    out: list[tuple[str, list[re.Pattern[str]]]] = []
    for item in load_emerging_tags(path):
        tag = str(item.get("tag") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", tag):
            continue
        compiled: list[re.Pattern[str]] = []
        for pat in item.get("patterns") or []:
            try:
                compiled.append(re.compile(str(pat), re.I))
            except re.error:
                continue
        if compiled:
            out.append((tag, compiled))
    if path is None:
        _overlay_rx = out
    return out


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN.finditer(text or "")]


def _interesting(tokens: list[str]) -> bool:
    for t in tokens:
        core = t.replace("-", "")
        if core in _SEED_EXACT or t in _SEED_EXACT:
            return True
        if any(core.startswith(s) or t.startswith(s) for s in _SEED_PREFIX):
            return True
    return False


def _covered_by_taxonomy(phrase: str) -> bool:
    return any(rx.search(phrase) for rxs in _TAX_RX.values() for rx in rxs)


def _slug(tokens: list[str]) -> str:
    raw = "_".join(t.replace("-", "_") for t in tokens)
    slug = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "", raw)).strip("_")
    return slug[:48]


def _ngrams(tokens: list[str], n: int) -> list[list[str]]:
    return [tokens[i : i + n] for i in range(len(tokens) - n + 1)]


def _is_junk_gram(gram: list[str]) -> bool:
    """Отсекает обрезки вроде 'agents can' / 'agents can support'."""
    if not gram or gram[0] in _STOP or gram[-1] in _STOP:
        return True
    if any(t in _AUX for t in gram):
        return True
    if gram[-1] in _LIGHT_TAIL:
        return True
    if _JUNK_SLUG_RX.search(_slug(gram)):
        return True
    content = [t for t in gram if t not in _STOP]
    if len(content) < 2 or not _interesting(content):
        return True
    if all(t in _GENERIC_CONTENT for t in content):
        return True
    return False


def _is_junk_tag(item: dict) -> bool:
    tag = str(item.get("tag") or "")
    if not tag or _JUNK_SLUG_RX.search(tag):
        return True
    label = str(item.get("label") or tag.replace("_", " "))
    return _is_junk_gram(_tokens(label))


def _phrase_candidates(title: str) -> list[list[str]]:
    toks = [t for t in _tokens(title) if len(t) > 1]
    out: list[list[str]] = []
    for n in (2, 3, 4):
        for gram in _ngrams(toks, n):
            if _is_junk_gram(gram):
                continue
            phrase = " ".join(gram)
            if _covered_by_taxonomy(phrase):
                continue
            if _slug(gram) in TAXONOMY:
                continue
            out.append(gram)
    return out


def _pattern_from_tokens(tokens: list[str]) -> str:
    parts = [re.escape(t) for t in tokens]
    return r"\b" + r"[- ]+".join(parts) + r"\b"


def _count_phrases(
    docs: Iterable[Any],
    *,
    now: datetime,
) -> dict[str, dict]:
    recent_from = now - timedelta(days=SIGNAL_WINDOW_DAYS)
    prior_from = now - timedelta(days=SIGNAL_WINDOW_DAYS * 2)
    buckets: dict[str, dict] = {}
    for doc in docs:
        title = getattr(doc, "title", None) or (doc.get("title") if isinstance(doc, dict) else "")
        published = getattr(doc, "published_at", None)
        if isinstance(doc, dict):
            published = doc.get("published_at")
        if isinstance(published, str):
            try:
                published = datetime.fromisoformat(published.replace("Z", ""))
            except ValueError:
                continue
        if published is None:
            continue
        if published >= recent_from:
            window = "recent"
        elif published >= prior_from:
            window = "prior"
        else:
            continue
        for gram in _phrase_candidates(title):
            slug = _slug(gram)
            if not slug or slug in TAXONOMY:
                continue
            rec = buckets.setdefault(
                slug,
                {
                    "tag": slug,
                    "label": " ".join(gram),
                    "tokens": gram,
                    "recent": 0,
                    "prior": 0,
                    "examples": [],
                    "patterns": [_pattern_from_tokens(gram)],
                    "category": "security",
                    "source": "heuristic",
                },
            )
            rec[window] += 1
            if window == "recent" and title and title not in rec["examples"] and len(rec["examples"]) < 3:
                rec["examples"].append(title[:160])
    return buckets


def _heuristic_pick(buckets: dict[str, dict]) -> list[dict]:
    scored = []
    for rec in buckets.values():
        recent, prior = rec["recent"], rec["prior"]
        if recent < MIN_RECENT:
            continue
        if prior > MAX_PRIOR and recent < prior * 3:
            continue
        novelty = recent / (prior + 1)
        scored.append((novelty, recent, rec))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]["tag"]))
    picked = []
    seen_labels: set[str] = set()
    for _, _, rec in scored:
        key = rec["label"]
        if any(key in s or s in key for s in seen_labels):
            continue
        seen_labels.add(key)
        picked.append(
            {
                "tag": rec["tag"],
                "label": rec["label"],
                "patterns": rec["patterns"],
                "category": rec["category"],
                "recent": rec["recent"],
                "prior": rec["prior"],
                "examples": rec["examples"],
                "source": "heuristic",
            }
        )
        if len(picked) >= MAX_TAGS:
            break
    return picked


def _llm_refine(candidates: list[dict], api_key: str) -> list[dict] | None:
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": LLM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    [{"tag": c["tag"], "label": c["label"], "examples": c["examples"]} for c in candidates[:15]],
                    ensure_ascii=False,
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        log.warning("emerging LLM refine failed: %s", exc)
        return None
    by_old = {c["tag"]: c for c in candidates}
    out: list[dict] = []
    for item in data.get("tags") or []:
        if not item.get("keep", True):
            continue
        tag = str(item.get("tag") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,47}", tag) or tag in TAXONOMY:
            continue
        if _JUNK_SLUG_RX.search(tag):
            continue
        patterns = [str(p) for p in (item.get("patterns") or []) if p]
        base = by_old.get(tag) or next((c for c in candidates if c["label"] in tag.replace("_", " ")), None)
        merged = {
            "tag": tag,
            "label": str(item.get("label") or (base or {}).get("label") or tag),
            "patterns": patterns or (base or {}).get("patterns") or [rf"\b{re.escape(tag.replace('_', ' '))}\b"],
            "category": "ai_tech" if item.get("category") == "ai_tech" else "security",
            "recent": (base or {}).get("recent", 0),
            "prior": (base or {}).get("prior", 0),
            "examples": (base or {}).get("examples", []),
            "source": "hybrid",
        }
        # Validate patterns compile.
        ok = []
        for pat in merged["patterns"]:
            try:
                re.compile(pat, re.I)
                ok.append(pat)
            except re.error:
                continue
        if not ok:
            continue
        merged["patterns"] = ok
        out.append(merged)
        if len(out) >= MAX_TAGS:
            break
    return out or None


def discover_emerging_tags(
    docs: Iterable[Any],
    *,
    now: datetime | None = None,
    use_llm: bool | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Ищет новые фразы в заголовках за 90д, которых нет в TAXONOMY."""
    buckets = _count_phrases(docs, now=now or utcnow())
    picked = _heuristic_pick(buckets)
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    want = use_llm if use_llm is not None else bool(key)
    if want and key and picked:
        refined = _llm_refine(picked, key)
        if refined:
            return refined
    return picked


def match_emerging_tags(text: str, path: Path | None = None) -> list[str]:
    found: list[str] = []
    for tag, rxs in overlay_matchers(path):
        if any(rx.search(text or "") for rx in rxs):
            found.append(tag)
    return found
