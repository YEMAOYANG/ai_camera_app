#!/usr/bin/env python3
"""Read published release media for storage migration; never dispatch or write SQL.

Only reviewed delivery media and public course identities leave the database.
Original classrooms, answers, audits, account data and credentials stay private.
The resulting inventory is itself private and is never an upload payload.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
PRIVATE_ROOT = ROOT / 'backend/data/course-storage'
NATIVE_ROOT = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms'
SCHEMA = 'mira.course-storage.releases.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
MEDIA_PATH = re.compile(r'/api/classroom-media/(tbpub_[a-f0-9]{24})/(audio|media)/([A-Za-z0-9_.-]+)\Z')
MEDIA_TYPES = frozenset({'audio/wav', 'audio/mpeg', 'image/webp', 'image/png',
                         'image/jpeg', 'video/mp4', 'video/webm', 'model/gltf-binary'})
MAX_MEDIA_BYTES = 16 * 1024 * 1024
# Display translations mirror the Student Web textbook picker; identity comes
# from stored subject/volume codes, never inference from a title or course ID.
SUBJECT_NAMES = {'chinese': '语文', 'math': '数学', 'english': '英语', 'science': '科学'}
VOLUME_NAMES = {'upper': '上册', 'lower': '下册', 'full': '全册'}

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class InventoryError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def parsed(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _require(condition, code):
    if not condition:
        raise InventoryError(code)


def _current_keys(conn, content_key):
    sql = """SELECT b.content_key FROM learning_textbook_course_builds b
        JOIN learning_courses c ON c.id=b.course_id AND c.version=b.course_version
        JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id
        WHERE b.status='published' AND c.status='published' AND c.quality_status='released'
        AND c.retired_at IS NULL AND r.retired_at IS NULL"""
    params = ()
    if content_key is not None:
        _require(SHA.fullmatch(content_key) is not None, 'content_key_invalid')
        sql += ' AND b.content_key=?'
        params = (content_key,)
    rows = conn.execute(sql + ' ORDER BY b.content_key', params).fetchall()
    if content_key is not None:
        _require(len(rows) == 1, 'published_content_key_not_found')
    return [row['content_key'] for row in rows]


def _validated_release(conn, key):
    # Read one large audit at a time. No app factory, worker or generator starts.
    from content.textbook_catalog import digest
    from content.textbook_release import validate_release

    build = conn.execute('SELECT * FROM learning_textbook_course_builds WHERE content_key=?', (key,)).fetchone()
    _require(build is not None, 'published_build_changed')
    revision = conn.execute('SELECT * FROM learning_textbook_revisions WHERE edition_id=? AND revision_id=?',
                            (build['edition_id'], build['revision_id'])).fetchone()
    course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                          (build['course_id'], build['course_version'])).fetchone()
    _require(revision is not None and course is not None, 'published_binding_missing')
    manifest = parsed(revision['manifest_json'])
    _require(digest(manifest) == revision['manifest_sha256'], 'manifest_hash_mismatch')
    release = validate_release(build, manifest, course)
    _require(isinstance(release, dict), 'release_contract_not_supported')
    return build, course, release, manifest


def release_metadata(course, manifest=None):
    """Project public display metadata without changing any release digest."""
    from content.textbook_metadata import course_storage_labels, reviewed_edition_label
    from schemas.education import GRADE_BY_CODE

    subject = course.get('subject', course.get('subjectCode'))
    grade = course.get('grade_code', course.get('gradeCode'))
    if manifest is not None:
        _require(manifest.get('subject', subject) == subject
                 and manifest.get('gradeCode', grade) == grade, 'release_display_identity_mismatch')
    definition = GRADE_BY_CODE.get(grade)
    book = manifest or {}
    return {
        'subjectCode': subject, 'subjectName': SUBJECT_NAMES.get(subject),
        'gradeCode': grade, 'gradeLabel': definition.label if definition else None,
        'volumeCode': book.get('volume'), 'volumeLabel': VOLUME_NAMES.get(book.get('volume')),
        'editionId': book.get('editionId'),
        'editionLabel': reviewed_edition_label(book) if book.get('editionLabel') else None,
        'publisher': book.get('publisher'), 'textbookTitle': book.get('title'),
        'schoolSystem': book.get('schoolSystem'), **course_storage_labels(course, manifest),
        'publishedAt': course.get('published_at', course.get('publishedAt')),
    }


def delivery_media(release):
    """Project only the exact published byte contract; reject outside/raw paths."""
    classroom = release.get('classroomId')
    _require(isinstance(classroom, str) and classroom.startswith('tbpub_'), 'classroom_identity_invalid')
    _require(SHA.fullmatch(str(release.get('sha256', ''))) is not None, 'release_hash_invalid')
    source = release.get('media')
    _require(isinstance(source, list) and bool(source), 'published_media_missing')
    result, seen = [], set()
    for item in source:
        _require(isinstance(item, dict), 'media_entry_invalid')
        path = item.get('path')
        match = MEDIA_PATH.fullmatch(path) if isinstance(path, str) else None
        _require(match is not None and match[1] == classroom and path not in seen,
                 'media_path_not_bound_to_release')
        _require(match[3] not in {'.', '..'} and '..' not in match[3], 'media_path_invalid')
        _require(SHA.fullmatch(str(item.get('sha256', ''))) is not None, 'media_hash_invalid')
        _require(type(item.get('byteSize')) is int and 0 < item['byteSize'] <= MAX_MEDIA_BYTES,
                 'media_size_invalid')
        _require(item.get('mimeType') in MEDIA_TYPES, 'media_type_invalid')
        seen.add(path)
        result.append({field: item[field] for field in ('path', 'sha256', 'byteSize', 'mimeType')})
    return sorted(result, key=lambda item: item['path'])


def _other_published_courses(conn):
    # Non-textbook courses need their own durable formal publication evidence;
    # a course's published flag alone never authorizes its raw/runtime assets.
    return [dict(row) for row in conn.execute("""SELECT c.id AS courseId,c.version AS courseVersion,
        c.title,c.content_origin AS contentOrigin,c.subject AS subjectCode,
        c.grade_code AS gradeCode,c.published_at AS publishedAt FROM learning_courses c
        WHERE c.status='published' AND c.quality_status='released' AND c.retired_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM learning_textbook_course_builds b
            JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id
            WHERE b.course_id=c.id AND b.course_version=c.version AND b.status='published'
            AND r.retired_at IS NULL) ORDER BY c.id,c.version""").fetchall()]


def _formal_authorities(conn, course):
    return conn.execute("""SELECT receipt.publication_receipt_hash,
        runtime.upstream_classroom_id,runtime.feature_manifest_json,
        audio.build_item_id,audio.classroom_content_sha256,audio.expected_segment_count,
        audio.tts_attempted_count,audio.tts_completed_count,audio.audio_validated_count,
        audio.asr_attempted_count,audio.asr_passed_count,audio.terminal_receipt_hash
        FROM learning_curriculum_classroom_item_receipts receipt
        JOIN learning_catalog_release_items item ON item.release_id=receipt.release_id
            AND item.course_id=receipt.course_id AND item.course_version=receipt.course_version
            AND item.package_id=receipt.package_id AND item.package_version=receipt.package_version
        JOIN learning_course_lesson_package_bindings binding ON binding.course_id=item.course_id
            AND binding.course_version=item.course_version AND binding.package_id=item.package_id
            AND binding.package_version=item.package_version
        JOIN learning_lesson_packages package ON package.id=item.package_id
            AND package.version=item.package_version AND package.course_id=item.course_id
            AND package.course_version=item.course_version
        JOIN learning_openmaic_runtime_classrooms runtime ON runtime.id=receipt.runtime_classroom_id
            AND runtime.course_id=item.course_id AND runtime.course_version=item.course_version
            AND runtime.package_id=item.package_id AND runtime.package_version=item.package_version
            AND runtime.candidate_build_item_id=receipt.build_item_id
            AND runtime.candidate_release_id=receipt.release_id
            AND runtime.candidate_grade_code=receipt.grade_code
            AND runtime.candidate_target_fingerprint=receipt.target_fingerprint
        JOIN learning_formal_qwen_audio_jobs audio ON audio.build_item_id=receipt.build_item_id
            AND audio.release_id=receipt.release_id AND audio.grade_code=receipt.grade_code
            AND audio.target_fingerprint=receipt.target_fingerprint
            AND audio.runtime_classroom_id=runtime.id
            AND audio.upstream_classroom_id=runtime.upstream_classroom_id
            AND audio.course_id=item.course_id AND audio.course_version=item.course_version
            AND audio.package_id=item.package_id AND audio.package_version=item.package_version
        WHERE receipt.course_id=? AND receipt.course_version=?
            AND item.status='published' AND item.quality_status='ready' AND item.retired_at IS NULL
            AND package.status='published' AND package.retired_at IS NULL
            AND runtime.status='ready' AND runtime.retired_at IS NULL
            AND receipt.classroom_status='passed' AND receipt.tts_status='passed'
            AND receipt.asr_roundtrip_status='passed' AND receipt.conversation_provider_status='passed'
            AND receipt.auto_validated=1 AND receipt.publication_status='published'
            AND receipt.published_at IS NOT NULL AND audio.state='auto_validated'""",
        (course['courseId'], course['courseVersion'])).fetchall()


def _formal_audio_rows(conn, build_item_id):
    return conn.execute("""SELECT segment.*,
        asset.kind AS asset_kind,asset.status AS asset_status,
        asset.scan_status AS asset_scan_status,asset.moderation_status AS asset_moderation_status,
        asset.transcode_status AS asset_transcode_status,asset.storage_key AS asset_storage_key,
        asset.content_hash AS asset_content_hash,asset.mime_type AS asset_mime_type,
        asset.byte_size AS asset_byte_size,asset.duration_ms AS asset_duration_ms,
        variant.variant_key,variant.status AS variant_status,variant.storage_key AS variant_storage_key,
        variant.content_hash AS variant_content_hash,variant.mime_type AS variant_mime_type,
        variant.byte_size AS variant_byte_size,variant.duration_ms AS variant_duration_ms,
        segment.state AS segment_state,segment.mime_type AS segment_mime_type,
        segment.byte_size AS segment_byte_size,segment.duration_ms AS segment_duration_ms
        FROM learning_formal_qwen_audio_segment_receipts segment
        JOIN learning_media_assets asset ON asset.id=segment.asset_id
        JOIN learning_media_asset_variants variant ON variant.asset_id=asset.id
            AND variant.status='ready'
        WHERE segment.build_item_id=? ORDER BY segment.scene_order,variant.variant_key""", (build_item_id,)).fetchall()


def _verify_local_media(item):
    """Hash only the controlled published source; never fetch remote bytes."""
    source = item.get('sourcePath')
    if source is None:
        match = MEDIA_PATH.fullmatch(item['path'])
        _require(match is not None, 'local_media_source_missing')
        source = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/' + item['path'].removeprefix('/api/classroom-media/')
    _require(isinstance(source, str) and (source.startswith(
        'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/') or source.startswith(
        'backend/data/learning-media/narration/')) and '\\' not in source
        and not {'', '.', '..'}.intersection(source.split('/')), 'local_media_source_invalid')
    path = ROOT / source
    _require(path.is_file() and path.resolve() == path and path.stat().st_size == item['byteSize'],
             'local_media_bytes_mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    _require(digest.hexdigest() == item['sha256'], 'local_media_hash_mismatch')


def _formal_release(conn, course, media_root, *, verify_source_bytes=False):
    """Use durable publication receipts, never a newly invented release hash."""
    from services.openmaic_runtime_audio_service import OpenMaicRuntimeAudioService

    authorities = _formal_authorities(conn, course)
    _require(len(authorities) == 1, 'formal_publication_binding_missing_or_ambiguous')
    authority = authorities[0]
    classroom = authority['upstream_classroom_id']
    _require(isinstance(classroom, str) and re.fullmatch(r'[A-Za-z0-9_-]+', classroom),
             'formal_classroom_identity_invalid')
    for field in ('publication_receipt_hash', 'classroom_content_sha256', 'terminal_receipt_hash'):
        _require(SHA.fullmatch(str(authority[field])) is not None, 'formal_publication_hash_invalid')
    expected = authority['expected_segment_count']
    _require(type(expected) is int and 1 <= expected <= 240
             and all(authority[field] == expected for field in ('tts_attempted_count',
                 'tts_completed_count', 'audio_validated_count', 'asr_attempted_count', 'asr_passed_count')),
             'formal_audio_terminal_incomplete')
    native_root = NATIVE_ROOT.resolve()
    room_file = (native_root / classroom / 'artifact/classroom.json' if classroom.startswith('omclass_')
                 else native_root / (classroom + '.json'))
    _require(room_file.is_file() and room_file.resolve() == room_file,
             'formal_classroom_source_missing_or_linked')
    room = json.loads(room_file.read_text())
    manifest = parsed(authority['feature_manifest_json'])
    room_hash = hashlib.sha256(canonical({'stage': room.get('stage'), 'scenes': room.get('scenes')}).encode()).hexdigest()
    _require(room.get('stage', {}).get('id') == classroom
             and room_hash == manifest.get('classroomContentSha256') == authority['classroom_content_sha256'],
             'formal_classroom_hash_mismatch')
    media = []
    for receipt_key in ('media', 'video'):
        receipt = manifest.get(receipt_key)
        if receipt is None:
            continue
        _require(isinstance(receipt, dict) and isinstance(receipt.get('assets'), list),
                 'formal_native_media_receipt_invalid')
        unhashed = {k: v for k, v in receipt.items() if k != 'receiptSha256'}
        _require(receipt.get('classroomId') == classroom
                 and receipt.get('buildItemId') == authority['build_item_id']
                 and hashlib.sha256(canonical(unhashed).encode()).hexdigest() == receipt.get('receiptSha256'),
                 'formal_native_media_receipt_hash_mismatch')
        for asset in receipt['assets']:
            path = asset.get('src')
            _require(isinstance(path, str) and re.fullmatch(
                r'/api/classroom-media/' + re.escape(classroom) + r'/media/[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp|gif|mp4|webm)', path),
                'formal_native_media_path_invalid')
            _require(SHA.fullmatch(str(asset.get('sha256', ''))) is not None
                     and type(asset.get('byteSize')) is int and 0 < asset['byteSize'] <= 32 * 1024 * 1024
                     and asset.get('mimeType') in MEDIA_TYPES | {'image/gif'}, 'formal_native_media_contract_invalid')
            rest = path.removeprefix('/api/classroom-media/' + classroom + '/')
            relative = classroom + ('/artifact/' if classroom.startswith('omclass_') else '/') + rest
            media.append({'path': path,
                'sourcePath': 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/' + relative,
                **{k: asset[k] for k in ('sha256', 'byteSize', 'mimeType')}})
    referenced = set(re.findall(r'/api/classroom-media/[A-Za-z0-9_-]+/(?:audio|media)/[A-Za-z0-9_.-]+', canonical(room)))
    _require(referenced == {item['path'] for item in media}, 'formal_native_media_unaccounted')
    rows = _formal_audio_rows(conn, authority['build_item_id'])
    _require(len(rows) == expected and [row['scene_order'] for row in rows] == list(range(expected))
             and len({row['asset_id'] for row in rows}) == expected, 'formal_audio_segments_incomplete')
    # Reuse its frozen byte/hash/PCM metadata contract without opening a DB
    # connection, minting a student session or fetching remote media.
    for row in rows:
        digest, byte_size, _ = OpenMaicRuntimeAudioService.verify_asset_metadata(row)
        relative = PurePosixPath(row['storage_key'])
        _require(relative.parts and relative.parts[0] == 'narration' and relative.suffix == '.wav'
                 and not relative.is_absolute() and not {'', '.', '..'}.intersection(relative.parts)
                 and '\\' not in row['storage_key'],
                 'formal_audio_source_not_narration')
        media.append({'path': '/mira/runtime-audio/' + row['asset_id'],
            'sourcePath': 'backend/data/learning-media/' + relative.as_posix(),
            'sha256': digest, 'byteSize': byte_size, 'mimeType': 'audio/wav'})
    _require(len({item['path'] for item in media}) == len(media), 'formal_media_path_duplicate')
    if verify_source_bytes:
        for item in media:
            _verify_local_media(item)
    return {'contentKey': None, 'releaseSha256': authority['publication_receipt_hash'],
        'classroomId': classroom, 'courseId': course['courseId'], 'courseVersion': course['courseVersion'],
        'title': course['title'], 'media': sorted(media, key=lambda item: item['path']),
        **release_metadata(course)}


def inventory(conn, *, content_key=None, media_root=None, verify_source_bytes=False):
    releases, failures, unique_paths, blobs = [], [], {}, {}
    keys = _current_keys(conn, content_key)
    for key in keys:
        try:
            build, course, release, manifest = _validated_release(conn, key)
            media = delivery_media(release)
            if verify_source_bytes:
                for item in media:
                    _verify_local_media(item)
            _require(release['contentKey'] == key
                     and release['classroomId'] == 'tbpub_' + key[:24], 'release_identity_mismatch')
            pending_paths, pending_blobs = {}, {}
            for item in media:
                previous = unique_paths.get(item['path'])
                _require(previous is None or previous == item, 'media_path_conflict')
                pending_paths[item['path']] = item
                previous_blob = blobs.get(item['sha256'])
                _require(previous_blob is None or previous_blob == (item['byteSize'], item['mimeType']),
                         'media_blob_contract_conflict')
                pending_blobs[item['sha256']] = (item['byteSize'], item['mimeType'])
            unique_paths.update(pending_paths)
            blobs.update(pending_blobs)
            releases.append({
                'contentKey': key, 'releaseSha256': release['sha256'],
                'classroomId': release['classroomId'], 'courseId': course['id'],
                'courseVersion': course['version'], 'title': course['title'], 'media': media,
                **release_metadata(course, manifest),
            })
        except Exception as exc:
            # Error text/tracebacks can contain private source material. Emit
            # only an existing API error code or a bounded static error name.
            code = getattr(exc, 'code', None) or (str(exc) if isinstance(exc, InventoryError) else type(exc).__name__)
            failures.append({'contentKey': key, 'error': code})
    other = _other_published_courses(conn) if content_key is None else []
    uncovered = []
    for course in other:
        try:
            formal = _formal_release(conn, course, media_root or BACKEND / 'data/learning-media',
                                     verify_source_bytes=verify_source_bytes)
            for item in formal['media']:
                previous = unique_paths.get(item['path'])
                _require(previous is None or previous == item, 'media_path_conflict')
                previous_blob = blobs.get(item['sha256'])
                _require(previous_blob is None or previous_blob == (item['byteSize'], item['mimeType']),
                         'media_blob_contract_conflict')
            for item in formal['media']:
                unique_paths[item['path']] = item
                blobs[item['sha256']] = (item['byteSize'], item['mimeType'])
            releases.append(formal)
        except Exception as exc:
            code = getattr(exc, 'code', None) or (str(exc) if isinstance(exc, InventoryError) else type(exc).__name__)
            failures.append({'courseId': course['courseId'], 'error': code})
            uncovered.append(course)
    metadata = [{'contentKey': r['contentKey'], 'courseId': r['courseId'], 'releaseSha256': r['releaseSha256'],
                 'media': r['media']} for r in releases]
    return {
        'schemaVersion': SCHEMA,
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'validation': {'logicalReleaseContracts': True,
                       'localMediaBytesVerified': verify_source_bytes,
                       'remoteMediaBytesVerified': False},
        'scope': {'contentKey': content_key, 'publishedOnly': True, 'retiredIncluded': False},
        'ok': not failures,
        'releases': releases,
        'totals': {
            'selectedReleaseCount': len(keys) + len(other), 'releaseCount': len(releases),
            'textbookReleaseCount': len(keys), 'formalReleaseCount': len(other) - len(uncovered),
            'mediaEntries': sum(len(r['media']) for r in releases),
            'uniquePaths': len(unique_paths), 'uniqueBlobs': len(blobs),
            'totalByteSize': sum(item['byteSize'] for item in unique_paths.values()),
            'uniqueBlobByteSize': sum(size for size, _ in blobs.values()),
        },
        'mediaInventorySha256': hashlib.sha256(canonical(metadata).encode()).hexdigest(),
        'validationFailures': failures,
        'nonTextbookPublishedCourses': [{k: c[k] for k in
            ('courseId', 'courseVersion', 'title', 'contentOrigin')} for c in other],
        'uncoveredPublishedCourses': [{k: c[k] for k in
            ('courseId', 'courseVersion', 'title', 'contentOrigin')} for c in uncovered],
        'allPublishedCourseMediaCovered': content_key is None and not failures and not uncovered,
    }


def write_private_inventory(value, output):
    _require(value.get('ok') is True, 'inventory_validation_failed_no_export')
    output = Path(output).absolute()
    lexical_root = PRIVATE_ROOT.absolute()
    _require(output.is_relative_to(lexical_root), 'output_outside_private_storage')
    _require('..' not in output.relative_to(lexical_root).parts, 'output_outside_private_storage')
    # macOS /var is a system alias. Trust the configured root's ancestors,
    # while rejecting links inside the private output subtree.
    _require(not lexical_root.is_symlink(), 'output_symlink_forbidden')
    root = lexical_root.resolve()
    output = root / output.relative_to(lexical_root)
    ancestors = [p for p in output.parents if p.is_relative_to(root)]
    _require(not any(p.is_symlink() for p in (output, *ancestors)), 'output_symlink_forbidden')
    _require(output.suffix == '.json' and not output.exists(), 'output_must_be_new_json')
    missing = []
    parent = output.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write((canonical(value) + '\n').encode())
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {'path': str(output), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


@contextmanager
def read_only_connection(database):
    conn = database.connect()
    try:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        conn.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        yield conn
    finally:
        conn.rollback()
        conn.close()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('mode', choices=('inventory', 'validate-all-published', 'validate-all-release'))
    result.add_argument('--content-key', help='Only this exact current published textbook release')
    result.add_argument('--output', type=Path, help='New private JSON under backend/data/course-storage/')
    result.add_argument('--verify-local', action='store_true',
                        help='Also read and SHA-256 check every published local media source (no remote GET)')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.mode != 'inventory' and args.output is not None:
        parser().error('validation prints aggregate results and takes no --output')
    # Configuration and DB imports stay inside main: importing/--help is inert.
    from core.config import AppConfig
    from core.database import Database
    try:
        config = AppConfig.from_env()
        media_root = Path(config.LEARNING_MEDIA_STORAGE_ROOT)
        media_root = media_root if media_root.is_absolute() else BACKEND / media_root
        with read_only_connection(Database(config.DATABASE_URL)) as conn:
            value = inventory(conn, content_key=args.content_key, media_root=media_root,
                              verify_source_bytes=args.verify_local)
        result = {key: value[key] for key in ('schemaVersion', 'scope', 'validation', 'ok', 'totals',
                  'mediaInventorySha256', 'validationFailures', 'nonTextbookPublishedCourses',
                  'uncoveredPublishedCourses', 'allPublishedCourseMediaCovered')}
        if args.mode == 'inventory' and value['ok']:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            label = args.content_key[:12] if args.content_key else 'all-published'
            target = args.output or PRIVATE_ROOT / 'manifests' / f'{label}-{stamp}-{os.getpid()}.json'
            result['file'] = write_private_inventory(value, target)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if value['ok'] else 1
    except Exception as exc:
        code = str(exc) if isinstance(exc, InventoryError) else type(exc).__name__
        print(json.dumps({'ok': False, 'error': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
