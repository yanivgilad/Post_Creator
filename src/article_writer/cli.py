from __future__ import annotations

import argparse

import uvicorn

from article_writer.config import get_settings
from article_writer.logging_setup import setup_logging
from article_writer.pipeline.run_daily import DailyPipeline
from article_writer.storage.sqlite_store import SQLiteStore
from article_writer.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local AI trends website and pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the local website and scheduler")
    serve.add_argument("--host", help="Host override")
    serve.add_argument("--port", type=int, help="Port override")

    subparsers.add_parser("init-db", help="Create the local SQLite schema")
    subparsers.add_parser("run-once", help="Execute one pipeline run immediately")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(settings)

    if args.command == "init-db":
        store = SQLiteStore(settings)
        store.init_db()
        print("Database initialized")
        return

    if args.command == "run-once":
        store = SQLiteStore(settings)
        store.init_db()
        pipeline = DailyPipeline(settings, store)
        run_id = pipeline.run("cli")
        print(f"Completed run {run_id}")
        return

    if args.command == "serve":
        app = create_app(settings, start_scheduler=True)
        uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)
        return

    parser.error("Unknown command")
