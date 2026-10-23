"""Restore exact approved parent quiz audio with a separate immutable amendment."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    args = parser.parse_args()
    from core.config import AppConfig
    from core.database import Database
    from core.errors import ApiError
    from repositories.textbook_repository import TextbookRepository
    from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
    from services.textbook_preview_service import TextbookPreviewService
    from services.textbook_parent_audio_restoration import restore_parent_audio
    config = AppConfig.from_env()
    service = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN))
    try:
        result = restore_parent_audio(service, args.key, args.classroom_directory, json.loads(args.patch.read_text()))
    except ApiError as exc:
        print(json.dumps({'error': exc.code, 'message': exc.message}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
