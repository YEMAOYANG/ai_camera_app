"""Standalone course archive delivery. Safe to import; never imports app.py."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading

from services.course_archive_queue import (
    ArchiveQueueError, CourseArchiveProcessor, CourseArchiveQueue, CourseArchiveWorker,
    NodeArchiveClient, storage_identity,
)


ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    parser.add_argument("--limit", type=int, default=10, help="Maximum course deliveries per batch (1-1000)")
    parser.add_argument("--include-history", action="store_true",
                        help="Also scan and deliver historical PG/legacy backfill (priority 2)")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    # Loading backend configuration does not create Flask, workers or a provider.
    from core.config import AppConfig
    if os.getenv("COURSE_STORAGE_ARCHIVE_ENABLED", "false").strip().lower() not in {"true", "1"}:
        print(json.dumps({"enabled": False}))
        return 0
    from core.database import Database
    from services.course_archive_exporter import CourseArchiveExporter

    config = AppConfig.from_env()
    node = shutil.which(os.getenv("COURSE_ARCHIVE_NODE") or "node")
    if not node:
        raise ArchiveQueueError("archive_node_unavailable")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15)
    if version.returncode or not version.stdout.strip().startswith("v24."):
        raise ArchiveQueueError("archive_requires_node24")
    # The Native snapshot exporter also uses Node for producer-compatible JSON.
    os.environ["PATH"] = str(Path(node).resolve().parent) + os.pathsep + os.environ.get("PATH", "")
    storage = storage_identity(os.getenv("COURSE_STORAGE_ENDPOINT", ""),
        os.getenv("COURSE_STORAGE_BUCKET", ""), os.getenv("COURSE_STORAGE_REGION", "us-east-1"))
    queue = CourseArchiveQueue(ROOT / "backend/data/course-storage", storage)
    database = Database(config.DATABASE_URL)
    client = NodeArchiveClient(project_root=ROOT, node=node)
    processor = CourseArchiveProcessor(queue, CourseArchiveExporter(project_root=ROOT), client, database=database)
    worker = CourseArchiveWorker(queue, processor, database=database, scan_history=args.include_history)
    stopped = threading.Event()

    def stop(_signum, _frame):
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with queue.lock():
        print("course archive worker ready", flush=True)
        while not stopped.is_set():
            result = worker.run_once(limit=args.limit, stop_requested=stopped.is_set)
            print(json.dumps(result, sort_keys=True), flush=True)
            if args.once:
                return 1 if result["failed"] or result["discoveryErrors"] else 0
            stopped.wait(15)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArchiveQueueError as error:
        print(json.dumps({"error": str(error)}))
        raise SystemExit(1)
