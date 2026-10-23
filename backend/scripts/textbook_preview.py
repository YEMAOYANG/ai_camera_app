"""Generate exactly one operator preview; repeated starts reuse its reservation.

No implicit migration, import, publication or reset. The prepare command is
provider-free; start sends one request only for a never-dispatched reservation.
adopt reserves the lesson for a classroom an operator already authored and saved
in this local OpenMAIC; it sends no request and still needs narrate and review.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from core.database import Database
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from services.textbook_preview_service import TextbookPreviewService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "adopt", "start", "status", "narrate", "freeze"))
    parser.add_argument("--key")
    parser.add_argument("--edition", default="pep-chinese-g1-upper-2022-standard")
    parser.add_argument("--revision", default="20260924-preview-2")
    parser.add_argument("--node", default="u1-l1")
    parser.add_argument("--classroom-directory", type=Path)
    parser.add_argument("--speech-selection", type=Path,
                        help="narrate only: JSON with schemaVersion=mira.textbook.speech-selection.v1, previewKey, coreSha256 and speeches [{sceneId, actionId}]; keeps the preview partial")
    parser.add_argument("--retry-recorded-failure", action="store_true",
                        help="narrate only: retry exactly one selected speech after its saved failed/ambiguous attempts")
    parser.add_argument("--attempt", type=int,
                        help="narrate retry only: the exact next deterministic attempt; dispatches once and stops")
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--expected-core-sha256")
    parser.add_argument("--expected-classroom-sha256")
    parser.add_argument("--expected-receipts-sha256")
    parser.add_argument("--classroom-id", help="adopt: the saved classroom to reserve this lesson for")
    parser.add_argument("--authoring", type=Path, help="adopt: JSON record of the Agent session that authored it")
    parser.add_argument("--teaching-revision", help="Explicit teaching content version; default reuses the existing version")
    parser.add_argument("--regeneration-reason")
    parser.add_argument("--budget-reference")
    args = parser.parse_args()
    if bool(args.regeneration_reason) != bool(args.budget_reference):
        parser.error("--regeneration-reason and --budget-reference must be supplied together")
    if args.action not in ("prepare", "adopt") and any((args.teaching_revision, args.regeneration_reason, args.budget_reference)):
        parser.error("teaching version options apply only to prepare and adopt")
    if args.action not in ("prepare", "adopt") and not args.key:
        parser.error("start/status require --key")
    if args.action == "adopt" and not all((args.classroom_id, args.authoring, args.classroom_directory)):
        parser.error("adopt requires --classroom-id, --authoring and --classroom-directory")
    if args.action == "narrate" and not args.classroom_directory:
        parser.error("narrate requires --classroom-directory pointing to this local OpenMAIC classroom store")
    if args.speech_selection and args.action != "narrate":
        parser.error("--speech-selection applies only to narrate")
    retry_values = (args.retry_recorded_failure, args.attempt, args.expected_plan_sha256,
                    args.expected_core_sha256, args.expected_classroom_sha256, args.expected_receipts_sha256)
    if any(value is not None and value is not False for value in retry_values):
        if args.action != "narrate":
            parser.error("recorded-failure retry options apply only to narrate")
        if (not args.retry_recorded_failure or args.speech_selection is None or args.attempt is None
                or not all((args.expected_plan_sha256, args.expected_core_sha256,
                            args.expected_classroom_sha256, args.expected_receipts_sha256))):
            parser.error("recorded-failure retry requires one speech selection, an attempt and all four SHA-256 fences")
    selection = None
    if args.speech_selection:
        try:
            selection = json.loads(args.speech_selection.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            parser.error(f"cannot read --speech-selection JSON: {exc}")
        if not isinstance(selection, dict):
            parser.error("--speech-selection must contain a JSON object")
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
                                    OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        if args.action == "narrate":
            from services.textbook_preview_audio import narrate_preview
            retry_fences = ({"planSha256": args.expected_plan_sha256,
                             "coreSha256": args.expected_core_sha256,
                             "classroomSha256": args.expected_classroom_sha256,
                             "receiptsSha256": args.expected_receipts_sha256}
                            if args.retry_recorded_failure else None)
            result = narrate_preview(service, args.key, args.classroom_directory,
                                     speech_selection=selection,
                                     retry_recorded_failure=args.retry_recorded_failure,
                                     retry_attempt=args.attempt,
                                     retry_fences=retry_fences,
                                     progress=lambda value: print(json.dumps(value), flush=True))
        elif args.action == "freeze":
            result = service.freeze(args.key)
        elif args.action == "adopt":
            result = service.adopt(args.edition, args.revision, args.node, args.classroom_id, args.classroom_directory,
                                   json.loads(args.authoring.read_text(encoding="utf-8")),
                                   teaching_revision=args.teaching_revision,
                                   regeneration={"reason": args.regeneration_reason, "budgetReference": args.budget_reference}
                                   if args.regeneration_reason else None)
        else:
            result = service.prepare(args.edition, args.revision, args.node,
                                     teaching_revision=args.teaching_revision,
                                     regeneration={"reason": args.regeneration_reason, "budgetReference": args.budget_reference}
                                     if args.regeneration_reason else None) if args.action == "prepare" else (
                service.start(args.key) if args.action == "start" else service.poll(args.key))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ApiError, OpenMaicFullRuntimeError) as exc:
        print(json.dumps({"error": exc.code, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
