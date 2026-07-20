"""Экспорт статического сайта: index.html + data.json со снапшотом аналитики.

Результат не требует backend — подходит для GitHub Pages, S3, nginx и т.п.
Фильтрация ленты выполняется на клиенте по выгруженному массиву документов.
"""

import json
import shutil
from datetime import timedelta

from sqlalchemy import func, select

from .analytics.scoring import top_events
from .analytics.signals import classify_signals
from .analytics.timeseries import weekly_tag_counts
from .analytics.archive import update_archive
from .config import PROJECT_ROOT
from .db import Document, get_session, init_db, utcnow
from .feed import build_feed
from .synthesis.narrative import build_trend_brief

FEED_LIMIT = 600


def build_snapshot(session, feed_limit: int = FEED_LIMIT) -> dict:
    total = session.scalar(select(func.count(Document.id)))
    by_type = dict(
        session.execute(
            select(Document.source_type, func.count(Document.id)).group_by(
                Document.source_type
            )
        ).all()
    )
    last_week = session.scalar(
        select(func.count(Document.id)).where(
            Document.published_at >= utcnow() - timedelta(days=7)
        )
    )
    feed = build_feed(session, limit=feed_limit)
    events = top_events(session, days=30, limit=15)
    signals = classify_signals(session)
    trends = weekly_tag_counts(session, weeks=13)
    archive = update_archive(session)
    trend_brief = build_trend_brief(signals, events, feed)
    return {
        "generated_at": utcnow().isoformat(),
        "archive": archive,
        "stats": {
            "total_documents": total,
            "by_source_type": by_type,
            "last_week": last_week,
        },
        "top_events": events,
        "trends": {"weeks": trends["weeks"], "series": trends["series"]},
        "signals": signals,
        "feed": feed,
        "trend_brief": trend_brief,
    }


def export_hosting() -> str:
    """Архив для загрузки на хостинг: только index.html.

    Данные подтягиваются с GitHub (DATA_URL в index.html), сервер не нужен.
    """
    site_dir = PROJECT_ROOT / "dist" / "site"
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)
    shutil.copy(PROJECT_ROOT / "web" / "index.html", site_dir / "index.html")

    stamp = utcnow().strftime("%Y-%m-%d")
    zip_path = shutil.make_archive(
        str(PROJECT_ROOT / "dist" / f"TrendWatcher_site_{stamp}"), "zip", site_dir
    )
    return zip_path


def export_site() -> tuple[str, str]:
    """Собирает dist/site и zip-архив. Возвращает (путь к site, путь к zip)."""
    init_db()
    site_dir = PROJECT_ROOT / "dist" / "site"
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)

    shutil.copy(PROJECT_ROOT / "web" / "index.html", site_dir / "index.html")
    with get_session() as session:
        snapshot = build_snapshot(session)
    with open(site_dir / "data.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, default=str)

    stamp = utcnow().strftime("%Y-%m-%d")
    zip_path = shutil.make_archive(
        str(PROJECT_ROOT / "dist" / f"TrendWatcher_static_{stamp}"), "zip", site_dir
    )
    return str(site_dir), zip_path
