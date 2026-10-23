#!/usr/bin/env python3
"""Read a real existing student's classroom through an isolated runtime gateway.

No launch(), login, task creation, event submission or paid provider dispatch.
Only the gateway's normal internal-guard audit appends are allowed. Credentials,
tickets, cookies and pupil identities stay in memory and are never printed.
"""
from __future__ import annotations

import argparse
import hashlib
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.textbook_catalog import digest
from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from core.security import now_ms
from models.care import AUDIT_DOMAIN_INTERNAL_API
from repositories.course_storage_repository import CourseStorageRepository
from repositories.textbook_repository import TextbookRepository
from scripts.course_storage_releases import _validated_release
from scripts.verify_course_storage_runtime import ReadOnlyDatabase
from services.course_file_store import CourseFileStore
from services.textbook_classroom_service import TextbookClassroomService

MAX_CLASSROOM_BYTES = 64 * 1024 * 1024
MAX_AUDIO_BYTES = 16 * 1024 * 1024
SHA = re.compile(r'[a-f0-9]{64}\Z')
IDENTIFIER = re.compile(r'[A-Za-z0-9_]+\Z')


class StudentVerificationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise StudentVerificationError(code)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def _quoted(name):
    require(isinstance(name, str) and IDENTIFIER.fullmatch(name), 'student_verification_database_identifier_invalid')
    return '`' + name + '`'


def database_snapshot(database, *, guard_cutoff=None):
    """Hash every base-table row on MySQL; no private row body leaves MySQL.

    Per-column SHA avoids concatenating large frozen JSON documents. Sorting
    fixed-size row hashes, rather than source rows, avoids MySQL JSON filesort.
    Existing internal audit rows remain protected; new guard appends are counted.
    """
    result = {}
    with database.transaction() as conn:
        columns = conn.execute('SELECT c.TABLE_NAME AS table_name,c.COLUMN_NAME AS column_name,'
            'c.COLUMN_TYPE AS column_type,c.IS_NULLABLE AS is_nullable FROM INFORMATION_SCHEMA.COLUMNS c '
            'JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME '
            "WHERE c.TABLE_SCHEMA=DATABASE() AND t.TABLE_TYPE='BASE TABLE' ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION").fetchall()
        groups = {}
        for row in columns:
            groups.setdefault(row['table_name'], []).append(row)
        guard = conn.execute('SELECT COUNT(*) AS row_count,COALESCE(MAX(created_at),0) AS cutoff '
            'FROM audit_events WHERE audit_domain=?', (AUDIT_DOMAIN_INTERNAL_API,)).fetchone()
        cutoff = guard['cutoff'] if guard_cutoff is None else guard_cutoff

        def rows_hash(table, fields, where='', params=()):
            pieces = []
            for field in fields:
                name = _quoted(field['column_name'])
                pieces.append("IF(" + name + " IS NULL,'N',CONCAT('V',LENGTH(CAST(" + name
                    + " AS BINARY)),':',SHA2(CAST(" + name + " AS BINARY),256)))")
            expression = "SHA2(CONCAT(" + ','.join(pieces) + "),256)"
            rows = conn.execute('SELECT ' + expression + ' AS row_sha256 FROM ' + _quoted(table) + where, params).fetchall()
            require(len(rows) <= 1_000_000 and all(SHA.fullmatch(r['row_sha256'] or '') for r in rows),
                    'student_verification_database_snapshot_invalid')
            hashes = sorted(r['row_sha256'] for r in rows)
            return {'rows': len(hashes), 'sha256': hashlib.sha256(('\n'.join(hashes)).encode()).hexdigest(),
                    'schemaSha256': hashlib.sha256(json_bytes(fields)).hexdigest()}

        for table, fields in groups.items():
            where, params = (' WHERE audit_domain IS NULL OR audit_domain<>?', (AUDIT_DOMAIN_INTERNAL_API,)) if table == 'audit_events' else ('', ())
            result[table] = rows_hash(table, fields, where, params)
        protected_guard = rows_hash('audit_events', groups['audit_events'],
            ' WHERE audit_domain=? AND created_at<=?', (AUDIT_DOMAIN_INTERNAL_API, cutoff))
    return {'business': result, 'guard': {'rows': guard['row_count'], 'cutoff': cutoff,
                                        'existing': protected_guard}}


def select_existing_identity(database, *, content_key=None):
    require(content_key is None or SHA.fullmatch(content_key), 'student_verification_content_key_invalid')
    timestamp = now_ms()
    with database.transaction() as conn:
        rows = conn.execute("""SELECT s.id AS student_session_id,l.id AS learning_session_id,
            b.content_key,c.grade_selection_revision,c.grade_code
            FROM student_sessions s JOIN student_principals p ON p.id=s.principal_id
            JOIN student_trusted_devices d ON d.id=s.device_id AND d.principal_id=p.id
                AND d.family_id=p.family_id AND d.child_id=p.child_id
            JOIN children c ON c.id=p.child_id AND c.family_id=p.family_id
            JOIN learning_sessions l ON l.child_id=c.id AND l.family_id=c.family_id
            JOIN learning_textbook_course_builds b ON b.course_id=l.course_id AND b.course_version=l.course_version
            JOIN learning_courses course ON course.id=b.course_id AND course.version=b.course_version
            JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id
            WHERE s.revoked_at IS NULL AND s.refresh_expires_at>?
                AND p.status='active' AND d.status='trusted' AND d.revoked_at IS NULL AND d.expires_at>?
                AND c.grade_selection_revision>=1 AND course.grade_code=c.grade_code
                AND b.status='published' AND course.status='published' AND course.quality_status='released'
                AND course.retired_at IS NULL AND r.retired_at IS NULL
                AND (? IS NULL OR b.content_key=?)
            ORDER BY s.last_active_at DESC,l.updated_at DESC LIMIT 1""",
            (timestamp + 60_000, timestamp + 60_000, content_key, content_key)).fetchall()
    require(bool(rows), 'student_verification_no_valid_existing_identity')
    return dict(rows[0])


class GatewayReader:
    """A GET-only, loopback-pinned client with an ephemeral cookie jar."""
    def __init__(self, origin):
        try:
            parsed = urlsplit(origin)
            valid = (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
                and parsed.port is not None and not parsed.username and not parsed.password
                and parsed.path in {'', '/'} and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        require(valid, 'student_verification_gateway_origin_invalid')
        self.origin = parsed.scheme + '://' + parsed.netloc
        self.connection = HTTPConnection(parsed.hostname, parsed.port, timeout=60)
        self.cookies = {}
        self.requests = 0

    def get(self, path, *, limit):
        require(isinstance(path, str) and path.startswith('/') and not path.startswith('//')
                and not re.search(r'[\x00-\x20\x7f]', path), 'student_verification_request_path_invalid')
        headers = {'Accept': '*/*', 'Accept-Encoding': 'identity'}
        if self.cookies:
            headers['Cookie'] = '; '.join(name + '=' + value for name, value in self.cookies.items())
        self.connection.request('GET', path, headers=headers)
        response = self.connection.getresponse()
        body = response.read(limit + 1)
        require(len(body) <= limit, 'student_verification_gateway_body_oversized')
        for name, value in response.getheaders():
            if name.lower() == 'set-cookie':
                jar = SimpleCookie()
                jar.load(value)
                for cookie_name, morsel in jar.items():
                    require(cookie_name.startswith('mira_openmaic_runtime'), 'student_verification_cookie_invalid')
                    self.cookies[cookie_name] = morsel.value
        self.requests += 1
        return response.status, dict((k.lower(), v) for k, v in response.getheaders()), body

    def close(self):
        self.cookies.clear()
        self.connection.close()


def verify_student_entry(*, database, identity, release, signer, gateway, snapshot=database_snapshot,
                         expected_scene_ids=None):
    """Exercise a genuine ticket exchange and reads, preserving all business rows."""
    before = snapshot(database)
    error = None
    outcome = {}
    try:
        status, _, body = gateway.get('/health', limit=16 * 1024)
        health = json.loads(body)
        require(status == 200 and health.get('service') == 'mira-openmaic-runtime-gateway',
                'student_verification_wrong_gateway')
        authority = {'purpose': 'ticket', 'key': identity['content_key'], 'release': release['sha256'],
            'studentSession': identity['student_session_id'], 'learningSession': identity['learning_session_id'],
            'gradeRevision': int(identity['grade_selection_revision']), 'accessScope': 'published_directory'}
        ticket = 'tbpt_' + signer.dumps(authority)
        status, headers, _ = gateway.get('/mira/textbook-launch?' + urlencode({'ticket': ticket}), limit=16 * 1024)
        del ticket
        cid = release['classroomId']
        expected_document = '/classroom/' + cid + '?mira=1&textbook=1'
        require(status == 303 and headers.get('location') == expected_document,
                'student_verification_exchange_failed')
        token = gateway.cookies.get('mira_openmaic_runtime', '')
        require(token.startswith('tbpr_'), 'student_verification_runtime_cookie_missing')
        runtime = signer.loads(token[5:], max_age=90)
        require(all(runtime.get(k) == v for k, v in authority.items() if k != 'purpose')
                and runtime.get('purpose') == 'runtime' and now_ms() < runtime.get('expiresAt', 0),
                'student_verification_runtime_cookie_not_bound')
        # Keep the production exchange's real cookie; do not forge a replacement
        # or relax its identity checks. No cookie is retained after this run.
        del token
        status, _, document = gateway.get(expected_document, limit=MAX_CLASSROOM_BYTES)
        require(status == 200 and b'<html' in document.lower(), 'student_verification_native_document_failed')
        status, headers, body = gateway.get('/api/classroom?' + urlencode({'id': cid}), limit=MAX_CLASSROOM_BYTES)
        response = json.loads(body)
        room = response.get('classroom')
        original_ids = [s['id'] for s in release['classroom']['scenes']]
        expected_scene_ids = original_ids if expected_scene_ids is None else expected_scene_ids
        require(len(expected_scene_ids) == len(original_ids) and len(set(original_ids)) == len(original_ids)
                and set(expected_scene_ids) == set(original_ids), 'student_verification_scene_projection_invalid')
        require(status == 200 and response.get('success') is True and isinstance(room, dict)
                and room.get('id') == cid and room.get('stage', {}).get('id') == cid
                and room['stage'].get('fixedTextbook') is True
                and [s.get('id') for s in room.get('scenes', [])] == expected_scene_ids,
                'student_verification_classroom_identity_mismatch')
        require(all(not {'answer', 'analysis'} & set(question)
                    for scene in room['scenes'] if scene.get('type') == 'quiz'
                    for question in scene.get('content', {}).get('questions', [])),
                'student_verification_private_answer_exposed')
        audio = next((m for m in release['media'] if m.get('mimeType') in {'audio/wav', 'audio/mpeg'}), None)
        require(audio is not None and re.fullmatch('/api/classroom-media/' + re.escape(cid)
            + r'/audio/[A-Za-z0-9_-]+\.(?:wav|mp3)', audio.get('path', ''))
            and type(audio.get('byteSize')) is int and 0 < audio['byteSize'] <= MAX_AUDIO_BYTES,
            'student_verification_bound_audio_missing')
        status, headers, raw = gateway.get(audio['path'], limit=MAX_AUDIO_BYTES)
        require(status == 200 and headers.get('content-type', '').split(';')[0] == audio['mimeType']
                and len(raw) == audio['byteSize'] and hashlib.sha256(raw).hexdigest() == audio['sha256'],
                'student_verification_audio_hash_mismatch')
        outcome = {'classroomId': cid, 'contentKey': identity['content_key'], 'releaseSha256': release['sha256'],
            'sceneCount': len(room['scenes']), 'classroomResponseSha256': hashlib.sha256(body).hexdigest(),
            'audioSha256': audio['sha256'], 'audioBytes': len(raw), 'gatewayReads': gateway.requests,
            'runtimeExpiresAt': runtime['expiresAt'], 'gatewaySourceVersion': health.get('sourceVersion')}
    except Exception as caught:
        error = caught if isinstance(caught, StudentVerificationError) else StudentVerificationError('student_verification_http_or_contract_failed')
    finally:
        gateway.close()
    after = snapshot(database, guard_cutoff=before['guard']['cutoff'])
    require(before['business'] == after['business'], 'student_verification_business_database_changed')
    require(before['guard']['existing'] == after['guard']['existing']
            and after['guard']['rows'] >= before['guard']['rows'], 'student_verification_existing_guard_audit_changed')
    if error:
        raise error
    return {'ok': True, **outcome, 'businessDatabaseSha256': digest(before['business']),
        'businessTablesUnchanged': len(before['business']), 'guardAuditAppends': after['guard']['rows'] - before['guard']['rows'],
        'studentSessionSha256': hashlib.sha256(identity['student_session_id'].encode()).hexdigest(),
        'learningSessionSha256': hashlib.sha256(identity['learning_session_id'].encode()).hexdigest(),
        'tokensPersisted': False, 'learningEventsSubmitted': 0, 'providerCalls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway-url', default='http://127.0.0.1:3104')
    parser.add_argument('--content-key')
    parser.add_argument('--select-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        app_config = AppConfig.from_env()
        database = ReadOnlyDatabase(Database(app_config.DATABASE_URL))
        identity = select_existing_identity(database, content_key=args.content_key)
        if args.select_only:
            print(json.dumps({'ok': True, 'contentKey': identity['content_key'], 'existingIdentityAvailable': True}))
            return 0
        config = CourseStorageConfig.from_env()
        require(config.mode == 'registry', 'student_verification_registry_required')
        with database.transaction() as conn:
            _, _, release, _ = _validated_release(conn, identity['content_key'])
        store = CourseFileStore(config=config, repository=CourseStorageRepository(database))
        service = TextbookClassroomService(TextbookRepository(database), student_auth=None,
            signing_key=app_config.STUDENT_AUTH_PEPPER, public_url=args.gateway_url, course_file_store=store)
        service._playback_release(release)
        from content import textbook_journey as journey
        scenes = journey.ordered_scenes(release) if journey.supported(release) else release['classroom']['scenes']
        result = verify_student_entry(database=database, identity=identity, release=release,
            signer=service.signer, gateway=GatewayReader(args.gateway_url), expected_scene_ids=[s['id'] for s in scenes])
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, StudentVerificationError) else 'student_verification_failed'
        print(json.dumps({'ok': False, 'errorCode': code,
                          'noIdentityCreated': True, 'tokensPersisted': False}))
        return 2 if code == 'student_verification_no_valid_existing_identity' else 1


if __name__ == '__main__':
    raise SystemExit(main())
