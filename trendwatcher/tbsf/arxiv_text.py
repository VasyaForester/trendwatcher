"""Загрузка полного текста arXiv (HTML → PDF fallback) для TBSF."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

from ..ingestion.common import http_get, strip_html

_ARXIV_ID_RX = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", re.I)
_last_fetch = 0.0
MIN_INTERVAL = 3.0  # секунд между запросами к arXiv

# Диск-кэш: в CI переживает прогоны через actions/cache (БД каждый раз с нуля).
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "fulltext_cache"


def arxiv_id_from_url(url: str) -> str | None:
    m = _ARXIV_ID_RX.search(url or "")
    return m.group(1) if m else None


def is_arxiv_url(url: str) -> bool:
    return "arxiv.org" in (url or "").lower()


def _cache_path(arxiv_id: str) -> Path:
    safe = arxiv_id.replace("/", "_")
    return CACHE_DIR / f"{safe}.txt"


def _read_cache(arxiv_id: str) -> str | None:
    path = _cache_path(arxiv_id)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return text if len(text) > 400 else None


def read_fulltext_cache(arxiv_id: str) -> str | None:
    """Публичное чтение кэша (без сети)."""
    return _read_cache(arxiv_id)


def _write_cache(arxiv_id: str, text: str) -> None:
    if len(text) <= 400:
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(arxiv_id).write_text(text, encoding="utf-8")
    except OSError:
        pass


def _throttle() -> None:
    global _last_fetch
    elapsed = time.monotonic() - _last_fetch
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_fetch = time.monotonic()


def fetch_fulltext(arxiv_id: str, max_chars: int = 100_000) -> str:
    """HTML-версия arXiv, иначе первые страницы PDF. Пустая строка — fallback на abstract."""
    cached = _read_cache(arxiv_id)
    if cached:
        return cached[:max_chars]

    _throttle()
    try:
        resp = http_get(f"https://arxiv.org/html/{arxiv_id}", timeout=45.0)
        if resp.status_code == 200 and len(resp.text) > 8000:
            text = strip_html(resp.text)
            if len(text) > 1500:
                text = text[:max_chars]
                _write_cache(arxiv_id, text)
                return text
    except Exception:  # noqa: BLE001
        pass

    _throttle()
    try:
        from pypdf import PdfReader

        resp = http_get(f"https://arxiv.org/pdf/{arxiv_id}.pdf", timeout=90.0)
        reader = PdfReader(io.BytesIO(resp.content))
        chunks: list[str] = []
        for page in reader.pages[:35]:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks)
        if len(text) > 400:
            text = text[:max_chars]
            _write_cache(arxiv_id, text)
            return text
    except Exception:  # noqa: BLE001
        pass
    return ""


def scoring_text(title: str, summary: str, full_text: str | None) -> str:
    """Текст для TBSF: abstract + полный текст (если есть)."""
    parts = [title, summary or ""]
    if full_text and full_text.strip():
        parts.append(full_text)
    return "\n\n".join(p for p in parts if p)
