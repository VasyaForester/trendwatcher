"""CLI TrendWatcher: python run.py ingest | backfill-signals | export | ..."""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="TrendWatcher CLI")
    parser.add_argument(
        "command",
        choices=[
            "ingest",
            "serve",
            "analyze",
            "retag",
            "export",
            "export-site",
            "score-tbsf",
            "archive",
            "backfill-signals",
            "diet",
            "restore-db",
        ],
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Календарный год для backfill-signals",
    )
    parser.add_argument(
        "--rebuild-weeks",
        type=int,
        default=0,
        help="Для archive: перезаписать N последних недель (0 = только missing)",
    )
    args = parser.parse_args()

    if args.command == "ingest":
        from trendwatcher.ingestion.runner import run_all

        run_all()
    elif args.command == "backfill-signals":
        from trendwatcher.analytics.archive import rebuild_weekly_snapshots, update_archive
        from trendwatcher.db import get_session, init_db
        from trendwatcher.ingestion.backfill import backfill_signal_year

        info = backfill_signal_year(year=args.year)
        print(json.dumps({"backfill": info}, ensure_ascii=False, indent=2))
        from datetime import datetime

        start = datetime.fromisoformat(info["from"])
        end = datetime.fromisoformat(info["to"])
        weeks = max(int((end - start).days / 7) + 1, 1)
        init_db()
        with get_session() as s:
            rebuilt = rebuild_weekly_snapshots(s, weeks=weeks)
            arch = update_archive(s)
        print(
            json.dumps(
                {"archive_rebuild_weeks": rebuilt, "archive": arch},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "restore-db":
        from trendwatcher.ingestion.restore import restore_db_from_ledger

        info = restore_db_from_ledger(replace=True)
        print(json.dumps(info, ensure_ascii=False, indent=2))
    elif args.command == "diet":
        from trendwatcher.db import get_session, init_db
        from trendwatcher.ingestion.compact import compact_stats, diet_documents, vacuum_db

        init_db()
        with get_session() as s:
            result = diet_documents(s)
        vacuum_db()
        print(json.dumps({"diet": result, "stats": compact_stats()}, ensure_ascii=False, indent=2))
    elif args.command == "retag":
        from trendwatcher.ingestion.runner import retag_all

        retag_all()
    elif args.command == "export":
        from trendwatcher.export import export_site

        site_dir, zip_path = export_site()
        print(f"site:    {site_dir}")
        print(f"archive: {zip_path}")
    elif args.command == "score-tbsf":
        from trendwatcher.db import get_session, init_db
        from trendwatcher.ingestion.compact import diet_documents, vacuum_db
        from trendwatcher.tbsf.batch import rescore_all, rescore_recent

        init_db()
        with get_session() as s:
            # Сначала окно топ-событий с full_text, затем лёгкий проход по остальному.
            # Бюджет сетевых скачиваний: кэш на диске/Actions закрывает повторные прогоны.
            n_recent = rescore_recent(s, days=35, budget=80)
            n_all = rescore_all(s, fetch_fulltext=False)
            diet = diet_documents(s)
        vacuum_db()
        print(
            f"scored recent={n_recent} all={n_all}; diet={diet}"
        )
    elif args.command == "archive":
        from trendwatcher.analytics.archive import update_archive
        from trendwatcher.db import get_session, init_db

        init_db()
        with get_session() as s:
            info = update_archive(
                s,
                rebuild_weeks=args.rebuild_weeks if args.rebuild_weeks else None,
            )
        print(json.dumps(info, ensure_ascii=False, indent=2))
    elif args.command == "export-site":
        from trendwatcher.export import export_hosting

        zip_path = export_hosting()
        print(f"archive: {zip_path}")
        print("upload index.html to hosting root — data loads from GitHub Actions")
    elif args.command == "serve":
        import uvicorn

        uvicorn.run("trendwatcher.api.main:app", host="127.0.0.1", port=args.port)
    elif args.command == "analyze":
        from trendwatcher.analytics.scoring import top_events
        from trendwatcher.analytics.signals import classify_signals
        from trendwatcher.db import get_session, init_db

        init_db()
        with get_session() as s:
            report = {
                "top_events": top_events(s, days=30, limit=10),
                "signals": classify_signals(s),
            }
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
