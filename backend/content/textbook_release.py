"""Immutable, pre-generated textbook releases. No model calls on delivery."""
from copy import deepcopy
import hashlib
import re

from content.textbook_catalog import canonical, digest, lesson_by_id
from core.errors import ApiError

INPUT_SCHEMA = 'mira.textbook.saved-classroom-input.v1'
RELEASE_SCHEMA = 'mira.textbook.saved-classroom-release.v1'
KEY = re.compile(r'^[a-f0-9]{64}$')
MEDIA = re.compile(r'(?:https?://[^/\s"\x27<>\\]+)?/api/classroom-media/([A-Za-z0-9_-]+)/((?:audio|media)/[A-Za-z0-9_.-]+)')


def fail(message='这节课的发布资料不完整，请稍后再来'):
    raise ApiError('textbook_release_unavailable', message, 409)


def questions(classroom):
    return [q for s in classroom['scenes'] if s['type'] == 'quiz' for q in s['content']['questions']]


def check_questions(classroom):
    items = questions(classroom)
    if not items or len(items) > 30 or len({q['id'] for q in items}) != len(items):
        fail('题目数量或身份无效')
    for q in items:
        options = q.get('options', [])
        if (q.get('type') != 'single' or not 2 <= len(options) <= 6
                or len({o.get('value') for o in options}) != len(options)
                or not isinstance(q.get('answer'), list) or len(q['answer']) != 1
                or q['answer'][0] not in {o.get('value') for o in options}
                or not q.get('questionAudioUrl') or not q.get('analysis')
                or type(q.get('points', 1)) is not int or not 1 <= q.get('points', 1) <= 100):
            fail('每道题需要唯一答案、解析和已生成的听题音频')
    return items


def validate_release(build, manifest, course=None):
    """Validate exact hashes and the separate saved-artifact publication contract.

    A release review covers one lesson, not every pending lesson in its book.
    Historical generator/whole-catalog releases retain their existing gates.
    """
    from repositories.textbook_repository import TextbookRepository
    parse = TextbookRepository.parse
    frozen, review = parse(build['input_json']), parse(build['review_json'])
    from content.textbook_batch_release import INPUT_SCHEMA as ACTIVITY_INPUT, validate_activity_release
    if isinstance(frozen, dict) and frozen.get('schemaVersion') == ACTIVITY_INPUT:
        return validate_activity_release(build, manifest, course)
    if not isinstance(frozen, dict) or frozen.get('schemaVersion') != INPUT_SCHEMA:
        return None
    release = (review or {}).get('release')
    if not isinstance(release, dict) or release.get('schemaVersion') != RELEASE_SCHEMA:
        fail()
    receipt = {k: v for k, v in release.items() if k != 'sha256'}
    binding = frozen.get('textbookBinding', {})
    if (build['status'] != 'published' or digest(receipt) != release.get('sha256')
            or digest({k: v for k, v in frozen.items() if k != 'contentKey'}) != build['content_key']
            or frozen.get('contentKey') != build['content_key']
            or binding != {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'alignmentManifestSha256': digest(manifest), 'nodeId': build['node_id'], 'partIndex': 1,
                'teachingRevision': build['teaching_revision']}
            or release.get('contentKey') != build['content_key']
            or release.get('classroomId') != 'tbpub_' + build['content_key'][:24]
            or digest(release.get('classroom')) != release.get('classroomSha256')
            or review.get('alignmentConfirmed') is not True or review.get('originalExpressionConfirmed') is not True
            or review.get('sourceUsageConfirmed') is not True or review.get('publicationAuthorized') is not True
            or not review.get('reviewer') or not review.get('basis')):
        fail()
    _, node = lesson_by_id(manifest, build['node_id'])
    if frozen.get('knowledgeBrief') != node['brief'] or frozen.get('gradeCode') != manifest['gradeCode']:
        fail()
    if course is not None and (course['status'] != 'published' or course['quality_status'] != 'released'
            or course.get('retired_at') is not None or course['id'] != build['course_id']
            or course['version'] != build['course_version'] or digest(parse(course['content_json'])) != build['course_content_sha256']):
        fail()
    if (not release.get('media') or not release.get('audioAudit', {}).get('passed')
            or release['audioAudit'].get('segments') != sum(a.get('type') == 'speech' for s in release['classroom']['scenes'] for a in s.get('actions', []))):
        fail()
    return release


def public_classroom(release):
    """Answers/teacher prompts remain on the backend; playback is OpenMAIC."""
    content = deepcopy(release['classroom'])
    allowed_stage = {'id', 'name', 'style', 'createdAt', 'updatedAt', 'agentIds'}
    content['stage'] = {k: v for k, v in content['stage'].items() if k in allowed_stage}
    content['stage']['fixedTextbook'] = True
    if release.get('assessmentMode') == 'ungraded':
        content['stage']['miraUngradedActivity'] = True
    for scene in content['scenes']:
        if scene['type'] == 'quiz':
            scene['content']['questions'] = [{k: v for k, v in q.items()
                if k in {'id', 'type', 'question', 'options', 'points', 'questionAudioUrl'}}
                for q in scene['content']['questions']]
        elif scene['type'] == 'interactive':
            html = scene['content'].get('html', '')
            # The reviewed role game queues named narration clips. Resolve its
            # original dynamic filename expression to the audited speech IDs,
            # so the gateway can embed the exact published assets for srcdoc.
            queued_audio = r"player\.src='/api/classroom-media/[A-Za-z0-9_-]+/audio/'\+queue\.shift\(\)\+'\.wav'"
            if re.search(queued_audio, html):
                aliases = {a['id'][7:]: a['audioUrl'] for a in scene.get('actions', [])
                           if a.get('type') == 'speech' and a.get('id', '').startswith('review_')
                           and isinstance(a.get('audioUrl'), str)}
                required = {'speaker-teal', 'speaker-coral', 'cue-me', 'cue-you', 'cue-he'}
                allowed = {m['path'] for m in release['media'] if m.get('mimeType', '').startswith('audio/')}
                if not required.issubset(aliases) or any(aliases[key] not in allowed for key in required):
                    fail('互动听题素材不完整')
                sources = canonical({key: aliases[key] for key in sorted(required)})
                scene['content']['html'] = re.sub(queued_audio, lambda _: f'player.src=({sources})[queue.shift()]', html)
    return content


def grade_answers(release, answers):
    items = check_questions(release['classroom'])
    if not isinstance(answers, dict) or set(answers) != {q['id'] for q in items}:
        raise ApiError('textbook_answers_invalid', '请完成每道题再提交', 400)
    results = []
    for q in items:
        answer = answers[q['id']]
        if not isinstance(answer, str) or answer not in {o['value'] for o in q['options']}:
            raise ApiError('textbook_answers_invalid', '选项无效，请重新选择', 400)
        correct = answer == q['answer'][0]
        results.append({'questionId': q['id'], 'response': answer, 'correct': correct,
            'score': q.get('points', 1) if correct else 0, 'maxScore': q.get('points', 1),
            'explanation': q['analysis'], 'correctAnswer': q['answer'][0]})
    return {'results': results, 'score': sum(r['score'] for r in results),
            'maxScore': sum(r['maxScore'] for r in results),
            'correctCount': sum(r['correct'] for r in results), 'totalQuestions': len(results)}
