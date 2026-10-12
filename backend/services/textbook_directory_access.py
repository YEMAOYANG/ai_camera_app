"""Expose reviewed releases through their exact textbook directories."""
from content.textbook_catalog import digest
from content.textbook_release import KEY, fail, validate_release
from core.errors import ApiError


def published_release(repo, conn, key, child):
    if not isinstance(key, str) or not KEY.fullmatch(key):
        fail()
    build = repo.get_build(conn, key)
    if build is None or build['status'] != 'published':
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
    release = validate_release(build, manifest, course)
    if release is None:
        fail()
    return build, release, course, manifest


def published_books(service, child):
    """Only add book revisions that actually contain a valid published release."""
    result = {}
    counted_nodes = set()
    with service.repository.transaction() as conn:
        rows = conn.execute("SELECT b.content_key FROM learning_textbook_course_builds b "
            "JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id "
            "WHERE b.status='published' AND r.retired_at IS NULL AND r.grade_code=? ORDER BY b.content_key",
            (child['grade_code'],)).fetchall()
        for row in rows:
            try:
                build, _, _, manifest = published_release(service.repository, conn, row['content_key'], child)
            except ApiError:
                continue
            identity = (manifest['editionId'], manifest['revisionId'])
            if identity not in result:
                result[identity] = {**service._book(manifest), 'selected': False, 'selectionRevision': 0,
                    'currentNodeId': None, 'accessMode': 'published', 'learningStatus': {'status': 'ready',
                    'availableLessonCount': 0, 'availableActivityCount': 0, 'completedLessonCount': 0}}
            kind = service.repository.parse(build['input_json']).get('activityScope', {}).get('kind', 'lesson_courseware')
            # A new teaching revision preserves its older release, but the
            # directory still exposes one entry for this node and part.
            slot = (*identity, build['node_id'], build['part_index'], kind)
            if slot in counted_nodes:
                continue
            counted_nodes.add(slot)
            counter = 'availableLessonCount' if kind == 'lesson_courseware' else 'availableActivityCount'
            result[identity]['learningStatus'][counter] += 1
    return result
