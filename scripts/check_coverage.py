"""Диагностика покрытия корпуса по неделям: где данные плотные, а где дыры."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from collections import defaultdict

from sqlalchemy import select

from trendwatcher.analytics.timeseries import week_start
from trendwatcher.db import Document, get_session, init_db

init_db()
with get_session() as s:
    docs = s.scalars(select(Document)).all()

weekly_total = defaultdict(int)
weekly_by_src = defaultdict(lambda: defaultdict(int))
tag_weeks = defaultdict(set)

for d in docs:
    w = week_start(d.published_at).isoformat()
    weekly_total[w] += 1
    weekly_by_src[w][d.source_type] += 1
    for t in d.tags:
        tag_weeks[t].add(w)

print("Недельное покрытие (последние 30 недель):")
for w in sorted(weekly_total)[-30:]:
    src = weekly_by_src[w]
    print(f"  {w}: total={weekly_total[w]:<4} research={src.get('research',0):<4} "
          f"vuln={src.get('vulnerability',0):<3} news={src.get('news',0):<3} "
          f"vendor={src.get('vendor',0):<3} standards={src.get('standards',0)}")

print("\nАктивные недели по интересующим тегам (за все время):")
for t in ["self_evolving_agents", "agentic_ai", "prompt_injection", "red_teaming",
          "world_models", "data_poisoning", "reasoning_models"]:
    weeks = sorted(tag_weeks.get(t, []))
    print(f"  {t:<22}: {len(weeks)} нед., от {weeks[0] if weeks else '-'} до {weeks[-1] if weeks else '-'}")
