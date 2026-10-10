"""Same-paper practice anchored to a server-gated reference, never mastery.

The photographed response remains immutable. Only a new student answer can
create a checked correction. A child's task completion is separately disclosed;
opening, hearing or asking about a lesson cannot create either one.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from services.homework_answer_quality import reference_for_correction, canonical_correction_answer

POLICY = json.loads((Path(__file__).parents[1] / 'content/homework_correction_policy.v1.json').read_text())


def practice_result(result):
    """Materialize presentation from the saved Tencent reference, without AI."""
    reference = reference_for_correction(result)
    if (result.get('method') != 'tencent_question.v1' or reference is None
            or reference['originalStatus'] != 'incorrect'):
        return result
    if result.get('answerMode') in {'picture_choice', 'numeric'} and result.get('voiceTexts'):
        return result
    voice = POLICY['voice']
    from services.homework_tencent_lesson import plain_reference_text
    ordinal = result.get('sourceAnswerOrdinal', 1)
    return {**result, 'status': 'incorrect', 'answerMode': 'spoken',
        'expectedAnswer': reference['expectedAnswer'], 'explanation': reference['analysis'],
        'hint': voice['hint'], 'voiceTexts': {
            'prompt': voice['prompt'].format(ordinal=ordinal),
            'hint': voice['hint'],
            'explanation': voice['explanation'].format(answer=plain_reference_text(reference['expectedAnswer']),
                analysis=plain_reference_text(reference['analysis']))[:1000],
            'success': voice['success'], 'retry': voice['retry']}}


def evaluate_response(text, reference):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= POLICY['maximumAnswerCharacters']:
        return None
    normalized = canonical_correction_answer(text)
    expected = reference.get('canonicalExpectedAnswer') or canonical_correction_answer(reference['expectedAnswer'])
    if normalized is None or expected is None:
        return None
    return {'correct': normalized == expected, 'normalizedAnswer': normalized,
        'referenceDigest': reference['digest'], 'referenceAuthority': reference['authority'],
        'scope': 'same_question_correction', 'countsForAbility': False, 'independent': None}


def correction_answer_state(correction):
    """Bind a self-report to the actual answer state, never to viewing a hint."""
    value = {key: correction.get(key) for key in ('attempts', 'correct', 'lastAnswer',
        'lastChoice', 'lastAnswerTurnId', 'updatedAt', 'referenceDigest')}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def self_reported_completion(result, correction, *, item_revision=None):
    """A child's source-bound task mark is not a new correct answer."""
    reference = reference_for_correction(result)
    saved = correction.get('selfReportedCompletion')
    if (reference is None or reference['originalStatus'] != 'incorrect'
            or type(item_revision) is not int or not isinstance(saved, dict)
            or saved.get('schemaVersion') != 'mira.homework-self-reported-completion.v1'
            or saved.get('completed') is not True or type(saved.get('completedAt')) is not int
            or saved['completedAt'] <= 0 or type(saved.get('itemRevision')) is not int
            or saved.get('itemRevision') != item_revision
            or saved.get('referenceDigest') != reference['digest']
            or saved.get('answerStateSha256') != correction_answer_state(correction)):
        return None
    return saved


def correction_view(result, correction, *, item_revision=None):
    reference = reference_for_correction(result)
    legacy_exact = (result.get('method') == 'decimal_arithmetic.v1'
        and result.get('status') in {'correct', 'incorrect'}
        and not result.get('recognitionNeedsConfirmation'))
    current = (correction.get('referenceDigest') == reference.get('digest')
        if reference else legacy_exact)
    correct = correction.get('correct') if current and type(correction.get('correct')) is bool else None
    attempts = int(correction.get('attempts', 0)) if current else 0
    self_report = self_reported_completion(result, correction, item_revision=item_revision) if correct is not True else None
    status = ('needs_review' if reference is None and not legacy_exact else 'corrected' if correct is True else
        'self_reported' if self_report else 'needs_practice' if correct is False else
        'in_progress' if correction.get('tutorViewed') else 'not_started')
    return {'status': status, 'answerEvaluationAllowed': reference is not None or legacy_exact,
        'lastAnswer': str(correction.get('lastAnswer') or correction.get('lastChoice') or '') if current else '',
        'attempts': attempts, 'correct': correct, 'updatedAt': correction.get('updatedAt') if current else None,
        'hintViewed': bool(correction.get('hintViewed')), 'explanationViewed': bool(correction.get('explanationViewed')),
        'tutorViewed': bool(correction.get('tutorViewed')), 'independent': None,
        'scope': 'same_question_correction', 'countsForAbility': False,
        'lastAnswerTurnId': correction.get('lastAnswerTurnId') if current else None,
        'correctedAt': correction.get('correctedAt') if correct else None,
        'selfReportedCompleted': self_report is not None,
        'selfReportedCompletedAt': self_report['completedAt'] if self_report else None}


def speech_digest(text):
    from services.teacher_speech import normalize_teacher_speech
    from services.learning_evidence_service import digest
    return digest(normalize_teacher_speech(text, maximum_characters=1000))


def evidence_question(row, item, result, reference):
    from services.learning_evidence_service import digest
    question = {'id': item['id'], 'version': str(item['revision']), 'subject': row['subject'],
        'gradeCode': row['grade_code'], 'knowledgeId': result['knowledgeId'],
        'knowledgeLabel': result['knowledgeLabel'], 'prompt': result['prompt'],
        'correctAnswer': reference['expectedAnswer'], 'explanation': reference['analysis'],
        'private': True, 'knowledgePoints': deepcopy(result.get('knowledgePoints', []))}
    question['fingerprint'] = digest([row['id'], item['id'], item['revision'], reference['digest']])
    return question
