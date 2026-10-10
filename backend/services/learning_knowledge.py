"""Conservative cross-source identities, never fuzzy or model-label matching."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from services.homework_math import check_item

POLICY=json.loads((Path(__file__).parents[1]/'content/homework_analysis_policy.v1.json').read_text())
MATH_ID=re.compile(r'^math:(primary_[1-6]):(addition|subtraction|multiplication|division):(range20|range100|range10000)(:decimal)?$')
LABELS={'addition':'加法','subtraction':'减法','multiplication':'乘法','division':'除法'}


def canonical_knowledge(question, *, subject, grade):
    """Return a registered identity or None; uncertain items stay source-local.

    A structured canonical ID is an explicit curriculum mapping. Otherwise only
    a pure numeric arithmetic expression whose trusted key agrees with the exact
    homework arithmetic checker is admitted. Story text, generic course names
    and model-produced skill labels are not sufficient evidence for a mapping.
    """
    if subject!='math' or not re.fullmatch(r'primary_[1-6]',str(grade)):
        return None
    declared=MATH_ID.fullmatch(str(question.get('knowledgeId') or ''))
    declared=declared if declared and declared.group(1)==grade else None
    if question.get('type')=='numeric':
        verified=check_item({'type':'arithmetic','prompt':question.get('prompt') or question.get('question') or question.get('stem') or '',
            'studentAnswer':'','confidence':1,'annotationAmbiguous':False},grade=grade,subject=subject,policy=POLICY)
        if verified.get('method')=='decimal_arithmetic.v1':
            evaluation=question.get('evaluation') or {}
            expected=evaluation.get('expected',evaluation.get('expectedAnswer',question.get('answer',question.get('correctAnswer'))))
            try:
                actual=Decimal(str(expected))
                agrees=actual.is_finite() and actual==Decimal(verified['expectedAnswer'])
            except (InvalidOperation,ValueError,TypeError):
                agrees=False
            if not agrees or declared and declared.group(0)!=verified['knowledgeId']:
                return None
            return verified['knowledgeId'],verified['knowledgeLabel']
    if declared:
        _,operation,boundary,decimal=declared.groups()
        return declared.group(0),f'{boundary[5:]}以内{LABELS[operation]}'+('（小数）' if decimal else '')
    return None
