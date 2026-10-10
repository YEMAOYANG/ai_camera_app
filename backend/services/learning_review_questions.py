"""Project immutable, published lesson activities; never generate on a student request."""
from copy import deepcopy
import json

from content import textbook_journey as journey
from content.textbook_picture_questions import presentation
from core.errors import ApiError
from services.learning_evidence_service import digest


def knowledge_id(course, skill, activity=None):
    # Authored activity concepts are intentionally separate from coarse course
    # labels. A future reviewed mapping may align them across textbook editions.
    return ':'.join((course['subject'], course['grade_code'], activity or str(course.get('node_code') or course['id']), skill))


def authored_question(spec, course, skill, original, *, verify_audio=True):
    value = {**deepcopy(original), 'skill': skill}
    pictures = presentation(value, 'transfer') if spec.renderer == 'tiandiren' else {
        'visual': value['visual'], 'options': value['options']}
    narration = value['prompt'] + ''.join(o['value'] + '，' + o['label'] + '。' for o in value['options'])
    assets = [journey.audio_id(text) + '.wav' for text in [narration, *value['hints'], value['explanation']]]
    if verify_audio:
        manifest = json.loads((journey.ROOT / spec.audio_pack / 'manifest.json').read_text())
        for asset in assets:
            entry = manifest.get(asset, {})
            if entry.get('providerId') != 'qwen-tts' or entry.get('fallbackUsed') is not False:
                raise ValueError('Review narration has no verified teacher recording')
            journey.audio_file(asset)
    question = {'id': value['id'], 'version': spec.plan['releaseSha256'], 'renderer': spec.renderer,
        'subject': course['subject'], 'gradeCode': course['grade_code'],
        'knowledgeId': knowledge_id(course, skill, spec.plan['id']),
        'knowledgeLabel': spec.plan['skills'][skill].get('name') or spec.plan['skills'][skill]['word'],
        'courseId': course['id'], 'courseVersion': course['version'], 'courseTitle': course['title'],
        'prompt': value['prompt'], **pictures, 'correctAnswer': value['targets'][0],
        'hints': value['hints'], 'explanation': value['explanation'],
        'promptAudioAsset': assets[0], 'hintAudioAssets': assets[1:-1], 'explanationAudioAsset': assets[-1],
        'estimatedSeconds': 60, 'approved': True, 'private': False}
    question['fingerprint'] = digest({k: question[k] for k in ('knowledgeId', 'prompt', 'options', 'correctAnswer', 'visual')})
    return question


def published_question_pool(conn, child):
    from content.textbook_release import validate_release
    from repositories.textbook_repository import TextbookRepository
    repo = TextbookRepository(None)
    rows = conn.execute('''SELECT DISTINCT c.* FROM learning_sessions s
        JOIN learning_courses c ON c.id=s.course_id AND c.version=s.course_version
        WHERE s.family_id=? AND s.child_id=? AND c.grade_code=?''',
        (child['family_id'], child['id'], child['grade_code'])).fetchall()
    result, gaps = [], []
    for row in rows:
        course = dict(row)
        build = conn.execute("SELECT * FROM learning_textbook_course_builds WHERE course_id=? AND course_version=? AND status='published'",
            (course['id'], course['version'])).fetchone()
        if not build:
            gaps.append(course['title'])
            continue
        directory = repo.get_revision(conn, build['edition_id'], build['revision_id'])
        try:
            release = validate_release(build, repo.manifest(directory), course) if directory else None
            if release is None or not journey.supported(release):
                gaps.append(course['title'])
                continue
            spec = journey.definition(release=release)
            for skill in spec.skills:
                for original in spec.flow['bank'][skill]:
                    result.append(authored_question(spec, course, skill, original))
        except (ApiError, KeyError, ValueError, OSError):
            gaps.append(course['title'])
    return result, sorted(set(gaps))
