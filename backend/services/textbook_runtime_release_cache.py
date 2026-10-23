"""Bounded, verified classroom projections; original publication audits stay intact.

Only playback uses this cache. Publication and inspection still read and verify
the full release. Authentication, child/session identity and permissions remain
the responsibility of TextbookClassroomService on every request.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import BoundedSemaphore, Event, Lock
from time import monotonic

from content.textbook_catalog import canonical, digest
from content.textbook_release import KEY, fail
from services import textbook_directory_access as directory

_TTL_SECONDS = 1800
_MAX_ENTRIES = 64
_MAX_BYTES = 64 * 1024 * 1024
_cache = OrderedDict()
_inflight = {}
_lock = Lock()
_identity_slots = BoundedSemaphore(2)
_cold_load_slot = BoundedSemaphore(1)


def _checked_identity(repo, conn, key, child):
    with _identity_slots:
        value = repo.runtime_release_identity(conn, key)
    if not value:
        fail()
    build, revision, course = (value[name] for name in ('build', 'revision', 'course'))
    if (build['status'] != 'published' or not revision or not course
            or revision.get('retired_at') is not None
            or course.get('retired_at') is not None
            or course.get('status') != 'published' or course.get('quality_status') != 'released'):
        fail()
    manifest = repo.manifest(revision)
    if (digest(manifest) != revision['manifest_sha256']
            or manifest.get('gradeCode') != child['grade_code']):
        fail()
    return value, digest(value)


def _matches_full(identity, full):
    build, _, course, manifest = full
    expected = identity['build']
    return (all(build.get(k) == v for k, v in expected.items()
                if k not in {'input_sha256', 'review_sha256'})
            and directory._value_sha256(build.get('input_json')) == expected['input_sha256']
            and directory._value_sha256(build.get('review_json')) == expected['review_sha256']
            and course == identity['course']
            and digest(manifest) == identity['revision']['manifest_sha256'])


def _projection(full):
    build, release, course, manifest = full
    # Preserve original frozen input and grading content. Only public_classroom
    # removes answers on delivery; stripping them here would change grading.
    return ({k: v for k, v in build.items() if k != 'review_json'},
            {k: v for k, v in release.items() if k != 'audioAudit'}, course, manifest)


def published_runtime_release(repo, conn, key, child):
    if not isinstance(key, str) or KEY.fullmatch(key) is None:
        fail()
    while True:
        identity, fingerprint = _checked_identity(repo, conn, key, child)
        with _lock:
            now = monotonic()
            expired = [k for k, v in _cache.items() if v['expires'] <= now]
            for k in expired:
                _cache.pop(k)
            cached = _cache.get(fingerprint)
            if cached is not None:
                _cache.move_to_end(fingerprint)
                return deepcopy(cached['value'])
            event = _inflight.get(fingerprint)
            leader = event is None
            if leader:
                event = Event()
                _inflight[fingerprint] = event
        if leader:
            break
        # The leader reads the large row only once. Recheck live authority after
        # waiting; neither the event nor the cache authorizes a student session.
        if not event.wait(25):
            fail('课堂正在校验，请稍后重新进入')

    try:
        # Different lessons can also contain large audits. Bound their full
        # reads/decoding, rather than merely bounding the retained projections.
        with _cold_load_slot:
            build = repo.get_build(conn, key)
            full = directory._published_release_from_build(repo, conn, build, child)
            if not _matches_full(identity, full):
                fail('课程发布数据已变化，请重新进入')
            _, after = _checked_identity(repo, conn, key, child)
            if after != fingerprint:
                fail('课程发布数据已变化，请重新进入')
            value = _projection(full)
            del full, build
        size = len(canonical(value).encode('utf-8'))
        if size <= _MAX_BYTES:
            with _lock:
                _cache[fingerprint] = {'value': deepcopy(value), 'size': size,
                                       'expires': monotonic() + _TTL_SECONDS}
                _cache.move_to_end(fingerprint)
                while (len(_cache) > _MAX_ENTRIES
                       or sum(v['size'] for v in _cache.values()) > _MAX_BYTES):
                    _cache.popitem(last=False)
        return deepcopy(value)
    finally:
        with _lock:
            done = _inflight.pop(fingerprint, None)
            if done is not None:
                done.set()


def _clear_for_tests():
    with _lock:
        _cache.clear()
