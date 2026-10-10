#!/usr/bin/env python3
"""Explicit local development fixtures through normal auth and learning services.

Never starts the app, a worker, camera or Provider. Identity credentials are
private; output contains only test-account metadata and short-lived pair codes.
Existing phone numbers without this script's private ownership manifest are
refused. Rerunning seed preserves the learner's subsequent progress.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from setup_grade6_student_smoke import SafeStop, api, local_parent_app, private_path, save

SCHEMA = 'mira.local-learning-demo.v1'
SAMPLES = {
    'pictures': {'phone': '19900009030', 'grade': 'primary_1', 'name': '图片考试测试同学'},
    'math': {'phone': '19900009031', 'grade': 'primary_6', 'name': '试卷订正测试同学'},
}
STATE_ROOT = ROOT.parent / '.local_backups' / 'student-learning-demo-v1'


def local_app():
    app = local_parent_app()
    url = urlparse(app.config['DATABASE_URL'])
    if url.scheme.split('+', 1)[0] != 'mysql' or url.hostname not in {'127.0.0.1', 'localhost', '::1'} or url.path != '/ai_camera_app_dev':
        raise SafeStop('only_local_ai_camera_app_dev_is_allowed')
    if not app.config.get('LEARNING_TEXTBOOK_LIBRARY_ONLY', True):
        raise SafeStop('textbook_library_only_required_no_generation_queue')
    if not app.config.get('LEARNING_REVIEW_ENABLED') or not app.config.get('HOMEWORK_ANALYSIS_ENABLED'):
        raise SafeStop('local_learning_review_and_homework_entries_required')
    # These flags govern this isolated script only. Nothing changes the live API.
    app.config.update(HOMEWORK_WORKER_ENABLED=False, HOMEWORK_AUDIO_ENABLED=False)
    from routes.api.v1.homework import homework_bp
    from routes.api.v1.learning_reviews import parent_learning_reviews_bp, parent_learning_weaknesses_bp
    from routes.api.v1.reports import reports_bp
    from routes.api.v2.student_reviews import student_reviews_bp
    from routes.api.v2.student_homework import student_homework_bp
    app.register_blueprint(homework_bp, url_prefix='/api')
    app.register_blueprint(parent_learning_reviews_bp, url_prefix='/api/learning/reviews')
    app.register_blueprint(parent_learning_weaknesses_bp, url_prefix='/api/reports/learning')
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(student_reviews_bp, url_prefix='/api/v2/student/learning/reviews')
    app.register_blueprint(student_homework_bp, url_prefix='/api/v2/student/learning')
    return app


def state_path(sample, *, create=False):
    return private_path(str(STATE_ROOT / (sample + '.json')), create=create)


def load_owned(database, sample):
    path = state_path(sample)
    state = json.loads(path.read_text())
    spec = SAMPLES[sample]
    if state.get('schemaVersion') != SCHEMA or state.get('sample') != sample or state.get('phone') != spec['phone']:
        raise SafeStop('owned_demo_manifest_required')
    with database.transaction() as conn:
        user = conn.execute('SELECT id,family_id FROM users WHERE phone=?', (spec['phone'],)).fetchone()
        if not user or user['family_id'] != state['familyId']:
            raise SafeStop('test_account_identity_changed')
        child = conn.execute('SELECT * FROM children WHERE family_id=? ORDER BY created_at LIMIT 1', (state['familyId'],)).fetchone()
        if state.get('childId') and child is None:
            raise SafeStop('test_child_was_removed_not_recreated')
        if child and (child['name'] != spec['name'] or child['grade_code'] != spec['grade'] or (state.get('childId') and child['id'] != state['childId'])):
            raise SafeStop('test_child_identity_changed')
    return path, state


def create_account(app, database, sample):
    spec = SAMPLES[sample]
    path = STATE_ROOT / (sample + '.json')
    if path.exists():
        return load_owned(database, sample)
    with database.transaction() as conn:
        if conn.execute('SELECT id FROM users WHERE phone=?', (spec['phone'],)).fetchone():
            raise SafeStop('existing_account_without_demo_manifest_refused')
    path = state_path(sample, create=True)
    state = {'schemaVersion': SCHEMA, 'sample': sample, 'phone': spec['phone'], 'pin': '2026', 'stage': 'reserved'}
    save(path, state)
    with app.test_client() as client:
        sms = api(client, 'POST', '/api/auth/sms/request', {'phone': spec['phone']})
        if sms.get('provider') != 'development' or not sms.get('debugCode'):
            raise SafeStop('development_sms_receipt_required')
        login = api(client, 'POST', '/api/auth/sms/login', {'phone': spec['phone'], 'code': sms['debugCode']})
        state.update(parentTokens=login['tokens'], familyId=login['family']['id'], stage='parent_created')
        save(path, state)
    return path, state


def parent_token(app, path, state):
    if state['parentTokens']['accessTokenExpiresAt'] < int(time.time() * 1000) + 30000:
        with app.test_client() as client:
            response = api(client, 'POST', '/api/auth/token/refresh', {'refreshToken': state['parentTokens']['refreshToken']})
        state['parentTokens'] = response['tokens']
        save(path, state)
    return state['parentTokens']['accessToken']


def ensure_child(app, path, state):
    token = parent_token(app, path, state)
    spec = SAMPLES[state['sample']]
    with app.test_client() as client:
        child = api(client, 'GET', '/api/children/current', token=token)['child']
        if child is None:
            api(client, 'POST', '/api/setup/parent-identity', {'displayName': '爸爸', 'relationship': '爸爸', 'relationshipKey': 'dad'}, token)
            now = datetime.now(ZoneInfo('Asia/Shanghai'))
            year = now.year if now.month >= 9 else now.year - 1
            child = api(client, 'POST', '/api/setup/child', {'name': spec['name'], 'nickname': spec['name'],
                'gradeCode': spec['grade'], 'schoolYearStartYear': year}, token)['child']
        if child['name'] != spec['name'] or child['gradeCode'] != spec['grade']:
            raise SafeStop('test_child_identity_changed')
    state.update(childId=child['id'], stage='child_created')
    save(path, state)


def seed(app, database, sample):
    path, state = create_account(app, database, sample)
    ensure_child(app, path, state)
    token = parent_token(app, path, state)
    now = int(time.time() * 1000)
    with app.app_context(), database.transaction() as conn:
        child = dict(conn.execute('SELECT * FROM children WHERE id=? AND family_id=? FOR UPDATE',
            (state['childId'], state['familyId'])).fetchone())
        from services.learning_evidence_service import digest
        namespace = 'learning_demo_v1_' + sample + '_' + digest([child['family_id'], child['id']])[:16]
        if sample == 'pictures':
            from dev_review_sample import create_review_samples
            course = conn.execute("SELECT c.* FROM learning_courses c JOIN learning_textbook_course_builds b ON b.course_id=c.id AND b.course_version=c.version WHERE c.grade_code='primary_1' AND c.subject='chinese' AND c.status='published' AND b.status='published' ORDER BY b.created_at DESC LIMIT 1").fetchone()
            if course is None:
                raise SafeStop('published_picture_course_required')
            result = create_review_samples(conn, child=child, course=dict(course), now=now, seed_namespace=namespace)
        else:
            from dev_homework_sample import seed_homework_samples
            from services.service_factory import homework_service
            result = seed_homework_samples(conn, child=child, service=homework_service(), now=now, seed_namespace=namespace)
    state.update(stage='seeded', samples=result, seededAt=now)
    save(path, state)
    return {'sample': sample, 'name': SAMPLES[sample]['name'], 'parentPhone': SAMPLES[sample]['phone'], **result}


def public_status(app, database, sample):
    path, state = load_owned(database, sample)
    token = parent_token(app, path, state)
    with app.app_context():
        from services.service_factory import learning_review_service, homework_service
        reviews = learning_review_service().parent_list(token, state['childId'])['reviews']
        homework = homework_service().list_parent(token, state['childId'])['submissions']
    samples = state.get('samples') or {}
    entries = samples.get('reviews', samples.get('submissions', []))
    links = [{k: e[k] for k in ('id', 'scenario', 'path') if k in e} for e in entries]
    return {'sample': sample, 'name': SAMPLES[sample]['name'], 'parentPhone': SAMPLES[sample]['phone'],
        'reviews': [{k: r[k] for k in ('id', 'status', 'totalQuestions', 'currentIndex', 'correctCount')} for r in reviews],
        'homework': [{k: h[k] for k in ('id', 'title', 'status', 'summary', 'readyForStudent')} for h in homework],
        'links': links, 'source': samples.get('source'), 'providerCalls': 0}


def pair_code(app, database, sample):
    path, state = load_owned(database, sample)
    token = parent_token(app, path, state)
    with app.test_client() as client:
        response = api(client, 'POST', f"/api/v2/parent/children/{state['childId']}/student-access/pairing-codes", {'pin': state['pin']}, token)
    return {'sample': sample, 'name': SAMPLES[sample]['name'], 'pairingCode': response['pairingCode'],
        'expiresAt': response['expiresAt'], 'studentTestPin': state['pin'],
        'url': ('http://localhost:3000/pair' if sample == 'pictures' else 'http://127.0.0.1:3000/pair')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seed', 'status', 'pair-code'))
    parser.add_argument('--sample', choices=('all', *SAMPLES), default='all')
    args = parser.parse_args()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            app = local_app()
            from core.database import Database
            database = Database(app.config['DATABASE_URL'])
            operation = {'seed': seed, 'status': public_status, 'pair-code': pair_code}[args.command]
            results = [operation(app, database, sample) for sample in (SAMPLES if args.sample == 'all' else (args.sample,))]
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, SafeStop) else type(error).__name__}))
        return 1
    print(json.dumps({'ok': True, 'command': args.command, 'results': results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
