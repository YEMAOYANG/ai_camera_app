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
    with service.repository.transaction() as conn:
        rows = conn.execute("SELECT DISTINCT b.edition_id,b.revision_id FROM learning_textbook_course_builds b "
            "JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id "
            "WHERE b.status='published' AND r.retired_at IS NULL AND r.grade_code=? ORDER BY b.edition_id,b.revision_id",
            (child['grade_code'],)).fetchall()
        for row in rows:
            builds = service.repository.builds(conn, row['edition_id'], row['revision_id'])
            releases = published_node_releases(service.repository, conn, child, builds)
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
            release = published_release(repo, conn, build['content_key'], child)
        except (ApiError, ValueError, TypeError, KeyError, AttributeError):
            # A withdrawn or damaged latest artifact must not hide an older
            # reviewed release or break the whole catalogue response.
            continue
        result[build['node_id']] = release
    return result
