"""Expose reviewed releases through their exact textbook directories."""
from collections import OrderedDict
import codecs
import hashlib
from threading import Event, Lock
from time import monotonic

from content.textbook_batch_release import (
    INPUT_SCHEMA as ACTIVITY_INPUT_SCHEMA,
    RELEASE_SCHEMA as ACTIVITY_RELEASE_SCHEMA,
    REVIEW_FLAGS as ACTIVITY_REVIEW_FLAGS,
    REVIEW_SCHEMA as ACTIVITY_REVIEW_SCHEMA,
    validate_input as validate_activity_input,
)
from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_release import (
    INPUT_SCHEMA as CLASSROOM_INPUT_SCHEMA,
    KEY,
    RELEASE_SCHEMA as CLASSROOM_RELEASE_SCHEMA,
    fail,
    validate_release,
)
from core.errors import ApiError


_VALIDATION_CACHE_TTL_SECONDS = 120
_VALIDATION_CACHE_MAX_ENTRIES = 64
_validation_cache = OrderedDict()
_validation_inflight = {}
_validation_cache_lock = Lock()


def _value_sha256(value):
    """Hash large JSON text without making a second full-size UTF-8 copy."""
    if not isinstance(value, (str, bytes, bytearray, memoryview)):
        value = canonical(value)
    result = hashlib.sha256()
    if isinstance(value, str):
        encoder = codecs.getincrementalencoder('utf-8')()
        for start in range(0, len(value), 1024 * 1024):
            result.update(encoder.encode(value[start:start + 1024 * 1024]))
        result.update(encoder.encode('', final=True))
    else:
        result.update(value)
    return result.hexdigest()


def _validation_fingerprint(build, manifest, course):
    """Bind a cache hit to every mutable input used by validate_release."""
    return digest({
        'build': {key: build.get(key) for key in (
            'content_key', 'edition_id', 'revision_id', 'node_id', 'part_index',
            'teaching_revision', 'course_id', 'course_version',
            'course_content_sha256', 'status', 'created_at', 'updated_at')},
        'inputJsonSha256': _value_sha256(build.get('input_json')),
        'reviewJsonSha256': _value_sha256(build.get('review_json')),
        'manifestSha256': digest(manifest),
        'course': {key: course.get(key) for key in (
            'id', 'version', 'grade_code', 'subject', 'status', 'quality_status',
            'content_origin', 'retired_at')},
        'courseContentJsonSha256': _value_sha256(course.get('content_json')),
    })


def _cache_entry(fingerprint):
    now = monotonic()
    with _validation_cache_lock:
        entry = _validation_cache.get(fingerprint)
        if entry is None:
            return None
        if entry['expiresAt'] <= now:
            _validation_cache.pop(fingerprint, None)
            return None
        _validation_cache.move_to_end(fingerprint)
        return entry


def _release_from_entry(repo, build, entry):
    try:
        review = repo.parse(build.get('review_json')) or {}
        release = review.get('release')
    except (ValueError, TypeError, AttributeError):
        return None
    if (not isinstance(release, dict)
            or release.get('sha256') != entry['releaseSha256']
            or release.get('schemaVersion') != entry['releaseSchemaVersion']):
        return None
    return release


def _validate_release_cached(repo, build, manifest, course):
    """Reuse only a successful validation of byte-identical published inputs."""
    fingerprint = _validation_fingerprint(build, manifest, course)
    while True:
        entry = _cache_entry(fingerprint)
        if entry is not None:
            release = _release_from_entry(repo, build, entry)
            if release is not None:
                return release
        with _validation_cache_lock:
            current = _validation_cache.get(fingerprint)
            if current is not None and current['expiresAt'] > monotonic():
                _validation_cache.move_to_end(fingerprint)
                retry_cached = True
                event = None
                leader = False
            else:
                if current is not None:
                    _validation_cache.pop(fingerprint, None)
                retry_cached = False
                event = _validation_inflight.get(fingerprint)
                if event is None:
                    event = Event()
                    _validation_inflight[fingerprint] = event
                    leader = True
                else:
                    leader = False
        if retry_cached:
            continue
        if leader:
            break
        event.wait()

    try:
        release = validate_release(build, manifest, course)
        if not isinstance(release, dict) or not isinstance(release.get('sha256'), str):
            return release
        entry = {
            'expiresAt': monotonic() + _VALIDATION_CACHE_TTL_SECONDS,
            'releaseSha256': release['sha256'],
            'releaseSchemaVersion': release.get('schemaVersion'),
        }
        with _validation_cache_lock:
            _validation_cache[fingerprint] = entry
            _validation_cache.move_to_end(fingerprint)
            while len(_validation_cache) > _VALIDATION_CACHE_MAX_ENTRIES:
                _validation_cache.popitem(last=False)
        return release
    finally:
        with _validation_cache_lock:
            completed = _validation_inflight.pop(fingerprint, None)
            if completed is not None:
                completed.set()


def _clear_validation_cache_for_tests():
    with _validation_cache_lock:
        _validation_cache.clear()


def _directory_course(build):
    return {
        'id': build.get('directory_course_id'),
        'version': build.get('directory_course_version'),
        'title': build.get('directory_course_title'),
        'grade_code': build.get('directory_course_grade_code'),
        'subject': build.get('directory_course_subject'),
        'content_json': build.get('directory_course_content_json'),
        'status': build.get('directory_course_status'),
        'quality_status': build.get('directory_course_quality_status'),
        'content_origin': build.get('directory_course_content_origin'),
        'retired_at': build.get('directory_course_retired_at'),
    }


def _json_true(value):
    """Normalize MySQL JSON booleans and SQLite JSON1's integer booleans."""
    return value is True or type(value) is int and value == 1


def _directory_entry(repo, build, manifest, child):
    """Validate the small publication projection used only by directory reads.

    The release SHA is anchored in the exact, hashed course content. The full
    classroom and audio evidence are deliberately absent here and are validated
    by ``published_release`` before launch and on every classroom authority.
    """
    key = build.get('content_key') if build else None
    if (not isinstance(key, str) or KEY.fullmatch(key) is None
            or build.get('status') != 'published' or build.get('part_index') != 1
            or build.get('edition_id') != manifest.get('editionId')
            or build.get('revision_id') != manifest.get('revisionId')
            or manifest.get('gradeCode') != child.get('grade_code')):
        fail()
    frozen = repo.parse(build.get('input_json'))
    evidence = repo.parse(build.get('directory_review_evidence_json'))
    release = repo.parse(build.get('directory_release_summary_json'))
    course = _directory_course(build)
    content = repo.parse(course.get('content_json'))
    if (not isinstance(frozen, dict) or not isinstance(evidence, dict)
            or not isinstance(release, dict) or not isinstance(content, dict)
            or course['id'] != build.get('course_id')
            or course['version'] != build.get('course_version')
            or course['status'] != 'published' or course['quality_status'] != 'released'
            or course.get('retired_at') is not None
            or digest(content) != build.get('course_content_sha256')):
        fail()

    # MySQL and SQLite both retain the exact evidence JSON. SQLite JSON_OBJECT
    # exposes a projected JSON boolean as 0/1, so the accompanying JSON type is
    # authoritative and prevents a numeric 1 from being relabelled as true.

    binding = frozen.get('textbookBinding', {})
    if (binding != {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
            'alignmentManifestSha256': digest(manifest), 'nodeId': build['node_id'],
            'partIndex': 1, 'teachingRevision': build['teaching_revision']}
            or frozen.get('contentKey') != key
            or digest({k: v for k, v in frozen.items() if k != 'contentKey'}) != key):
        fail()

    release_sha = release.get('sha256')
    classroom_id = 'tbpub_' + key[:24]
    audio = release.get('audioAudit')
    if (not isinstance(release_sha, str) or KEY.fullmatch(release_sha) is None
            or release.get('contentKey') != key
            or release.get('classroomId') != classroom_id
            or not isinstance(release.get('classroomSha256'), str)
            or KEY.fullmatch(release['classroomSha256']) is None
            or release.get('classroomObjectId') != classroom_id
            or release.get('stageId') != classroom_id
            or release.get('mediaType') not in ('ARRAY', 'array')
            or type(release.get('mediaCount')) is not int or release['mediaCount'] < 1
            or release.get('scenesType') not in ('ARRAY', 'array')
            or type(release.get('sceneCount')) is not int or release['sceneCount'] < 1
            or not isinstance(audio, dict) or audio.get('passedType') not in ('BOOLEAN', 'true')
            or not _json_true(audio.get('passed'))
            or audio.get('segmentsType') not in ('INTEGER', 'integer')
            or type(audio.get('segments')) is not int or audio['segments'] < 0
            or content.get('releaseSha256') != release_sha):
        fail()

    if frozen.get('schemaVersion') == ACTIVITY_INPUT_SCHEMA:
        validate_activity_input(frozen, manifest)
        if (evidence.get('schemaVersion') != ACTIVITY_REVIEW_SCHEMA
                or any(evidence.get(name) is not True for name in ACTIVITY_REVIEW_FLAGS)
                or not evidence.get('reviewer') or not evidence.get('basis') or not evidence.get('evidence')
                or evidence.get('sourceSha256') != frozen.get('sourceSha256')
                or evidence.get('sourceInputSha256') != frozen.get('sourceInputSha256')
                or evidence.get('audioAuditSha256') != frozen.get('audioAuditSha256')
                or digest(evidence) != frozen.get('reviewSha256')
                or release.get('schemaVersion') != ACTIVITY_RELEASE_SCHEMA
                or release.get('assessmentMode') != 'ungraded'
                or release.get('activityScopeType') not in ('OBJECT', 'object')
                or release.get('activityScope') != frozen.get('activityScope')
                or audio.get('sha256') != frozen.get('audioAuditSha256')
                or type(audio.get('segments')) is not int or audio['segments'] < 1
                or type(audio.get('minSimilarityBps')) is not int
                or audio['minSimilarityBps'] < 8500
                or course.get('grade_code') != frozen.get('gradeCode')
                or course.get('subject') != frozen.get('subject')
                or content.get('textbookBinding') != binding
                or content.get('assessmentMode') != 'ungraded'
                or content.get('questions') != []):
            fail()
    elif frozen.get('schemaVersion') == CLASSROOM_INPUT_SCHEMA:
        _, node = lesson_by_id(manifest, build['node_id'])
        if (release.get('schemaVersion') != CLASSROOM_RELEASE_SCHEMA
                or any(evidence.get(name) is not True for name in (
                    'alignmentConfirmed', 'originalExpressionConfirmed',
                    'sourceUsageConfirmed', 'publicationAuthorized'))
                or not evidence.get('reviewer') or not evidence.get('basis')
                or frozen.get('knowledgeBrief') != node['brief']
                or frozen.get('gradeCode') != manifest['gradeCode']):
            fail()
    else:
        fail()
    return build, release, course, manifest


def _published_release_from_build(repo, conn, build, child):
    key = build.get('content_key') if build else None
    if not isinstance(key, str) or not KEY.fullmatch(key) or build['status'] != 'published':
        fail()
    row = repo.get_revision(conn, build['edition_id'], build['revision_id'])
    if row is None:
        fail()
    manifest = repo.manifest(row)
    if digest(manifest) != row['manifest_sha256'] or manifest['gradeCode'] != child['grade_code']:
        fail()
    course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                          (build['course_id'], build['course_version'])).fetchone()
    if course is None or course.get('retired_at') is not None:
        fail()
    release = _validate_release_cached(repo, build, manifest, course)
    if release is None:
        fail()
    return build, release, course, manifest


def published_release(repo, conn, key, child):
    if not isinstance(key, str) or not KEY.fullmatch(key):
        fail()
    build = repo.get_build(conn, key)
    return _published_release_from_build(repo, conn, build, child)


def published_books(service, child):
    """Only add book revisions that actually contain a valid published release."""
    result = {}
    with service.repository.transaction() as conn:
        rows = conn.execute("SELECT DISTINCT b.edition_id,b.revision_id FROM learning_textbook_course_builds b "
            "JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id "
            "WHERE b.status='published' AND r.retired_at IS NULL AND r.grade_code=? ORDER BY b.edition_id,b.revision_id",
            (child['grade_code'],)).fetchall()
        for row in rows:
            revision = service.repository.get_revision(conn, row['edition_id'], row['revision_id'])
            if revision is None:
                continue
            manifest = service.repository.manifest(revision)
            if digest(manifest) != revision['manifest_sha256'] or manifest['gradeCode'] != child['grade_code']:
                continue
            builds = service.repository.directory_builds(conn, row['edition_id'], row['revision_id'])
            releases = published_node_directory_entries(service.repository, child, builds, manifest)
            for build, _, _, manifest in releases.values():
                identity = (manifest['editionId'], manifest['revisionId'])
                if identity not in result:
                    result[identity] = {**service._book(manifest), 'selected': False, 'selectionRevision': 0,
                        'currentNodeId': None, 'accessMode': 'published', 'learningStatus': {'status': 'ready',
                        'availableLessonCount': 0, 'availableActivityCount': 0, 'completedLessonCount': 0}}
                kind = service.repository.parse(build['input_json']).get('activityScope', {}).get('kind', 'lesson_courseware')
                counter = 'availableLessonCount' if kind == 'lesson_courseware' else 'availableActivityCount'
                result[identity]['learningStatus'][counter] += 1
    return result


def published_node_directory_entries(repo, child, builds, manifest):
    """Return the latest fail-closed directory projection for each node.

    This is deliberately separate from ``published_node_releases``: callers
    receive enough authority to render an unchanged directory response, never a
    full classroom that could be played without the strict launch validator.
    """
    result = {}
    for build in sorted(builds, key=lambda row: (-int(row['created_at']), row['content_key'])):
        if build['part_index'] != 1 or build['node_id'] in result:
            continue
        try:
            entry = _directory_entry(repo, build, manifest, child)
        except (ApiError, ValueError, TypeError, KeyError, AttributeError):
            # A damaged latest summary falls back only within this exact book
            # revision and node. Launch still validates the selected full row.
            continue
        result[build['node_id']] = entry
    return result


def published_node_releases(repo, conn, child, builds):
    """One latest valid release per directory node, shared by every student.

    Only publication integrity determines a fallback. Personal progress and
    selected books must never select different teaching revisions for a node.
    The directory contract exposes part one; other parts are not counted here.
    """
    result = {}
    for build in sorted(builds, key=lambda row: (-int(row['created_at']), row['content_key'])):
        if build['part_index'] != 1 or build['node_id'] in result:
            continue
        try:
            release = _published_release_from_build(repo, conn, build, child)
        except (ApiError, ValueError, TypeError, KeyError, AttributeError):
            # A withdrawn or damaged latest artifact must not hide an older
            # reviewed release or break the whole catalogue response.
            continue
        result[build['node_id']] = release
    return result
