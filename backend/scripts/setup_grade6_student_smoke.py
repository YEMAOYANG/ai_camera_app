#!/usr/bin/env python3
"""Local fixture via real APIs; browser login always uses the normal /pair UI.

Run only after the sample is published and normal workers are stopped. This file
never constructs the main application, starts workers, generates courses, sends
real SMS, calls a model, or manufactures/injects a student cookie. Setup reserves
normal grade preparation metadata; keep normal generation workers stopped.
prepare-teaching pairs its own local operator device to prepare an exact learning
session before necessary teaching authorization. It never consumes a launch URL.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SafeStop(RuntimeError):
    pass


def local_parent_app():
    from flask import Flask
    from core.config import AppConfig, validate_flask_config
    from routes.api.v1.auth import auth_bp
    from routes.api.v1.setup import setup_bp
    from routes.api.v1.children import children_bp
    from routes.api.v2.parent_student_access import parent_student_access_bp
    from routes.api.v2.student_auth import student_auth_bp
    from routes.api.v2.student_learning import student_learning_bp
    from services.service_factory import sms_provider
    from services.sms_provider import DevelopmentSmsProvider
    app = Flask('mira-isolated-grade6-smoke-parent')
    app.config.update(AppConfig.from_env().to_flask_config())
    db = urlparse(app.config['DATABASE_URL'])
    if (app.config['APP_ENV'] not in {'development', 'test'} or not app.config['DEV_ADAPTERS_ENABLED']
            or app.config['SMS_PROVIDER'] != 'development'
            or db.hostname not in {'localhost', '127.0.0.1', '::1'}
            or not db.path.endswith(('_dev', '_test'))):
        raise SafeStop('development_sms_and_local_development_database_required')
    validate_flask_config(app.config)
    with app.app_context():
        if type(sms_provider()) is not DevelopmentSmsProvider:
            raise SafeStop('real_sms_is_forbidden')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(setup_bp, url_prefix='/api/setup')
    app.register_blueprint(children_bp, url_prefix='/api/children')
    app.register_blueprint(parent_student_access_bp, url_prefix='/api/v2/parent')
    app.register_blueprint(student_auth_bp, url_prefix='/api/v2/student')
    app.register_blueprint(student_learning_bp, url_prefix='/api/v2/student/learning')
    return app


def private_path(raw, *, create):
    path = Path(raw).expanduser().absolute()
    if create:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SafeStop('private_directory_required')
    directory = path.parent.stat()
    if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) & 0o077:
        raise SafeStop('credential_directory_must_be_owned_and_mode_700')
    if create:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise SafeStop('credential_file_must_be_owned_and_mode_600')
    return path


def save(path, value):
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def api(client, method, route, body=None, token=None):
    response = client.open(route, method=method, json=body,
        headers={'Authorization': 'Bearer ' + token} if token else {})
    payload = response.get_json(silent=True)
    if response.status_code != 200 or not isinstance(payload, dict) or payload.get('ok') is not True:
        # Never echo response bodies, request data, phone numbers or credentials.
        raise SafeStop(f'parent_api_failed_http_{response.status_code}')
    return payload


def prepare_teaching(app, client, path, state, parent_token):
    """Create normal learning/binding records, never consume a classroom ticket."""
    from content.single_course_budget import single_slot_identity
    from core.database import Database
    from services.service_factory import openmaic_full_runtime_service
    identity = single_slot_identity('primary_6', 'math', 'fraction_ratio_percentage', 1)
    with Database(app.config['DATABASE_URL']).transaction() as conn:
        candidates = conn.execute("SELECT course.id, course.version, runtime.id AS runtime_id "
            "FROM learning_courses course JOIN learning_openmaic_runtime_classrooms runtime "
            "ON runtime.course_id=course.id AND runtime.course_version=course.version "
            "WHERE course.grade_code='primary_6' AND course.subject='math' "
            "AND course.node_code='fraction_ratio_percentage' AND course.status='published' "
            "AND runtime.candidate_build_item_id=? AND runtime.upstream_job_id=? "
            "AND runtime.status='ready' AND runtime.retired_at IS NULL",
            (identity['buildItemId'], 'omformal_d57c133cbf917beb4cb30bb0')).fetchall()
    if len(candidates) != 1:
        raise SafeStop('exact_published_grade6_sample_required')
    candidate = candidates[0]
    preparation = state.setdefault('teachingPreparation', {})
    student_tokens = preparation.get('studentTokens')
    if student_tokens is None:
        paired = api(client, 'POST', f"/api/v2/parent/children/{state['childId']}/student-access/pairing-codes",
            {'pin': state['pin']}, parent_token)
        student = api(client, 'POST', '/api/v2/student/auth/pair', {
            'pairingCode': paired['pairingCode'], 'clientDevice': {
                'label': '本地课程预检', 'type': 'operator', 'platform': 'local',
                'fingerprint': 'grade6-operator-' + secrets.token_hex(16)}})
        if student['student']['childId'] != state['childId'] or student['student']['gradeCode'] != 'primary_6':
            raise SafeStop('paired_student_identity_changed')
        preparation.update(studentTokens=student['tokens'], studentId=student['student']['id'],
            deviceId=student['device']['id'])
        save(path, state)
        student_tokens = preparation['studentTokens']
    if student_tokens['accessTokenExpiresAt'] < int(time.time()*1000) + 30000:
        refreshed = api(client, 'POST', '/api/v2/student/auth/refresh', {'refreshToken': student_tokens['refreshToken']})
        preparation['studentTokens'] = refreshed['tokens']
        save(path, state)
        student_tokens = preparation['studentTokens']
    student_token = student_tokens['accessToken']
    student = api(client, 'GET', '/api/v2/student/me', token=student_token)['student']
    if student['childId'] != state['childId'] or student['gradeCode'] != 'primary_6':
        raise SafeStop('fixture_student_identity_changed')
    today = api(client, 'GET', '/api/v2/student/learning/today', token=student_token)
    tasks = {item['task']['id']: item for item in today['items'] if item.get('task')
        and (item.get('recommendation') or {}).get('courseId') == candidate['id']
        and (item.get('recommendation') or {}).get('courseVersion') == candidate['version']}
    if len(tasks) != 1:
        raise SafeStop('one_normal_today_task_for_the_sample_required')
    task_id = next(iter(tasks))
    if preparation.get('taskId') not in (None, task_id):
        raise SafeStop('prepared_task_changed_use_the_existing_same_day_session')
    started = api(client, 'POST', '/api/v2/student/learning/sessions', {'taskId': task_id}, student_token)
    session = started['session']
    if (session['courseId'] != candidate['id'] or session['courseVersion'] != candidate['version']
            or session['taskId'] != task_id or session['status'] != 'in_progress'
            or preparation.get('sessionId') not in (None, session['id'])):
        raise SafeStop('sample_learning_session_changed')
    preparation.update(sessionId=session['id'], taskId=task_id, courseId=candidate['id'],
        courseVersion=candidate['version'], runtimeId=candidate['runtime_id'])
    save(path, state)
    launch = api(client, 'POST', f"/api/v2/student/learning/sessions/{session['id']}/openmaic-launch", {}, student_token)
    if launch.get('mode') != 'openmaic_full_runtime' or not launch.get('launchUrl'):
        raise SafeStop('normal_formal_launch_required')
    with app.app_context():
        runtime = openmaic_full_runtime_service()
        with runtime.repository.transaction() as conn:
            row = runtime.repository.get_owned_session_runtime(conn, family_id=state['familyId'],
                child_id=state['childId'], learning_session_id=session['id'])
            if (row is None or row['runtime_classroom_id'] != candidate['runtime_id']
                    or not runtime._formal_session_binding_state(row, family_id=state['familyId'], child_id=state['childId'])[1]):
                raise SafeStop('normal_immutable_formal_session_binding_required')
    # Never store or follow the launch URL. The browser obtains its own ticket
    # after exact teaching authorization; the immutable binding uses family,
    # child and learning-session identity, not this operator's login session.
    preparation.update(launchPreparedAt=int(time.time()*1000), launchExpiresAt=launch['expiresAt'],
        launchConsumed=False)
    state['stage'] = 'teaching_session_prepared'
    save(path, state)
    return {'ok': True, 'gradeCode': 'primary_6', 'sessionId': session['id'], 'taskId': task_id,
        'credentialsFile': str(path), 'launchConsumed': False, 'providerCalls': 0,
        'next': 'Authorize this exact teaching session, reload the API policy, then use pair-code and normal browser pairing.'}


def run(args):
    if not args.confirm_workers_stopped:
        raise SafeStop('confirm_workers_stopped_required')
    if args.command == 'prepare-teaching' and not args.confirm_sample_published:
        raise SafeStop('published_sample_confirmation_required')
    app = local_parent_app()
    from core.database import Database
    if args.command == 'setup':
        if not args.confirm_sample_published or not re.fullmatch(r'1[3-9][0-9]{9}', args.phone):
            raise SafeStop('published_sample_and_valid_fixture_phone_required')
        conn = Database(app.config['DATABASE_URL']).connect()
        try:
            if conn.execute('SELECT id FROM users WHERE phone=?', (args.phone,)).fetchone():
                raise SafeStop('fixture_account_already_exists_choose_an_unused_fixture')
            if not conn.execute("SELECT id FROM learning_courses WHERE grade_code='primary_6' AND subject='math' AND node_code='fraction_ratio_percentage' AND status='published' LIMIT 1").fetchone():
                raise SafeStop('publish_the_grade6_sample_before_onboarding')
        finally:
            conn.rollback()
            conn.close()
        path = private_path(args.credentials, create=True)
        state = {'schemaVersion': 'mira.local-grade6-student-smoke.v1', 'stage': 'preflight_passed',
                 'pin': f'{secrets.randbelow(10000):04d}'}
        save(path, state)
        with app.test_client() as client:
            sms = api(client, 'POST', '/api/auth/sms/request', {'phone': args.phone})
            if sms.get('provider') != 'development' or not sms.get('debugCode'):
                raise SafeStop('development_sms_receipt_required')
            login = api(client, 'POST', '/api/auth/sms/login', {'phone': args.phone, 'code': sms['debugCode']})
            state.update(stage='parent_logged_in', parentTokens=login['tokens'], familyId=login['family']['id'])
            save(path, state)
            token = state['parentTokens']['accessToken']
            if api(client, 'GET', '/api/children/current', token=token)['child'] is not None:
                raise SafeStop('existing_family_child_must_not_be_modified')
            api(client, 'POST', '/api/setup/parent-identity', {'displayName': '爸爸', 'relationship': '爸爸', 'relationshipKey': 'dad'}, token)
            now = datetime.now()
            year = now.year if now.month >= 9 else now.year - 1
            child = api(client, 'POST', '/api/setup/child', {'name': '六年级体验同学', 'nickname': '六年级体验同学',
                'gradeCode': 'primary_6', 'schoolYearStartYear': year}, token)['child']
            if child.get('gradeCode') != 'primary_6':
                raise SafeStop('unexpected_child_grade')
            state.update(stage='child_created', childId=child['id'])
            save(path, state)
    else:
        path = private_path(args.credentials, create=False)
        state = json.loads(path.read_text())
        if state.get('schemaVersion') != 'mira.local-grade6-student-smoke.v1' or not state.get('childId'):
            raise SafeStop('isolated_fixture_credentials_required')
    with app.test_client() as client:
        if state['parentTokens']['accessTokenExpiresAt'] < int(time.time()*1000) + 30000:
            refreshed = api(client, 'POST', '/api/auth/token/refresh', {'refreshToken': state['parentTokens']['refreshToken']})
            state['parentTokens'] = refreshed['tokens']
            save(path, state)
        token = state['parentTokens']['accessToken']
        child = api(client, 'GET', '/api/children/current', token=token)['child']
        if child['id'] != state['childId'] or child.get('gradeCode') != 'primary_6':
            raise SafeStop('isolated_child_identity_changed')
        if args.command == 'prepare-teaching':
            return prepare_teaching(app, client, path, state, token)
        paired = api(client, 'POST', f"/api/v2/parent/children/{state['childId']}/student-access/pairing-codes", {'pin': state['pin']}, token)
        state.update(stage='pairing_code_ready', pairingCode=paired['pairingCode'], pairingExpiresAt=paired['expiresAt'])
        save(path, state)
    return {'ok': True, 'gradeCode': 'primary_6', 'pairingCode': paired['pairingCode'],
            'expiresAt': paired['expiresAt'], 'credentialsFile': str(path),
            'next': 'Enter this short-lived code in a fresh browser session at http://localhost:3000/pair. Do not inject cookies.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup', 'pair-code', 'prepare-teaching'))
    parser.add_argument('--credentials', required=True, help='New/existing mode-600 JSON in an owned mode-700 directory')
    parser.add_argument('--phone', default='13800002026', help='Unused local fixture; existing accounts are rejected')
    parser.add_argument('--confirm-workers-stopped', action='store_true')
    parser.add_argument('--confirm-sample-published', action='store_true')
    args = parser.parse_args()
    try:
        # No backend logs or exception details may expose credentials in terminal output.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = run(args)
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, SafeStop) else type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
