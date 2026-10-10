"""Recover an exact local homework job from durable Tencent receipts only.

This operator does not call a provider. The worker may query the recovered
JobIds; the recovery must prove that every current page was already submitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from flask import Flask
from core.config import AppConfig, validate_flask_config
from core.errors import ApiError
from services.homework_tencent_grading import HomeworkTencentGrading
from services.service_factory import homework_service


class SafetyStop(RuntimeError):
    pass


def private_snapshot(snapshot: dict, identity: str) -> Path:
    data = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    folder = ROOT / 'data/homework/tencent-recovery' / identity
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / (hashlib.sha256(data).hexdigest() + '.before.json')
    if not target.exists():
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    return target


def recover(phone: str, identity: str, expected_revision: int, *, execute: bool = False) -> dict:
    if not re.fullmatch(r'1\d{10}', phone) or not re.fullmatch(r'hw_[a-f0-9]{32}', identity):
        raise SafetyStop('invalid_recovery_scope')
    load_dotenv(ROOT / '.env', override=True)
    config = AppConfig.from_env().to_flask_config()
    target = urlsplit(config['DATABASE_URL'])
    if target.hostname not in {'127.0.0.1', 'localhost'} or target.port != 3306 or target.path != '/ai_camera_app_dev':
        raise SafetyStop('recovery_requires_exact_local_development_database')
    app = Flask('tencent-saved-receipt-recovery')
    app.config.update(config)
    validate_flask_config(app.config)
    with app.app_context():
        service = homework_service()
        if getattr(service.provider, 'is_tencent_grading', False) is not True:
            raise SafetyStop('tencent_grading_not_configured')
        with service.repository.transaction() as conn:
            families = conn.execute('SELECT DISTINCT family_id FROM users WHERE phone=?', (phone,)).fetchall()
            if len(families) != 1:
                raise SafetyStop('recovery_owner_not_unique')
            row = service.repository.submission(conn, families[0]['family_id'], identity, lock=True)
            if row['revision'] != expected_revision or row['source'] != 'parent_app':
                raise SafetyStop('recovery_source_or_revision_changed')
            grader = HomeworkTencentGrading(service)
            result = grader.resume_saved_results(conn, row, execute=False)
            if not result.get('resumable'):
                return {'submissionId': identity, 'revision': expected_revision, **result, 'executed': False}
            if execute:
                snapshot = {'schemaVersion': 'mira.tencent-saved-recovery-snapshot.v1', 'submission': dict(row)}
                for table in ('homework_pages', 'homework_items', 'homework_jobs', 'homework_provider_calls', 'homework_actions'):
                    snapshot[table] = [dict(record) for record in conn.execute('SELECT * FROM ' + table + ' WHERE submission_id=?', (identity,)).fetchall()]
                private_snapshot(snapshot, identity)
                result = grader.resume_saved_results(conn, row, execute=True)
            return {'submissionId': identity, 'revision': expected_revision, **result, 'executed': execute}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True)
    parser.add_argument('--submission-id', required=True)
    parser.add_argument('--expected-revision', required=True, type=int)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        result = recover(args.phone, args.submission_id, args.expected_revision, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get('resumable') else 2
    except (SafetyStop, ApiError) as error:
        print(json.dumps({'ok': False, 'error': error.code if isinstance(error, ApiError) else str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
