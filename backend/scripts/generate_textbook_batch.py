"""Prepare or run at most two exact private authoring tasks; never publish.

prepare/status need no provider configuration. start sends a paid request only
for an untouched durable reservation; poll repeats GET only. Ambiguous outcomes
stay fenced for reconciliation. This operator never imports/migrates a database.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.textbook_batch_generation import KINDS, freeze_input
from services.textbook_batch_generation_service import TextbookBatchGenerationService


def matches(task, args):
    scope = task.get("scope", task.get("binding", {}))
    return (not args.task_id or task.get("taskId") in args.task_id) and (
        not args.kind or task.get("kind") == args.kind) and (
        not args.subject or scope.get("subject") == args.subject) and (
        not args.grade or scope.get("gradeCode") == args.grade) and (
        not getattr(args, "volume", None) or scope.get("volume") == args.volume) and (
        not getattr(args, "edition", None) or scope.get("editionId") == args.edition)


def select_tasks(path, args):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            task = json.loads(line)
            if not matches(task, args):
                continue
            if task.get("originalContent") is not None and not args.enrich_existing:
                if args.task_id:
                    raise ValueError("Task already has original content; use --enrich-existing explicitly")
                continue
            if task.get("directoryCoverage", {}).get("status") == "index_only":
                if args.task_id:
                    raise ValueError("Exact task has no official directory")
                continue
            if task.get("kind") == "lesson_courseware" and not args.reviewed_scope:
                if args.task_id or args.kind == "lesson_courseware":
                    raise ValueError("Lesson requires --reviewed-scope")
                continue
            yield task


def select_inputs(path, args, service):
    """Advance bounded preparation while revalidating every skipped input."""
    selected = []
    for task in select_tasks(path, args):
        frozen = freeze_input(task, reviewed_scope_path=args.reviewed_scope,
                              design_plan_path=getattr(args, "design_plan", None),
                              enrich_existing=args.enrich_existing)
        already_reserved = service.has_exact_reservation(frozen)
        if already_reserved and not args.task_id:
            continue
        selected.append(frozen)
        if len(selected) == args.limit:
            break
    return selected


def select_reservations(args, service):
    """Default queue commands advance only their eligible local states."""
    selected = []
    eligible_status = "prepared" if args.start else "generating" if args.poll else None
    for path in sorted(args.work_directory.glob("*/input.json")):
        frozen = json.loads(path.read_text(encoding="utf-8"))
        if not matches(frozen, args):
            continue
        state = service.get(frozen["taskId"])
        if not args.task_id and eligible_status and state["status"] != eligible_status:
            continue
        selected.append(frozen["taskId"])
        if len(selected) == args.limit:
            break
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare", "start", "poll", "status"):
        action.add_argument("--" + name, action="store_true")
    parser.add_argument("--tasks", type=Path, help="Immutable planner tasks.jsonl (prepare only)")
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--task-id", action="append")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--subject", choices=("chinese", "math", "english", "science"))
    parser.add_argument("--grade", choices=tuple("primary_" + str(n) for n in range(1, 7)))
    parser.add_argument("--volume", choices=("upper", "lower", "full"))
    parser.add_argument("--edition", help="Exact editionId from the immutable catalog")
    parser.add_argument("--limit", type=int, default=1, choices=(1, 2))
    parser.add_argument("--reviewed-scope", type=Path, help="Exact mira.textbook.reviewed-lesson-scope.v1 JSON")
    parser.add_argument("--design-plan", type=Path, help="Exact private mira.textbook.activity-design.v1 JSON")
    parser.add_argument("--enrich-existing", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare and not args.tasks:
        parser.error("--prepare requires --tasks")
    if not args.prepare and (args.tasks or args.reviewed_scope or args.design_plan or args.enrich_existing):
        parser.error("tasks/scope/enrichment options apply only to prepare")
    try:
        runtime = None
        if args.start or args.poll:
            from core.config import AppConfig
            from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
            config = AppConfig.from_env()
            runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                               formal_audio_internal_token=config.INTERNAL_API_TOKEN)
        service = TextbookBatchGenerationService(args.work_directory, runtime)
        if args.prepare:
            # Freeze all selected inputs before creating any reservations.
            inputs = select_inputs(args.tasks, args, service)
            results = [service.prepare(frozen) for frozen in inputs]
        else:
            ids = select_reservations(args, service)
            operation = service.start if args.start else service.poll if args.poll else service.get
            results = [operation(task_id) for task_id in ids]
        if not results:
            raise ValueError("No matching eligible or previously prepared task; no generation dispatched")
        for result in results:
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        # Provider/network exception strings can contain request details.
        message = str(exc) if isinstance(exc, ValueError) else "Operator could not complete; inspect saved local state before any retry"
        print(json.dumps({"ok": False, "errorType": type(exc).__name__, "message": message,
                          "publicationAllowed": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
