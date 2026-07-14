"""Загрузка полного текста arXiv (HTML → PDF fallback) для TBSF."""

from __future__ import annotations

import io
import re
import time

from ..ingestion.common import http_get, strip_html

_ARXIV_ID_RX = re.compile(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", re.I)
_last_fetch = 0.0
MIN_INTERVAL = 3.0  # секунд между запросами к arXiv


def arxiv_id_from_url(url: str) -> str | None:
    m = _ARXIV_ID_RX.search(url or "")
    return m.group(1) if m else None


def is_arxiv_url(url: str) -> bool:
    return "arxiv.org" in (url or "").lower()


def _throttle() -> None:
    global _last_fetch
    elapsed = time.monotonic() - _last_fetch
    if elapsed < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - elapsed)
    _last_fetch = time.monotonic()


def fetch_fulltext(arxiv_id: str, max_chars: int = 100_000) -> str:
    """HTML-версия arXiv, иначе первые страницы PDF. Пустая строка — fallback на abstract."""
    _throttle()
    try:
        resp = http_get(f"https://arxiv.org/html/{arxiv_id}", timeout=45.0)
        if resp.status_code == 200 and len(resp.text) > 8000:
            text = strip_html(resp.text)
            if len(text) > 1500:
                return text[:max_chars]
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
            return text[:max_chars]
    except Exception:  # noqa: BLE001
        pass
    return ""


def scoring_text(title: str, summary: str, full_text: str | None) -> str:
    """Текст для TBSF: abstract + полный текст (если есть)."""
    parts = [title, summary or ""]
    if full_text and full_text.strip():
        parts.append(full_text)
    return "\n\n".join(p for p in parts if p)
