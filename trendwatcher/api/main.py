from datetime import timedelta

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from ..analytics.constants import SIGNAL_WINDOW_WEEKS
from ..analytics.scoring import top_events
from ..analytics.signals import classify_signals
from ..analytics.timeseries import weekly_tag_counts
from ..config import PROJECT_ROOT
from ..db import Document, get_session, init_db, utcnow
from ..export import build_snapshot
from ..feed import build_feed

app = FastAPI(title="TrendWatcher", version="0.1.0")
init_db()


@app.get("/data.json")
def data_bundle():
    """Единый снапшот для дашборда — тот же формат, что у статического экспорта."""
    with get_session() as s:
        return build_snapshot(s)


@app.get("/api/stats")
def stats():
    with get_session() as s:
        total = s.scalar(select(func.count(Document.id)))
        by_type = dict(
            s.execute(
                select(Document.source_type, func.count(Document.id)).group_by(
                    Document.source_type
                )
            ).all()
        )
        last_fetch = s.scalar(select(func.max(Document.fetched_at)))
        last_week = s.scalar(
            select(func.count(Document.id)).where(
                Document.published_at >= utcnow() - timedelta(days=7)
            )
        )
    return {
        "total_documents": total,
        "by_source_type": by_type,
        "last_week": last_week,
        "last_fetch": last_fetch.isoformat() if last_fetch else None,
    }


@app.get("/api/top-events")
def api_top_events(days: int = Query(30, ge=1, le=120), limit: int = Query(15, ge=1, le=50)):
    with get_session() as s:
        return top_events(s, days=days, limit=limit)


@app.get("/api/trends")
def api_trends(weeks: int = Query(13, ge=2, le=52)):
    with get_session() as s:
        return weekly_tag_counts(s, weeks=weeks)


@app.get("/api/signals")
def api_signals(
    recent_weeks: int = Query(SIGNAL_WINDOW_WEEKS, ge=4, le=26),
    retro_weeks: int = Query(26, ge=13, le=52),
):
    with get_session() as s:
        return classify_signals(s, recent_weeks=recent_weeks, retro_weeks=retro_weeks)


@app.get("/api/feed")
def api_feed(
    tag: str | None = None,
    doc_type: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    with get_session() as s:
        items = build_feed(s, limit=500)
        out = []
        for d in items:
            if tag and tag not in d["tags"]:
                continue
            if doc_type and d["doc_type"] != doc_type:
                continue
            if q and q.lower() not in f"{d['title']} {d['summary']}".lower():
                continue
            out.append(d)
            if len(out) >= limit:
                break
        return out[:limit]


app.mount("/", StaticFiles(directory=PROJECT_ROOT / "web", html=True), name="web")
