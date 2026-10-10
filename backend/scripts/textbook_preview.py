"""Generate exactly one operator preview; repeated starts reuse its reservation.

No implicit migration, import, publication or reset. The prepare command is
provider-free; start sends one request only for a never-dispatched reservation.
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
    parser.add_argument("action", choices=("prepare", "start", "status", "narrate", "freeze"))
    parser.add_argument("--key")
    parser.add_argument("--edition", default="pep-chinese-g1-upper-2022-standard")
    parser.add_argument("--revision", default="20260924-preview-2")
    parser.add_argument("--node", default="u1-l1")
    parser.add_argument("--classroom-directory", type=Path)
    parser.add_argument("--teaching-revision", help="Explicit teaching content version; default reuses the existing version")
    parser.add_argument("--regeneration-reason")
    parser.add_argument("--budget-reference")
    args = parser.parse_args()
    if bool(args.regeneration_reason) != bool(args.budget_reference):
        parser.error("--regeneration-reason and --budget-reference must be supplied together")
    if args.action != "prepare" and any((args.teaching_revision, args.regeneration_reason, args.budget_reference)):
        parser.error("teaching version options apply only to prepare")
    if args.action != "prepare" and not args.key:
        parser.error("start/status require --key")
    if args.action == "narrate" and not args.classroom_directory:
        parser.error("narrate requires --classroom-directory pointing to this local OpenMAIC classroom store")
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
                                    OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        if args.action == "narrate":
            from services.textbook_preview_audio import narrate_preview
            result = narrate_preview(service, args.key, args.classroom_directory,
                                     progress=lambda value: print(json.dumps(value), flush=True))
        elif args.action == "freeze":
            result = service.freeze(args.key)
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
