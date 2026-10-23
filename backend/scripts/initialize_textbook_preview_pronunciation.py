"""Prepare/run the first pinyin profile of a zero-audio preview; never calls TTS."""
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
from services.textbook_preview_pronunciation_initialization import initialize_preview_pronunciation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run'))
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    args = parser.parse_args()
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                 formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        result = initialize_preview_pronunciation(service, args.key, args.classroom_directory,
            json.loads(args.patch.read_text()), execute=args.action == 'run')
    except (ApiError, OpenMaicFullRuntimeError, OSError, ValueError) as exc:
        print(json.dumps({'error': getattr(exc, 'code', 'pronunciation_initialization_io_error'),
                          'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
