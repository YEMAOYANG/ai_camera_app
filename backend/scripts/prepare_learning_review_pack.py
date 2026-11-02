#!/usr/bin/env python3
"""Prepare/generate/review/archive bounded original review packs; no student data writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.learning_review_content import ReviewContentError
from services.learning_review_content import PACK_ROOT, ReviewPackProducer, archive_pack, read_json, source_from_assignment_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    register = subs.add_parser('prepare')
    register.add_argument('--source', required=True, type=Path)
    register.add_argument('--request-id', required=True)
    register.add_argument('--question-count', type=int, default=5)
    derive = subs.add_parser('prepare-from-record')
    derive.add_argument('--record', type=Path, required=True)
    derive.add_argument('--identity', type=Path, required=True, help='Exact published course/contentKey/releaseSha256 identity')
    derive.add_argument('--media', type=Path, required=True, help='Reviewed picture descriptor list with actual paths and SHA256')
    derive.add_argument('--reviewer', required=True)
    derive.add_argument('--target-texts', type=Path, help='Optional reviewed targetId-to-exact-target-text list mapping')
    derive.add_argument('--request-id', required=True)
    derive.add_argument('--question-count', type=int, default=5)
    generate = subs.add_parser('generate')
    generate.add_argument('--request-id', required=True)
    generate.add_argument('--execute', action='store_true', help='Authorize this prepared job\'s at most two AI calls')
    narrate = subs.add_parser('narrate')
    narrate.add_argument('--request-id', required=True)
    narrate.add_argument('--execute', action='store_true', help='Pre-record exact Qwen clips under the frozen bounded plan')
    approve = subs.add_parser('approve')
    approve.add_argument('--request-id', required=True)
    approve.add_argument('--media', required=True, type=Path, help='Real Qwen audio descriptors with exact text and receipt hashes')
    approve.add_argument('--review', required=True, type=Path, help='Identified AI/maintainer/user review bound to the exact draft SHA and actual evidence')
    archive = subs.add_parser('archive')
    archive.add_argument('--pack-sha256', required=True)
    archive.add_argument('--execute', action='store_true', help='Upload/verify and register this approved pack')
    worker = subs.add_parser('worker')
    worker.add_argument('--limit', type=int, default=5)
    worker.add_argument('--execute', action='store_true')
    status = subs.add_parser('status')
    status.add_argument('--request-id', required=True)
    args = parser.parse_args(argv)
    producer = ReviewPackProducer()
    if args.command in {'generate', 'narrate', 'archive', 'worker'} and not args.execute:
        return {'status': 'dry_run', 'command': args.command, 'providerCalls': 0, 'uploads': 0}
    if args.command == 'generate':
        draft = producer.generate(args.request_id)
        from content.learning_review_content import digest
        return {'status': draft['status'], 'draftSha256': digest(draft), 'questionCount': len(draft['questions'])}
    if args.command == 'narrate':
        return producer.narrate(args.request_id)
    if args.command == 'worker':
        if not 1 <= args.limit <= 100:
            raise ReviewContentError('review_worker_limit_invalid')
        results = []
        for path in sorted((PACK_ROOT / 'jobs').glob('*/input.json')):
            if len(results) >= args.limit:
                break
            if (path.parent / 'draft.json').exists():
                continue
            try:
                draft = producer.generate(path.parent.name)
                results.append({'requestId': path.parent.name, 'status': draft['status']})
            except (ReviewContentError, BlockingIOError) as error:
                results.append({'requestId': path.parent.name, 'error': str(error) if isinstance(error, ReviewContentError) else 'review_job_busy'})
        return {'jobs': results}
    if args.command == 'status':
        from content.learning_review_content import ID, require
        require(ID.fullmatch(args.request_id), 'review_request_invalid')
        job = PACK_ROOT / 'jobs' / args.request_id
        return {'requestId': args.request_id, 'prepared': (job / 'input.json').exists(),
            'generated': (job / 'draft.json').exists(),
            'dispatchFenced': any((job / (phase + '-intent.json')).exists()
                and not (job / (phase + '-result.json')).exists() for phase in ('generation', 'verification'))}
    from core.config import AppConfig
    from core.database import Database
    database = Database(AppConfig.from_env().DATABASE_URL)
    if args.command == 'archive':
        from repositories.course_storage_repository import CourseStorageRepository
        return archive_pack(args.pack_sha256, repository=CourseStorageRepository(database))
    from scripts.course_storage_releases import read_only_connection
    with read_only_connection(database) as conn:
        if args.command == 'prepare-from-record':
            source = source_from_assignment_record(args.record, source_identity=read_json(args.identity),
                media=read_json(args.media), reviewer=args.reviewer,
                target_texts=read_json(args.target_texts) if args.target_texts else None)
            return producer.prepare(source, request_id=args.request_id, question_count=args.question_count, conn=conn)
        if args.command == 'prepare':
            return producer.prepare(read_json(args.source), request_id=args.request_id,
                question_count=args.question_count, conn=conn)
        if args.command == 'approve':
            return producer.approve(args.request_id, media=read_json(args.media), review=read_json(args.review), conn=conn)


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False))
    except ReviewContentError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
