"""Prepare or publish one audited saved textbook lesson. No generation calls."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.database import Database
from content.textbook_catalog import digest
from content.textbook_delivery_media import compact_copy
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from repositories.textbook_repository import TextbookRepository
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_publication_service import TextbookPublicationService
from services.textbook_preview_audio import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'publish'])
    parser.add_argument('--key', required=True)
    parser.add_argument('--edition', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--teaching-revision', required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--audio-audit', type=Path, required=True)
    acceptance = parser.add_mutually_exclusive_group()
    acceptance.add_argument('--asr-reconciliation', type=Path,
                        help='Exact human whole-sentence review for low-score formal pinyin ASR; preserves the original audit')
    acceptance.add_argument('--pronunciation-review', type=Path,
                        help='Independent user-authorized operator/automatic evidence; never human listening or a low-score waiver')
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compact-media', action='store_true',
                        help='deliver WebP pictures and MP3 narration encoded from the reviewed files')
    args = parser.parse_args()
    config = AppConfig.from_env()
    target = urlparse(config.DATABASE_URL)
    print(json.dumps({'database': {'host': target.hostname, 'port': target.port or 5432, 'name': target.path.lstrip('/')},
                      'action': args.action}), flush=True)
    service = TextbookPublicationService(TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)),
        OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                  formal_audio_internal_token=config.INTERNAL_API_TOKEN)),
        delivery_copy=compact_copy if args.compact_media else None)
    prepared = service.prepare(key=args.key, edition=args.edition, revision=args.revision, node=args.node,
        teaching_revision=args.teaching_revision, review=json.loads(args.review.read_text()),
        audio_audit=json.loads(args.audio_audit.read_text()), classroom_directory=args.classroom_directory,
        asr_reconciliation=json.loads(args.asr_reconciliation.read_text()) if args.asr_reconciliation else None,
        pronunciation_review=json.loads(args.pronunciation_review.read_text()) if args.pronunciation_review else None)
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output / 'prepared-release.json', prepared)
    summary = {'status': 'prepared', 'contentKey': prepared['frozen']['contentKey'],
        'releaseSha256': prepared['release']['sha256'], 'mediaCount': len(prepared['release']['media']),
        'sourceSha256': prepared['frozen']['sourceSha256']}
    if args.action == 'publish':
        summary = service.publish(prepared)
        atomic_json(args.output / 'publication-receipt.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
