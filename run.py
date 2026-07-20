"""CLI TrendWatcher: python run.py ingest | serve | analyze"""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="TrendWatcher CLI")
    parser.add_argument("command", choices=["ingest", "serve", "analyze", "retag", "export", "export-site", "score-tbsf", "archive"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.command == "ingest":
        from trendwatcher.ingestion.runner import run_all

        run_all()
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
        from trendwatcher.tbsf.batch import rescore_all

        init_db()
        with get_session() as s:
            n = rescore_all(s)
        print(f"scored {n} research documents with TBSF")
    elif args.command == "archive":
        from trendwatcher.db import get_session, init_db
        from trendwatcher.analytics.archive import update_archive

        init_db()
        with get_session() as s:
            info = update_archive(s)
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
