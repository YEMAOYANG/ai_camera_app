"""Freeze/start/query one reviewed Pro workbench draft. No TTS, export or publish.

prepare --draft reviewed.json [--teaching-revision 1] freezes the original bytes
and a v3 page contract (scopeReview, qualityRules, pagePlan, lockedAssessments).
New v3 dispatch requires the matching native runtime capability; historical
v1/v2 jobs keep their original bytes and recovery behavior.
amend --job-directory PATH --draft revised.json --expected-draft-sha256 SHA
      --reviewer NAME --basis REASON revises only request/qualityRules before
any dispatch/owner/session/artifact exists. The same command resumes interrupted
local writes; immutable archives remain. It never creates a Pro client or POST.
start --job-directory PATH may POST once. status is GET-only, including recovery.
attach-materials --job-directory PATH --materials-manifest PATH freezes 1–20
PNG/UTF-8 text assets and uploads each once before start. Manifest schema is
mira.operator.material-attachments.v1, with assets[{assetKey,path,sha256,mimeType}].
mimeType defaults to image/png, requiring width/height; text/plain needs neither.
Optional byteSize must match. Shared text sources do not add planned image assets.
Text can be read by the agent after local plain-text extraction; this CLI never
extracts or invokes a provider. All materialIds bind before the first run starts.
Finish amendments first. Unknown upload outcomes stop; never blindly retry them.
An existing preview/build always requires reuse review, even a legacy release.

supersede-widget explicitly creates a new teaching revision for exactly one
unsupported renderer enum in an already-dispatched, terminal v3 parent. It
requires an exact source draft hash and reviewer/basis. The parent must have
no saved stage, candidate, generated media or non-text material. Its original
bytes and negative asset check are archived; all other duplicate fences remain.
This action prepares only. A later start repeats the parent checks before POST.
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
from integrations.openmaic_workbench_client import WorkbenchError
from repositories.textbook_repository import TextbookRepository
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, WorkbenchCatalogGuard


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'amend', 'attach-materials', 'supersede-widget', 'start', 'status'))
    parser.add_argument('--draft', type=Path)
    parser.add_argument('--job-directory', type=Path)
    parser.add_argument('--materials-manifest', type=Path, help='attach-materials: reviewed PNG/UTF-8 text manifest')
    parser.add_argument('--teaching-revision', help='prepare only; defaults to 1')
    parser.add_argument('--expected-draft-sha256', help='amend: exact original frozen draft byte SHA256')
    parser.add_argument('--reviewer', help='amend: reviewer of the complete revised prompt')
    parser.add_argument('--basis', help='amend: concrete review basis; does not waive locked scope')
    parser.add_argument('--origin', help='Existing local Pro workbench origin, e.g. http://127.0.0.1:3100')
    parser.add_argument('--source-job', type=Path, help='supersede-widget: original terminal authoring job')
    parser.add_argument('--expected-source-draft-sha256', help='supersede-widget: exact original draft byte hash')
    parser.add_argument('--classroom-directory', type=Path, help='supersede-widget: real local native classroom store')
    args = parser.parse_args(argv)
    if args.action == 'prepare' and (not args.draft or args.job_directory):
        parser.error('prepare requires --draft and does not accept --job-directory')
    if args.action in ('start', 'status') and (not args.job_directory or args.draft):
        parser.error('start/status require --job-directory and do not accept --draft')
    if args.action == 'attach-materials' and (not args.job_directory or not args.materials_manifest or args.draft):
        parser.error('attach-materials requires --job-directory and --materials-manifest, without --draft')
    if args.action != 'attach-materials' and args.materials_manifest is not None:
        parser.error('--materials-manifest applies only to attach-materials')
    amendment_args = (args.expected_draft_sha256, args.reviewer, args.basis)
    if args.action == 'amend' and (not args.job_directory or not args.draft or not all(amendment_args)):
        parser.error('amend requires --job-directory, --draft, --expected-draft-sha256, --reviewer and --basis')
    if args.action not in ('amend', 'supersede-widget') and any(value is not None for value in amendment_args):
        parser.error('amendment review arguments apply only to amend')
    successor_args = (args.source_job, args.expected_source_draft_sha256, args.classroom_directory)
    if args.action == 'supersede-widget' and (not all(successor_args) or not args.draft
            or not args.teaching_revision or not args.reviewer or not args.basis
            or args.job_directory or args.expected_draft_sha256):
        parser.error('supersede-widget requires source-job, expected-source-draft-sha256, classroom-directory, '
                     'draft, teaching-revision, reviewer and basis; no job-directory or expected-draft-sha256')
    if args.action != 'supersede-widget' and any(value is not None for value in successor_args):
        parser.error('source-job, expected-source-draft-sha256 and classroom-directory apply only to supersede-widget')
    if args.action not in ('prepare', 'supersede-widget') and args.teaching_revision is not None:
        parser.error('amend/start/status use the frozen teaching revision; do not pass --teaching-revision')
    try:
        config = AppConfig.from_env()
        service = TextbookWorkbenchAuthoring(WorkbenchCatalogGuard(TextbookRepository(Database(config.DATABASE_URL))),
                                            ROOT.parent / 'output/textbook-operator-lessons',
                                            origin=args.origin or config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL)
        if args.action == 'prepare':
            result = service.prepare(args.draft, teaching_revision=args.teaching_revision or '1')
        elif args.action == 'amend':
            result = service.amend(args.job_directory, args.draft, expected_draft_sha256=args.expected_draft_sha256,
                                   reviewer=args.reviewer, basis=args.basis)
        elif args.action == 'attach-materials':
            result = service.attach_materials(args.job_directory, args.materials_manifest)
        elif args.action == 'supersede-widget':
            result = service.supersede_unsupported_widget(args.source_job, args.draft,
                teaching_revision=args.teaching_revision,
                expected_source_draft_sha256=args.expected_source_draft_sha256,
                reviewer=args.reviewer, basis=args.basis, classroom_directory=args.classroom_directory)
        else:
            result = service.run(args.job_directory, start=args.action == 'start')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('error') else 0
    except (WorkbenchError, ApiError) as exc:
        print(json.dumps({'error': exc.code, 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception:
        # DB/transport exception strings may include credentials or raw requests.
        print(json.dumps({'error': 'authoring_check_failed',
                          'message': '本地检查失败；保留冻结文件和派发栅栏。未完成修订只能用同一 amend 命令恢复；其他情况使用 status 核查'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
