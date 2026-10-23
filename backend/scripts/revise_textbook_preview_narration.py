"""Prepare/run ASR repairs and narrowly reviewed missing quiz feedback audio.

prepare freezes evidence without provider calls. run dispatches only selected
replacement lines. Original WAVs and the original plan remain untouched; the
original receipt list and raw audit are archived before execution. Version 2
can link a quiz question to its independent verbatim speech without changing
its choices, answer, pictures, analysis or points. Version 3 only permits the
registered ZCS Chinese override removal with unchanged text; every unselected
provider body must remain identical and keeps its original request plan.
The separate preview-feedback-addition.v1 schema requires a passing full source
audit and only adds missing selected-option speech, preserving all old audio.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.database import Database
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_narration_revision import revise_preview_narration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run'))
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--failed-audit', '--source-audit', dest='failed_audit', type=Path, required=True)
    parser.add_argument('--retry-recorded-failure', action='store_true',
                        help='Permit one new recorded attempt per selected line after a saved failed/ambiguous receipt; never resend an unknown dispatch.')
    args = parser.parse_args()
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        result = revise_preview_narration(service, args.key, args.classroom_directory,
            json.loads(args.patch.read_text()), args.failed_audit, execute=args.action == 'run',
            retry_recorded_failure=args.retry_recorded_failure,
            progress=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
    except (ApiError, OpenMaicFullRuntimeError) as exc:
        print(json.dumps({'error': exc.code, 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
