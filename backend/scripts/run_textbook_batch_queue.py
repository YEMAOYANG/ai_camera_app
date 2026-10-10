"""Run a resumable whole-catalog private queue; publication is never enabled.

init/admit-index/prepare/status are provider-free. run-once/watch may start paid
jobs only under an explicit action. Watch requires either a total start bound
or --continuous; each iteration still has at most two native generation jobs.
"""
import argparse
import json
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.textbook_batch_queue_service import TextbookBatchQueueService


def log_result(value, directory):
    """Keep heartbeat logs small; complete edition statistics stay on disk."""
    if isinstance(value, dict):
        value = dict(value)
        key = "summary" if "summary" in value else None
        summary = value.get(key) if key else value
        if isinstance(summary, dict) and "by" in summary:
            compact = {**summary, "by": {key: groups for key, groups in summary["by"].items()
                                            if key != "editionId"},
                       "completeSummaryPath": str(directory.resolve() / "latest-summary.json")}
            if key:
                value[key] = compact
            else:
                value = compact
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    for action in ("init", "admit-index", "prepare", "status", "run-once", "watch", "hold-task"):
        actions.add_argument("--" + action, action="store_true")
    parser.add_argument("--queue-directory", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--authoring-index", type=Path)
    parser.add_argument("--enrich-existing", action="store_true")
    parser.add_argument("--navigation-drafts", action="store_true",
                        help="Explicitly allow directory-navigation drafts pending quality review")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--max-starts", type=int, help="Total paid job starts allowed in this invocation")
    parser.add_argument("--continuous", action="store_true", help="Explicit watch until stopped, including waiting for new admissions")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--min-free-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--hold-reason", help="Reason for an immutable provider-free task dispatch hold")
    parser.add_argument("--narrate-generated", action="store_true",
                        help="Explicit paid serial audio phase; standalone or after each watch/run-once tick")
    parser.add_argument("--audio-limit", type=int, default=1)
    parser.add_argument("--resume-audio", action="store_true",
                        help="Explicitly continue unstarted segments after a stopped audio attempt; prior POSTs remain fenced")
    parser.add_argument("--classroom-directory", type=Path)
    for name in ("task-id", "subject", "grade", "edition", "volume", "kind"):
        parser.add_argument("--" + name, action="append")
    args = parser.parse_args(argv)
    generation_action = any(getattr(args, action) for action in ("init", "admit_index", "prepare", "status", "run_once", "watch", "hold_task"))
    if not generation_action and not args.narrate_generated:
        parser.error("an action is required")
    if args.narrate_generated and generation_action and not (args.watch or args.run_once):
        parser.error("--narrate-generated combines only with --watch/--run-once")
    if args.resume_audio and not args.narrate_generated:
        parser.error("--resume-audio requires --narrate-generated")
    if not 1 <= args.audio_limit <= 24 or not 1 <= args.limit <= 200:
        parser.error("audio limit must be 1..24 and prepare limit 1..200")
    if args.init and not args.tasks:
        parser.error("--init requires --tasks")
    if args.admit_index and not args.authoring_index:
        parser.error("--admit-index requires --authoring-index")
    if args.hold_task and (not args.task_id or not args.hold_reason):
        parser.error("--hold-task requires explicit --task-id and --hold-reason")
    if args.hold_reason and not args.hold_task:
        parser.error("--hold-reason applies only to --hold-task")
    if not args.init and (args.tasks or args.enrich_existing or args.navigation_drafts):
        parser.error("tasks/enrichment/navigation policy is immutable at init")
    if args.authoring_index and not (args.init or args.admit_index):
        parser.error("authoring index is admitted explicitly at init/admit-index")
    if args.watch and ((args.max_starts is None) == (not args.continuous)):
        parser.error("--watch requires exactly one of --max-starts or --continuous")
    if args.continuous and not args.watch:
        parser.error("--continuous applies only to --watch")
    if args.max_starts is not None and args.max_starts < 0:
        parser.error("--max-starts cannot be negative")
    if not 15 <= args.poll_seconds <= 3600 or args.min_free_bytes < 1:
        parser.error("poll interval must be 15..3600 seconds and free-space minimum positive")
    filters = {key: getattr(args, flag) for key, flag in (
        ("taskId", "task_id"), ("subject", "subject"), ("gradeCode", "grade"),
        ("editionId", "edition"), ("volume", "volume"), ("kind", "kind"))}
    try:
        runtime = None
        if args.run_once or args.watch or args.narrate_generated:
            from core.config import AppConfig
            from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
            config = AppConfig.from_env()
            runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                formal_audio_internal_token=config.INTERNAL_API_TOKEN)
        service = TextbookBatchQueueService(args.queue_directory, runtime,
            minimum_free_bytes=args.min_free_bytes)
        audio = None
        if args.narrate_generated:
            from services.textbook_batch_queue_audio_service import TextbookBatchQueueAudioService
            options = {"classroom_directory": args.classroom_directory} if args.classroom_directory else {}
            audio = TextbookBatchQueueAudioService(service, **options)
        if args.init:
            result = service.initialize(args.tasks, enrich_existing=args.enrich_existing,
                                        navigation_drafts=args.navigation_drafts)
            if args.authoring_index:
                service.admit_index(args.authoring_index)
                result = service.status()
        elif args.admit_index:
            result = service.admit_index(args.authoring_index)
        elif args.prepare:
            result = service.prepare(limit=args.limit, filters=filters)
        elif args.hold_task:
            result = service.hold_tasks(args.task_id, reason=args.hold_reason)
        elif args.status:
            result = service.status()
        elif args.run_once:
            result = service.run_once(max_starts=min(2, args.max_starts if args.max_starts is not None else 2), filters=filters)
            if audio:
                result["audioResults"] = audio.narrate(limit=args.audio_limit, filters=filters, continue_audio=args.resume_audio)
                result["summary"] = service.refresh_summary()
        elif not args.watch:
            result = {"audioResults": audio.narrate(limit=args.audio_limit, filters=filters,
                                                   continue_audio=args.resume_audio), "summary": service.refresh_summary()}
        else:
            stopping = False
            def stop(_signum, _frame):
                nonlocal stopping
                stopping = True
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            starts = 0
            while not stopping:
                remaining = 2 if args.continuous else min(2, args.max_starts - starts)
                result = service.run_once(max_starts=remaining, filters=filters)
                starts += len(result["started"])
                if audio:
                    result["audioResults"] = audio.narrate(limit=args.audio_limit, filters=filters,
                                                           continue_audio=args.resume_audio)
                    result["summary"] = service.refresh_summary()
                log_result({"startsThisInvocation": starts, **result}, args.queue_directory)
                summary = result["summary"]
                if not args.continuous and not summary["occupiedJobSlots"] and (starts >= args.max_starts
                        or not result["started"] and not result["polled"]) and not result.get("audioResults"):
                    break
                # Interruptible short sleeps keep SIGTERM responsive; no new call
                # is made after a stop request. In-flight receipts remain durable.
                deadline = time.monotonic() + args.poll_seconds
                while not stopping and time.monotonic() < deadline:
                    time.sleep(min(1, max(0, deadline - time.monotonic())))
            return 0
        log_result(result, args.queue_directory)
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Inspect durable local queue state before resuming"
        print(json.dumps({"ok": False, "errorType": type(exc).__name__, "message": message,
                          "publicationAllowed": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
