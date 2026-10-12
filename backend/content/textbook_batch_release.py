"""Versioned delivery contract for reviewed, ungraded textbook activities.

Private generation receipts are never publication authority. This separate
release binds an exact saved artifact, review, teacher and media inventory.
"""
from content.textbook_catalog import digest, lesson_by_id
from content.textbook_release import KEY, MEDIA, fail, questions
from content.teacher_profiles import get_formal_subject_qwen_voice_identity

INPUT_SCHEMA = 'mira.textbook.activity-release-input.v1'
RELEASE_SCHEMA = 'mira.textbook.activity-release.v1'
REVIEW_SCHEMA = 'mira.textbook.activity-publication-review.v1'
KINDS = ('book_exploration', 'unit_guide', 'lesson_courseware')
REVIEW_FLAGS = ('alignmentConfirmed', 'originalExpressionConfirmed', 'sourceUsageConfirmed',
                'publicationAuthorized', 'visualInteractionConfirmed', 'narrationStateConfirmed')


def node_key(kind, unit_id=None, node_id=None):
    if kind == 'book_exploration':
        return 'explore-book'
    if kind == 'unit_guide' and isinstance(unit_id, str) and unit_id:
        return 'guide-' + digest(unit_id)[:32]
    if kind == 'lesson_courseware' and isinstance(node_id, str) and node_id:
        return node_id
    fail('探索、单元和课次身份不完整')


def activity_unit(manifest, frozen):
    scope = frozen.get('activityScope', {})
    kind = scope.get('kind')
    unit = next((u for u in manifest['units'] if u['unitId'] == scope.get('unitId')), None)
    if kind == 'book_exploration':
        if scope.get('unitId') is not None or scope.get('nodeId') is not None or not manifest['units']:
            fail()
        return None
    if kind not in KINDS or unit is None:
        fail('导学与教材单元不一致')
    if kind == 'unit_guide' and scope.get('nodeId') is not None:
        fail()
    if kind == 'lesson_courseware':
        actual, _ = lesson_by_id(manifest, scope.get('nodeId'))
        if actual['unitId'] != unit['unitId']:
            fail()
    return unit


def validate_input(frozen, manifest):
    if not isinstance(frozen, dict) or frozen.get('schemaVersion') != INPUT_SCHEMA:
        fail()
    activity_unit(manifest, frozen)
    scope = frozen['activityScope']
    binding = frozen.get('textbookBinding', {})
    if (binding != {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
            'alignmentManifestSha256': digest(manifest),
            'nodeId': node_key(scope['kind'], scope.get('unitId'), scope.get('nodeId')),
            'partIndex': 1, 'teachingRevision': binding.get('teachingRevision')}
            or not isinstance(binding.get('teachingRevision'), str) or not 1 <= len(binding['teachingRevision']) <= 64
            or frozen.get('gradeCode') != manifest['gradeCode'] or frozen.get('subject') != manifest['subject']
            or frozen.get('assessmentMode') != 'ungraded'
            or frozen.get('teacher') != get_formal_subject_qwen_voice_identity(manifest['subject']).to_target_payload()
            or any(not KEY.fullmatch(str(frozen.get(k, ''))) for k in
                   ('sourceInputSha256', 'sourceSha256', 'audioAuditSha256', 'taskId', 'reviewSha256'))
            or frozen.get('contentKey') != digest({k: v for k, v in frozen.items() if k != 'contentKey'})
            or not isinstance(frozen.get('knowledgeBrief'), dict) or not frozen['knowledgeBrief'].get('objectives')):
        fail('课件的教材、年级、教师或审核身份发生变化')
    return frozen


def validate_activity_release(build, manifest, course=None):
    from repositories.textbook_repository import TextbookRepository
    parse = TextbookRepository.parse
    frozen = validate_input(parse(build['input_json']), manifest)
    review = parse(build['review_json']) or {}
    release = review.get('release') or {}
    evidence = {k: v for k, v in review.items() if k != 'release'}
    binding = frozen['textbookBinding']
    if (build['status'] != 'published' or build['content_key'] != frozen['contentKey']
            or any(build[field] != binding[key] for field, key in
                   (('edition_id', 'editionId'), ('revision_id', 'alignmentRevisionId'),
                    ('node_id', 'nodeId'), ('part_index', 'partIndex'), ('teaching_revision', 'teachingRevision')))
            or review.get('schemaVersion') != REVIEW_SCHEMA or any(review.get(k) is not True for k in REVIEW_FLAGS)
            or not review.get('reviewer') or not review.get('basis') or not review.get('evidence')
            or review.get('sourceSha256') != frozen['sourceSha256']
            or review.get('sourceInputSha256') != frozen['sourceInputSha256']
            or review.get('audioAuditSha256') != frozen['audioAuditSha256']
            or digest(evidence) != frozen['reviewSha256']
            or release.get('schemaVersion') != RELEASE_SCHEMA or release.get('assessmentMode') != 'ungraded'
            or release.get('activityScope') != frozen['activityScope']
            or release.get('contentKey') != frozen['contentKey']
            or release.get('classroomId') != 'tbpub_' + frozen['contentKey'][:24]
            or release.get('sha256') != digest({k: v for k, v in release.items() if k != 'sha256'})
            or release.get('classroomSha256') != digest(release.get('classroom'))):
        fail()
    room = release['classroom']
    audit = release.get('audioAudit', {})
    media = release.get('media', [])
    if (room.get('id') != release['classroomId'] or room.get('stage', {}).get('id') != room['id']
            or not room.get('scenes') or questions(room) or not media
            or audit.get('sha256') != frozen['audioAuditSha256'] or audit.get('passed') is not True
            or audit.get('segments', 0) < 1 or audit.get('minSimilarityBps', 0) < 8500):
        fail()
    from content.textbook_catalog import canonical
    paths = {m['path'] for m in media}
    references = {m.group(0) for m in MEDIA.finditer(canonical(room))}
    if paths != references or any(not p.startswith('/api/classroom-media/' + room['id'] + '/') for p in paths):
        fail('课件媒体与发布清单不一致')
    if course is not None:
        content = parse(course['content_json'])
        if (course['id'] != build['course_id'] or course['version'] != build['course_version']
                or course['status'] != 'published' or course['quality_status'] != 'released' or course.get('retired_at') is not None
                or course['grade_code'] != frozen['gradeCode'] or course['subject'] != frozen['subject']
                or digest(content) != build['course_content_sha256'] or content.get('textbookBinding') != binding
                or content.get('releaseSha256') != release['sha256'] or content.get('assessmentMode') != 'ungraded'
                or content.get('questions') != []):
            fail()
    return release
