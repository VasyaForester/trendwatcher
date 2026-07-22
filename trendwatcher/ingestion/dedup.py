"""Нормализация URL и отпечаток заголовка для дедупликации."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source",
}
_PUNCT_RX = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RX = re.compile(r"\s+")
_CVE_RX = re.compile(r"cve[-\s]?\d{4}[-\s]?\d+", re.I)

# Стоп-слова и канцелярит заголовков новостей.
_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "by", "at",
    "with", "from", "as", "its", "it", "is", "are", "was", "were", "be", "been",
    "says", "say", "said", "after", "over", "into", "about", "than", "then",
    "this", "that", "these", "those", "new", "how", "why", "what", "when",
    "while", "during", "under", "amid", "via", "per", "vs", "just", "more",
    "most", "also", "still", "already", "could", "would", "may", "might",
    "can", "will", "has", "have", "had", "their", "our", "your", "his", "her",
}

# Однотокенные «якоря» организаций (после нормализации фраз).
_ORG_TOKENS = {
    "openai", "huggingface", "anthropic", "microsoft", "google", "nvidia",
    "servicenow", "databricks", "amazon", "aws", "meta", "apple", "ibm",
    "oracle", "salesforce", "github", "gitlab", "deepmind", "xai", "mistral",
    "cohere", "perplexity", "cursor", "langchain",
}

# Классы security-событий: достаточно совпадения класса, не точной формы слова.
_EVENT_RX = [
    re.compile(p, re.I)
    for p in (
        r"breach", r"hack(?:ed|ing)?", r"compromis", r"intrusion",
        r"jailbreak", r"prompt\s*injection", r"exploit", r"rce",
        r"zero[\s-]?day", r"leak(?:ed|ing)?", r"rogue", r"escap",
        r"containment", r"backdoor", r"malware", r"ransomware",
        r"stolen", r"exfiltrat",
    )
]

_PHRASE_MAP = (
    ("hugging face", "huggingface"),
    ("open ai", "openai"),
    ("git hub", "github"),
    ("zero day", "zeroday"),
    ("machine keys", "machinekeys"),
)


def normalize_url(url: str) -> str:
    """Канонический URL: без фрагмента, tracking-параметров, лишнего слэша."""
    if not url:
        return ""
    raw = url.strip()
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or ""
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def title_fingerprint(title: str) -> str:
    """Грубый ключ заголовка для ловли перепечаток одной новости."""
    t = (title or "").lower().replace("ё", "е")
    for src, dst in _PHRASE_MAP:
        t = t.replace(src, dst)
    t = _PUNCT_RX.sub(" ", t)
    t = _WS_RX.sub(" ", t).strip()
    return t[:180]


def _cve_ids(text: str) -> set[str]:
    found = set()
    for m in _CVE_RX.findall(text or ""):
        norm = re.sub(r"[-\s]", "", m.lower())
        # cve202650522 → cve-2026-50522-ish key
        if len(norm) >= 10:
            found.add(norm)
    return found


_SHORT_KEEP = {"ai", "ml", "llm", "rce", "gpt", "rag", "mcp", "cve"}


def significant_tokens(title: str) -> set[str]:
    fp = title_fingerprint(title)
    out: set[str] = set()
    for tok in fp.split():
        if tok in _STOP:
            continue
        if len(tok) > 2 or tok in _SHORT_KEEP:
            out.add(tok)
    return out


def _event_hit(title: str) -> bool:
    t = title_fingerprint(title)
    return any(rx.search(t) for rx in _EVENT_RX)


def titles_near_duplicate(a: str, b: str, *, jaccard_min: float = 0.42) -> bool:
    """Перепечатки одной истории: общий CVE, org+событие, или Jaccard токенов."""
    if not a or not b:
        return False
    cves_a, cves_b = _cve_ids(a), _cve_ids(b)
    if cves_a and cves_b and cves_a & cves_b:
        return True

    ta, tb = significant_tokens(a), significant_tokens(b)
    if not ta or not tb:
        return False

    evt_a, evt_b = _event_hit(a), _event_hit(b)
    orgs = (ta & tb) & _ORG_TOKENS
    if orgs and evt_a and evt_b:
        # 2+ общих org (OpenAI+HuggingFace) — достаточно.
        if len(orgs) >= 2:
            return True
        # 1 org + security-событие в обоих + ещё ≥1 общий значимый токен
        # (ловим формулировки вроде «breach at startup» без второго имени).
        inter = (ta & tb) | {"_evt"}
        if len(inter) >= 3:
            return True

    inter = ta & tb
    if len(inter) < 3:
        return False
    return len(inter) / len(ta | tb) >= jaccard_min
