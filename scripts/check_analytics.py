"""Быстрая smoke-проверка аналитики на собранных данных."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from trendwatcher.analytics.scoring import top_events
from trendwatcher.analytics.signals import classify_signals
from trendwatcher.db import get_session, init_db

init_db()
with get_session() as s:
    events = top_events(s, days=30, limit=10)
    signals = classify_signals(s)

print("top events:", len(events))
for e in events[:8]:
    if e.get("score_type") == "tbsf":
        print(f"  TBSF {e['score']:>3}% {e.get('tbsf_vector',''):<15} | {e['title'][:70]}")
    else:
        print(f"  comp {e['score']:>5} | {e['doc_type']:<13} | {e['title'][:70]}")

print("\nsignals:", len(signals))
for sg in signals:
    print(
        f"  {sg['level']:<9} | {sg['category']:<8} | {sg['tag']:<22} | "
        f"recent={sg['recent']:<3} share={sg['recent_share']} base_share={sg['baseline_share']} "
        f"age={sg['age_weeks']}w long={int(sg['long_running'])}"
    )
    print(f"            {sg['reason']}")
