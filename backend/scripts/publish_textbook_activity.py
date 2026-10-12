"""Prepare/publish explicitly reviewed activities, retaining per-course receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import AppConfig
from core.database import Database
from repositories.textbook_repository import TextbookRepository
from services.textbook_activity_publication_service import TextbookActivityPublicationService
from content.textbook_catalog import canonical
from scripts.narrate_textbook_batch import DEFAULT_CLASSROOM_DIRECTORY


def immutable_json(path, value):
    raw = canonical(value).encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('publication_evidence_already_exists_with_different_bytes')
    else:
        with path.open('xb') as stream:
            stream.write(raw)
    if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(raw).digest():
        raise ValueError('publication_evidence_readback_failed')


def process(args, repo, service):
    prepared = service.prepare(args.candidate_directory, args.audio_directory, json.loads(args.review.read_text()), args.teaching_revision)
    args.output.mkdir(parents=True, exist_ok=True)
    immutable_json(args.output / 'prepared-release.json', prepared)
    summary = {'status': 'prepared', 'contentKey': prepared['frozen']['contentKey'],
               'releaseSha256': prepared['release']['sha256'], 'mediaCount': len(prepared['release']['media'])}
    if args.action == 'publish':
        backup = args.output / 'database-before-publication.json'
        if not backup.exists():
            with repo.transaction() as conn:
                course = prepared['course']
                before = {'build': repo.get_build(conn, prepared['frozen']['contentKey']),
                          'course': conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                                                 (course['id'], course['version'])).fetchone(),
                          'editionId': prepared['manifest']['editionId'], 'revisionId': prepared['manifest']['revisionId']}
            immutable_json(backup, before)
        summary = service.publish(prepared)
        # Repeating an acknowledged publication returns created=False, but its
        # immutable receipt and original pre-write snapshot must remain intact.
        receipt = args.output / 'publication-receipt.json'
        if not receipt.exists():
            immutable_json(receipt, summary)
        elif {k: v for k, v in json.loads(receipt.read_text()).items() if k != 'created'} != {k: v for k, v in summary.items() if k != 'created'}:
            raise ValueError('publication_receipt_changed')
    return summary


def batch_entries(path, action):
    index = json.loads(path.read_text())
    if index.get('schemaVersion') != 'mira.textbook.activity-publication-batch.v1' or not index.get('entries'):
        raise ValueError('explicit_publication_batch_required')
    entries, tasks, outputs = [], set(), set()
    for row in index['entries']:
        candidate = Path(row['candidateDirectory']).resolve()
        original = json.loads((candidate / 'input.json').read_text())
        task = original['taskId']
        output = Path(row['outputDirectory']).resolve()
        if (task != row.get('taskId') or original['inputSha256'] != row.get('inputSha256')
                or task in tasks or output in outputs or output == candidate
                or output.is_relative_to(candidate) or candidate.is_relative_to(output)):
            raise ValueError('batch_duplicate_or_changed_course_identity')
        tasks.add(task); outputs.add(output)
        entries.append(SimpleNamespace(action=action, candidate_directory=candidate,
            audio_directory=Path(row['audioDirectory']), review=Path(row['reviewPath']),
            teaching_revision=row['teachingRevision'], output=output))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'publish'])
    parser.add_argument('--batch-index', type=Path)
    parser.add_argument('--candidate-directory', type=Path)
    parser.add_argument('--audio-directory', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--teaching-revision')
    parser.add_argument('--classroom-directory', type=Path, default=DEFAULT_CLASSROOM_DIRECTORY)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    single = (args.candidate_directory, args.audio_directory, args.review, args.teaching_revision, args.output)
    if args.batch_index:
        if any(single):
            parser.error('--batch-index cannot combine with single-course arguments')
        entries = batch_entries(args.batch_index, args.action)
    else:
        if not all(single):
            parser.error('provide --batch-index or all single-course arguments')
        entries = [args]
    config = AppConfig.from_env()
    target = urlparse(config.DATABASE_URL)
    print(json.dumps({'database': {'host': target.hostname, 'port': target.port or 3306, 'name': target.path.lstrip('/')},
                      'action': args.action, 'courseCount': len(entries)}), flush=True)
    repo = TextbookRepository(Database(config.DATABASE_URL))
    service = TextbookActivityPublicationService(repo, config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, args.classroom_directory)
    failures = 0
    for entry in entries:
        try:
            result = process(entry, repo, service)
        except Exception as exc:
            if not args.batch_index:
                raise
            failures += 1
            # Keep the batch moving without resending model calls or mutating a
            # failed course. Its exact prepared release and backup remain saved.
            result = {'ok': False, 'candidateDirectory': str(entry.candidate_directory),
                      'errorType': type(exc).__name__, 'message': str(exc) if isinstance(exc, ValueError) else 'Inspect this course before resuming'}
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
