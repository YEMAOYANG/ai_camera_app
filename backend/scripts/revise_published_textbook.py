"""Prepare an immutable local correction, then register a separate preview.

Neither command generates content, dispatches TTS/ASR, reviews or publishes.
The original published build, preview, plan, receipts and audit remain intact.
For HTML-only layout corrections use a v1 operator patch with changes: [] plus
a nonempty --visual-patch. All original audio and ASR evidence is inherited;
the new preview still requires complete visual review, audio audit and release.

The v4 complete-scene patch uses nativeSessionId, nativeStageId,
nativeRevisionId and expectedCandidateSha256 in place of changes. Prepare
verifies the applied native receipt and literal artifacts, seals evidenceSha256,
and lists unchanged, modified, added and deleted speech separately. It never
creates a missing native receipt or rewrites an old authoring snapshot.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.errors import ApiError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Read parent evidence and write only a local candidate')
    parent_source = prepare.add_mutually_exclusive_group(required=True)
    parent_source.add_argument('--parent-content-key')
    parent_source.add_argument('--parent-preview-key', help='Explicit audited unpublished preview; requires the dedicated v4 schema')
    prepare.add_argument('--patch', type=Path, required=True)
    prepare.add_argument('--visual-patch', type=Path,
                         help='Validated HTML patch; required and nonempty when operator changes is []')
    prepare.add_argument('--source-audit', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    register = commands.add_parser('register', help='Reserve a new teaching version and save its separate preview')
    register.add_argument('--candidate', type=Path, required=True)
    register.add_argument('--budget-reference', required=True)
    for command in (prepare, register):
        command.add_argument('--classroom-directory', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args)
    except ApiError as exc:
        print(json.dumps({'ok': False, 'error': exc.code, 'message': exc.message}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:
        # Driver/HTTP errors may contain credentials or private response data.
        # An interrupted register may already have saved its target; never
        # suggest deleting its marker or creating a replacement request.
        print(json.dumps({'ok': False, 'error': 'textbook_operator_revision_unconfirmed',
            'exceptionType': type(exc).__name__,
            'message': '操作未确认完成。保留候选、归档和保存标记，先核对原任务状态；不要删除标记或另建候选重发登记。'},
            ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def execute(args):
    from core.config import AppConfig
    from core.database import Database
    from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
    from repositories.textbook_repository import TextbookRepository
    from services.textbook_preview_service import TextbookPreviewService
    from services.textbook_operator_revision_service import prepare_revision, register_revision
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    if args.command == 'prepare':
        result = prepare_revision(service, args.parent_content_key, args.classroom_directory,
            json.loads(args.patch.read_text()), args.source_audit, args.output,
            visual_patch=json.loads(args.visual_patch.read_text()) if args.visual_patch else None,
            parent_preview_key=args.parent_preview_key)
        result.pop('files', None)
    else:
        result = register_revision(service, args.candidate, args.classroom_directory, budget_reference=args.budget_reference)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
