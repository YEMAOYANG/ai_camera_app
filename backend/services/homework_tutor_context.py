"""Bounded grading references for teaching, never replacement paper grades."""
from __future__ import annotations

from fractions import Fraction
import re
import unicodedata

from services.homework_tencent_normalizer import grading_reference


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def grading_context(result):
    # An unverified answer key anchors the vision model to the same mistake.
    # Keep raw provider references for server comparison/audit, not this input.
    from services.homework_answer_quality import student_grading
    reference = student_grading(result)
    if reference is None:
        return None
    validation = result.get('sourceValidation')
    validation = validation if isinstance(validation, dict) else {}
    issues = validation.get('issues')
    issues = issues if isinstance(issues, list) else []
    return {
        'schemaVersion': 'mira.homework-tutor-grading-context.v1',
        'provider': 'tencent', 'referenceScope': 'answer_blank',
        'paperJudgment': reference['status'],
        'originalPaperAnswer': _text(result.get('studentAnswer'), 1000),
        'referenceAnswer': _text(reference.get('referenceAnswer'), 1000),
        'analysis': _text(reference.get('analysis'), 4000),
        'knowledgePoints': [_text(value, 200) for value in reference['knowledgePoints'][:16]],
        'questionType': _text(result.get('sourceQuestionType'), 120),
        'referenceSteps': '',
        'answerIndex': result.get('sourceAnswerOrdinal'),
        'answerCount': result.get('sourceAnswerCount'),
        'sourceValidation': {'trusted': validation.get('trusted') is True,
            'issues': [_text(value, 200) for value in issues[:32] if isinstance(value, str)]},
        'countsForAbility': False,
        'authority': 'source_reviewed_reference' if reference.get('studentQuality', {}).get('status') == 'verified' else 'withheld_unverified_reference',
        'sourceSeparation': {'printedConditions': 'must_observe_original_image',
            'handwrittenAnswer': 'student_response_only',
            'auxiliaryHandwriting': 'never_a_printed_condition', 'annotationLayerVerified': False},
    }


def _normalized(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).replace('−', '-')


def _scalar(value):
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:/\d+)?%?', value):
        return None
    try:
        return Fraction(value.rstrip('%')) / (100 if value.endswith('%') else 1)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def reference_comparison(reply, result):
    """Detect comparable differences; do not infer which source is correct.

    Neither the child's photographed answer nor a multi-blank solution can be
    used as the teacher's answer. Only a located current blank with independently
    readable source conditions is eligible for this narrow comparison.
    """
    context = grading_reference(result)
    if context is None:
        return None
    reference = context.get('referenceAnswer','')
    teacher = _text((reply.get('assessment') or {}).get('expectedAnswer'), 1000)
    value = {'status': 'unverified', 'reason': '参考答案尚需结合原题核实。'}
    if reference:
        value['referenceAnswer'] = reference
    check = reply.get('sourceCheck') or {}
    ordinal = result.get('sourceAnswerOrdinal')
    count = result.get('sourceAnswerCount')
    prompt = check.get('prompt')
    if (not reference or not teacher or reply.get('sourceConfirmationOnly') is True
            or check.get('basis') != 'original_image' or check.get('questionLocated') is not True
            or check.get('questionReadable') is not True or check.get('answerLocated') is not True
            or not isinstance(prompt,str) or not prompt.strip()
            or prompt.strip().startswith(('请看原图','请根据这页原作文','请根据原图'))
            or type(count) is not int or not 1<=count<=200
            or type(ordinal) is not int or not 1<=ordinal<=count
            or type(check.get('answerOrdinal')) is not int or check['answerOrdinal']!=ordinal):
        return value
    value['teacherAnswer'] = teacher
    left, right = _normalized(reference), _normalized(teacher)
    a, b = _scalar(left), _scalar(right)
    if left == right or a is not None and b is not None and a == b:
        value.update(status='consistent', reason='本次讲解结果与批改参考一致，仍属于老师指导。')
    elif a is not None and b is not None or left in {'+', '-', '×', '÷', '<', '>', '='} and right in {'+', '-', '×', '÷', '<', '>', '='}:
        value.update(status='conflict', reason='批改参考与本次讲解结果不同，需要结合原图核实；原成绩没有改动。')
    return value
