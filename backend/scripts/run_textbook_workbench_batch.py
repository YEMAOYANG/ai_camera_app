"""Operate an exact v4 workbench draft batch without weakening per-course gates.

``init``, ``prepare`` and ``hold`` never create a workbench session. ``status``
is GET-only.  Explicit ``start-bounded`` and ``watch-bounded`` actions may
create sessions; both require a 1..2 start cap and the exact frozen batch
SHA256.  Watch also requires a finite total-start budget, stops on the first
quality/transport blocker, and never turns generated output into publication.
"""
import argparse
import json
from pathlib import Path
import re
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.openmaic_workbench_client import WorkbenchError
from services.textbook_workbench_batch import TextbookWorkbenchBatch


WATCH_SCHEMA = "mira.operator.workbench-batch-watch.v1"


def _authoring(origin=None):
    # Keep provider-free init/hold and CLI validation importable even when the
    # runtime/database dependency set is intentionally absent.
    from core.config import AppConfig
    from core.database import Database
    from repositories.textbook_repository import TextbookRepository
    from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, WorkbenchCatalogGuard

    config = AppConfig.from_env()
    return TextbookWorkbenchAuthoring(
        WorkbenchCatalogGuard(TextbookRepository(Database(config.DATABASE_URL))),
        ROOT.parent / "output/textbook-operator-lessons",
        origin=origin or config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
    )


def _batch_complete(summary):
    entries = summary.get("entries") if isinstance(summary, dict) else None
    return bool(entries) and all(
        row.get("held") or row.get("status") in {"held", "saved_stage_available"}
        for row in entries
    )


def _batch_completion_status(summary):
    if not _batch_complete(summary):
        return None
    return ("completed_with_holds" if any(
        row.get("held") or row.get("status") == "held" for row in summary["entries"])
        else "completed")


def _batch_active_count(summary):
    return sum(
        not row.get("held") and row.get("status") in {"session_queued", "session_running"}
        for row in summary.get("entries", [])
    )


def _batch_ready_count(summary):
    return sum(
        not row.get("held") and row.get("status") in {"prepared", "prepared_snapshot"}
        for row in summary.get("entries", [])
    )


def _require_watch_identity(summary, confirm_batch_sha256):
    if (not isinstance(summary, dict)
            or summary.get("batchSha256") != confirm_batch_sha256):
        raise ValueError("workbench_batch_confirmation_mismatch")


def _watch_result(status, *, summary, starts, polls, max_total_starts, blockers=None):
    completed = status in {"completed", "completed_with_holds"}
    return {"schemaVersion": WATCH_SCHEMA, "ok": completed, "watchStatus": status,
            "batchId": (summary or {}).get("batchId"),
            "batchSha256": (summary or {}).get("batchSha256"),
            "startsThisInvocation": starts, "pollsThisInvocation": polls,
            "maximumTotalStarts": max_total_starts,
            "blockers": blockers or [], "summary": summary,
            "generatedDraftsAreReviewed": False, "audioCompleted": False,
            "publicationAllowed": False, "studentDeliveryAllowed": False}


def _watch_heartbeat(summary, *, starts, polls, max_total_starts):
    return {"schemaVersion": WATCH_SCHEMA, "watchStatus": "running",
            "batchId": summary.get("batchId"), "batchSha256": summary.get("batchSha256"),
            "startsThisInvocation": starts, "pollsThisInvocation": polls,
            "maximumTotalStarts": max_total_starts,
            "statusCounts": summary.get("statusCounts", {}),
            "occupiedAuthorSessions": summary.get("occupiedAuthorSessions"),
            "maximumConcurrentAuthorSessions": summary.get("maximumConcurrentAuthorSessions"),
            "publicationAllowed": False, "studentDeliveryAllowed": False}


def _interruptible_wait(seconds, stop_requested, *, sleeper=time.sleep, clock=time.monotonic):
    deadline = clock() + seconds
    while not stop_requested() and clock() < deadline:
        sleeper(min(1, max(0, deadline - clock())))


def _watch_bounded(batch, *, max_starts, max_total_starts, confirm_batch_sha256,
                   poll_seconds, stop_requested=lambda: False,
                   wait=_interruptible_wait, emit=lambda _value: None):
    """Keep two safe author slots full without weakening per-course gates."""
    if (max_starts not in (1, 2) or not 1 <= max_total_starts <= 8
            or not 15 <= poll_seconds <= 3600
            or re.fullmatch(r"[0-9a-f]{64}", str(confirm_batch_sha256)) is None):
        raise ValueError("workbench_batch_watch_contract_invalid")
    starts = polls = 0
    summary = None
    while True:
        if stop_requested():
            return _watch_result("stopped_by_signal", summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts)
        summary = batch.status()
        polls += 1
        _require_watch_identity(summary, confirm_batch_sha256)
        entry_blockers = [row for row in summary.get("dispatchBlockers", [])
                          if row.get("scope") == "batch_entry"]
        if entry_blockers:
            return _watch_result("blocked", summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts, blockers=entry_blockers)
        completion = _batch_completion_status(summary)
        if completion:
            return _watch_result(completion, summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts)
        external_blockers = [row for row in summary.get("dispatchBlockers", [])
                             if row.get("scope") == "external_authoring"]
        if external_blockers:
            return _watch_result("blocked", summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts, blockers=external_blockers)

        remaining = max_total_starts - starts
        available = max(0, int(summary.get("maximumConcurrentAuthorSessions", 0))
                        - int(summary.get("occupiedAuthorSessions", 0)))
        for _index in range(min(max_starts, remaining, available)):
            if stop_requested():
                return _watch_result("stopped_by_signal", summary=summary, starts=starts, polls=polls,
                                     max_total_starts=max_total_starts)
            operation = batch.start_bounded(max_starts=1,
                confirm_batch_sha256=confirm_batch_sha256, stop_on_blockers=True)
            attempts = operation.get("startAttempts", [])
            starts += len(attempts)
            summary = operation["summary"]
            _require_watch_identity(summary, confirm_batch_sha256)
            blockers = summary.get("dispatchBlockers", [])
            if blockers:
                return _watch_result("blocked", summary=summary, starts=starts, polls=polls,
                                     max_total_starts=max_total_starts, blockers=blockers)
            completion = _batch_completion_status(summary)
            if completion:
                return _watch_result(completion, summary=summary, starts=starts, polls=polls,
                                     max_total_starts=max_total_starts)
            if not attempts or int(summary.get("occupiedAuthorSessions", 0)) >= int(
                    summary.get("maximumConcurrentAuthorSessions", 0)):
                break

        emit(_watch_heartbeat(summary, starts=starts, polls=polls,
                              max_total_starts=max_total_starts))
        if starts >= max_total_starts and not _batch_active_count(summary):
            reason = "start_budget_exhausted" if _batch_ready_count(summary) else "wave_not_terminal"
            return _watch_result(reason, summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts,
                                 blockers=[{"scope": "watch", "reason": reason}])
        if (not _batch_active_count(summary) and not _batch_ready_count(summary)
                and not summary.get("externalOccupiedAuthorSessions")):
            return _watch_result("no_dispatchable_entries", summary=summary, starts=starts, polls=polls,
                                 max_total_starts=max_total_starts,
                                 blockers=[{"scope": "watch", "reason": "no_dispatchable_entries"}])
        wait(poll_seconds, stop_requested)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "prepare", "status", "start-bounded",
                                           "watch-bounded", "hold"))
    parser.add_argument("--queue-directory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-starts", type=int,
                        help="maximum new sessions per action/tick; must be 1 or 2")
    parser.add_argument("--max-total-starts", type=int,
                        help="watch-only cap on new session attempts in this invocation")
    parser.add_argument("--poll-seconds", type=int,
                        help="watch-only GET polling interval; defaults to 15 seconds")
    parser.add_argument("--confirm-batch-sha256",
                        help="exact SHA256 printed by init/status; required before any new session")
    parser.add_argument("--entry-id", action="append")
    parser.add_argument("--reason")
    parser.add_argument("--origin")
    args = parser.parse_args(argv)

    if args.action == "init":
        if not args.manifest:
            parser.error("init requires --manifest")
        if any(value is not None for value in (args.limit, args.max_starts,
                                                args.max_total_starts, args.poll_seconds,
                                                args.confirm_batch_sha256, args.entry_id, args.reason, args.origin)):
            parser.error("init accepts only --manifest and --queue-directory")
    elif args.manifest is not None:
        parser.error("--manifest applies only to init")

    if args.action == "prepare":
        if args.limit is None:
            args.limit = 8
        if not 1 <= args.limit <= 200:
            parser.error("prepare --limit must be 1..200")
    elif args.limit is not None:
        parser.error("--limit applies only to prepare")

    if args.action in {"start-bounded", "watch-bounded"}:
        if args.max_starts not in (1, 2):
            parser.error(args.action + " requires --max-starts 1 or 2")
        if (not isinstance(args.confirm_batch_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", args.confirm_batch_sha256) is None):
            parser.error(args.action + " requires --confirm-batch-sha256")
    elif args.max_starts is not None or args.confirm_batch_sha256 is not None:
        parser.error("start confirmation arguments apply only to start-bounded/watch-bounded")

    if args.action == "watch-bounded":
        if args.max_total_starts is None or not 1 <= args.max_total_starts <= 8:
            parser.error("watch-bounded requires --max-total-starts 1..8")
        if args.poll_seconds is None:
            args.poll_seconds = 15
        if not 15 <= args.poll_seconds <= 3600:
            parser.error("watch-bounded --poll-seconds must be 15..3600")
    elif args.max_total_starts is not None or args.poll_seconds is not None:
        parser.error("--max-total-starts/--poll-seconds apply only to watch-bounded")

    if args.action == "hold":
        if not args.entry_id or not args.reason:
            parser.error("hold requires --entry-id and --reason")
    elif args.entry_id is not None or args.reason is not None:
        parser.error("--entry-id/--reason apply only to hold")
    if args.origin is not None and args.action not in {"prepare", "status", "start-bounded", "watch-bounded"}:
        parser.error("--origin applies only to prepare/status/start-bounded/watch-bounded")

    try:
        if args.action == "init":
            result = TextbookWorkbenchBatch(args.queue_directory).initialize(args.manifest)
        elif args.action == "hold":
            # A hold is a local immutable dispatch fence and does not load the
            # database, runtime origin, owner cookie or HTTP client.
            result = TextbookWorkbenchBatch(args.queue_directory).hold(args.entry_id, reason=args.reason)
        else:
            batch = TextbookWorkbenchBatch(args.queue_directory, _authoring(args.origin))
            if args.action == "prepare":
                result = batch.prepare(limit=args.limit)
            elif args.action == "status":
                result = batch.status()
            elif args.action == "start-bounded":
                result = batch.start_bounded(max_starts=args.max_starts,
                                             confirm_batch_sha256=args.confirm_batch_sha256)
            else:
                stopping = False

                def stop(_signum, _frame):
                    nonlocal stopping
                    stopping = True

                previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
                for signum in previous:
                    signal.signal(signum, stop)
                try:
                    result = _watch_bounded(batch, max_starts=args.max_starts,
                        max_total_starts=args.max_total_starts,
                        confirm_batch_sha256=args.confirm_batch_sha256,
                        poll_seconds=args.poll_seconds, stop_requested=lambda: stopping,
                        emit=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
                finally:
                    for signum, handler in previous.items():
                        signal.signal(signum, handler)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.action != "watch-bounded" or result.get("ok") else 1
    except (WorkbenchError, ValueError) as exc:
        error = exc.code if isinstance(exc, WorkbenchError) else str(exc)
        message = str(exc) if isinstance(exc, (WorkbenchError, ValueError)) else "batch operation failed"
        print(json.dumps({"ok": False, "error": error, "message": message,
                          "publicationAllowed": False}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:
        # Do not place raw database, filesystem, cookie or transport details in
        # an aggregate operator response.
        print(json.dumps({"ok": False, "error": "workbench_batch_operation_failed",
                          "errorType": type(exc).__name__,
                          "message": "请检查冻结批次和逐课任务状态后继续；不会自动重派",
                          "publicationAllowed": False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
