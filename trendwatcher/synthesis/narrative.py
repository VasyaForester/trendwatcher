"""Гибридный обзор трендов: facts → OpenAI, иначе шаблон; кеш по facts_hash."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import httpx

from ..analytics.constants import SIGNAL_WINDOW_WEEKS
from ..config import PROJECT_ROOT
from ..db import utcnow
from .facts import build_facts_pack

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """Ты аналитик трендов AI и AI security. Пишешь нейтральный обзор на русском.
Правила:
- Используй ТОЛЬКО факты из JSON пользователя. Не выдумывай цифры, темы и статьи.
- Тон спокойный, без маркетинга и кликбейта.
- 4 коротких абзаца (по 2–4 предложения).
- Структура:
  1) Обзор AI-трендов за окно (self-evolving agents, agentic AI, reasoning и т.п. — если есть в фактах).
  2) Какие темы чаще звучат в контексте безопасности AI.
  3) Новая/ускоряющаяся тема и почему она может изменить ландшафт угроз (только если есть emerging/research в фактах).
  4) Зрелая часто упоминаемая угроза и динамика (рост/спад/стабильность) — если есть в mature_or_declining или security_signals.
- Упоминай числа публикаций и динамику из фактов там, где это уместно.
- Не используй markdown, списки и заголовки — только абзацы, разделённые пустой строкой."""


def facts_hash(facts: dict) -> str:
    payload = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _fmt_signal_list(items: list[dict], *, with_vel: bool = True) -> str:
    parts = []
    for s in items:
        chunk = f'{s["label"]} ({s["level"]}, {s["recent"]} публ.'
        if with_vel:
            chunk += f', {s.get("velocity_label", "")}'
        chunk += ")"
        parts.append(chunk)
    return "; ".join(parts) if parts else "недостаточно данных"


def render_template(facts: dict) -> list[str]:
    """Детерминированный нейтральный текст из пакета фактов."""
    weeks = facts.get("window_weeks", SIGNAL_WINDOW_WEEKS)
    ai = facts.get("ai_tech_signals") or []
    sec = facts.get("security_signals") or []
    emerging = facts.get("emerging_signals") or []
    mature = facts.get("mature_or_declining") or []
    papers = facts.get("arxiv_papers") or []

    if ai:
        ai_bits = _fmt_signal_list(ai[:4])
        p1 = (
            f"За прошедшие {weeks} недель (~3 месяца) в корпусе публикаций TrendWatcher "
            f"наблюдаются следующие тренды в области AI: {ai_bits}."
        )
    else:
        p1 = (
            f"За прошедшие {weeks} недель (~3 месяца) устойчивых AI-трендов по ключевым "
            "тегам пока недостаточно для уверенного обзора — данных мало или они шумные."
        )

    if sec:
        top_sec = ", ".join(f'{s["label"]} ({s["recent"]} публ.)' for s in sec[:5])
        p2 = (
            f"В контексте безопасности AI чаще всего звучат такие темы: {top_sec}. "
            "Оценка опирается на долю упоминаний в корпусе и классификацию сигналов."
        )
    else:
        p2 = (
            "В контексте безопасности AI за окно наблюдения не удалось выделить "
            "устойчивый набор доминирующих тем."
        )

    if emerging:
        e = emerging[0]
        paper_hint = ""
        if papers:
            paper_hint = f" Среди заметных работ на arXiv — «{papers[0]['title'][:120]}»."
        p3 = (
            f"Обращает на себя внимание тема «{e['label']}» ({e['level']}, "
            f"{e['recent']} публ., {e.get('velocity_label', '')}): "
            f"{e.get('reason') or 'ускорение относительно предыдущего периода'}. "
            f"Потенциально она способна изменить ландшафт угроз и поверхность атак агентных систем."
            f"{paper_hint}"
        )
    else:
        p3 = (
            "Ярко выраженной новой технологии с устойчивым ускорением за окно "
            "наблюдения в текущем срезе не зафиксировано."
        )

    if mature:
        m = mature[0]
        trend = "падает" if (m.get("velocity") or 0) < -0.05 else "стабилизируется"
        p4 = (
            f"Тема «{m['label']}» остаётся одной из наиболее часто упоминаемых "
            f"({m['recent']} публ. за ~3 месяца), однако число/доля таких публикаций {trend} "
            f"({m.get('velocity_label', '')})."
        )
    elif sec:
        m = sec[0]
        p4 = (
            f"Наиболее объёмная security-тема сейчас — «{m['label']}» "
            f"({m['recent']} публ., уровень {m['level']}, {m.get('velocity_label', '')})."
        )
    else:
        p4 = "По зрелым угрозам за окно наблюдения отдельный сигнал выделить не удалось."

    return [p1, p2, p3, p4]


def _parse_paragraphs(text: str) -> list[str]:
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text.strip()) if c.strip()]
    if len(chunks) >= 3:
        return chunks[:6]
    # fallback: split by sentences into ~4 blocks
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return []
    n = max(1, len(sentences) // 4)
    out = []
    for i in range(0, len(sentences), n):
        out.append(" ".join(sentences[i : i + n]))
    return out[:6]


def call_openai(
    facts: dict,
    api_key: str,
    *,
    model: str | None = None,
    timeout: float = 60.0,
) -> list[str]:
    model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
    user_content = (
        "Сформируй обзор по следующим фактам (JSON):\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
    )
    payload = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(OPENAI_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    paragraphs = _parse_paragraphs(text)
    if len(paragraphs) < 3:
        raise ValueError("OpenAI returned too few paragraphs")
    return paragraphs


def load_previous_brief(paths: list[Path] | None = None) -> dict | None:
    candidates = paths or [
        PROJECT_ROOT / "data.json",
        PROJECT_ROOT / "dist" / "site" / "data.json",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            brief = data.get("trend_brief")
            if isinstance(brief, dict) and brief.get("paragraphs"):
                return brief
        except (OSError, json.JSONDecodeError):
            continue
    return None


def build_trend_brief(
    signals: list[dict],
    top_events: list[dict],
    feed: list[dict],
    *,
    previous: dict | None = None,
    api_key: str | None = None,
    use_llm: bool = True,
) -> dict:
    """Собирает trend_brief: кеш → LLM → template fallback."""
    facts = build_facts_pack(signals, top_events, feed)
    fhash = facts_hash(facts)
    prev = previous if previous is not None else load_previous_brief()

    if (
        prev
        and prev.get("facts_hash") == fhash
        and isinstance(prev.get("paragraphs"), list)
        and len(prev["paragraphs"]) >= 3
    ):
        return {
            "window_weeks": facts["window_weeks"],
            "generated_at": prev.get("generated_at") or utcnow().isoformat(),
            "mode": prev.get("mode", "template"),
            "facts_hash": fhash,
            "paragraphs": prev["paragraphs"],
            "highlights": facts["highlights"],
            "sources": facts["sources"],
        }

    key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "").strip()
    mode = "template"
    paragraphs: list[str]

    if use_llm and key:
        try:
            paragraphs = call_openai(facts, key)
            mode = "llm"
        except Exception:
            paragraphs = render_template(facts)
            mode = "template"
    else:
        paragraphs = render_template(facts)

    return {
        "window_weeks": facts["window_weeks"],
        "generated_at": utcnow().isoformat(),
        "mode": mode,
        "facts_hash": fhash,
        "paragraphs": paragraphs,
        "highlights": facts["highlights"],
        "sources": facts["sources"],
    }
