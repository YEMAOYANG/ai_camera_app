"""Exact arithmetic whitelist. No eval, guessed answer keys or model grading."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import re
from services.homework_assets import crop_region

PATTERN = re.compile(r'^\s*(\d{1,5}(?:\.\d{1,3})?)\s*([+\-−×xX*÷/])\s*(\d{1,5}(?:\.\d{1,3})?)\s*(?:=\s*(?:[?？_□（）()]*)\s*)?$')
ANSWER_PATTERN = re.compile(r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?')
OPERATIONS = {'+': ('addition','加法'), '-': ('subtraction','减法'), '−':('subtraction','减法'),
 '×':('multiplication','乘法'), 'x':('multiplication','乘法'), 'X':('multiplication','乘法'), '*':('multiplication','乘法'),
 '÷':('division','除法'), '/':('division','除法')}


def numeric(value):
    return format(value.normalize(), 'f')


def check_item(raw, *, grade, subject, policy, confirmed=False):
    prompt = str(raw.get('prompt') or '').strip()[:1000]
    answer = str(raw.get('studentAnswer') or '').strip()[:1000]
    confidence = raw.get('confidence', 0)
    if type(confidence) not in {int,float} or not 0 <= confidence <= 1:
        confidence = 0
    result = {'prompt':prompt, 'studentAnswer':answer, 'confidence':confidence,
        'region':crop_region(raw.get('region')), 'recognitionConfirmed':confirmed,
        'recognitionNeedsConfirmation':raw.get('recognitionNeedsConfirmation') is True and not confirmed,
        'annotationAmbiguous':raw.get('annotationAmbiguous') is not False,
        'type':raw.get('type') if isinstance(raw.get('type'),str) and raw.get('type') in set(policy.get('supportedTypes', ['arithmetic','unsupported'])) else 'unsupported', 'status':'pending', 'expectedAnswer':None,
        'knowledgeId':None, 'knowledgeLabel':'待确认知识点', 'hint':'请先核对题目和原作答。',
        'explanation':'', 'method':'unverified', 'picture':None, 'answerMode':None, 'voiceTexts':{}}
    # These are observations of the photographed answer, not an answer key.
    # Retain them through saved revisions and the tutor's original-source input.
    for key in ('transcriptVersion','sourceQuestionLabel','answerState','answerRegions','visualEvidence'):
        if key in raw:
            result[key]=raw[key]
    if not confirmed and result['region'] is None:
        result['recognitionNeedsConfirmation']=True
    state=raw.get('answerState')
    if not confirmed:
        # Defend direct/restored callers as well as freshly parsed responses.
        # A blank source cannot carry an inferred numeric answer into grading.
        if (state=='unclear'
                or state=='blank' and any(char not in '□?？_（）() ,，、;；\t\r\n' for char in answer)
                or state=='written' and (not answer or '□' in answer)):
            result['recognitionNeedsConfirmation']=True
    if confirmed and state is not None:
        # Existing explicit parent source corrections only edit the answer.
        # Derive its new state rather than keep the old blank classification.
        state='written' if answer and '□' not in answer else 'blank' if not answer else 'unclear'
        result['answerState']=state
    match = PATTERN.fullmatch(prompt)
    if subject != 'math' or not match or raw.get('type') != 'arithmetic':
        result['status'] = 'unsupported'
        return result
    left, operator, right = match.groups()
    a, b = Decimal(left), Decimal(right)
    if max(a,b) > policy['maxOperand'] or operator in {'/','÷'} and b == 0:
        result['status'] = 'unsupported'
        return result
    kind,label = OPERATIONS[operator]
    if kind == 'division':
        # Decimal's context rounds division and multiplication. Inverse
        # multiplication may therefore equal the original numerator even for
        # a repeating decimal (for example 2/3), so it cannot prove termination.
        denominator = (Fraction(a) / Fraction(b)).denominator
        for factor in (2, 5):
            while denominator % factor == 0:
                denominator //= factor
        if denominator != 1:
            result['status']='unsupported'
            return result
    expected = a+b if kind=='addition' else a-b if kind=='subtraction' else a*b if kind=='multiplication' else a/b
    # Negative results are outside this initial contract.
    if expected < 0:
        result['status']='unsupported'
        return result
    boundary = 'range20' if max(a,b,expected)<=20 else 'range100' if max(a,b,expected)<=100 else 'range10000' if max(a,b,expected)<=10000 else 'range100000000'
    decimal_scope = ':decimal' if any(v!=int(v) for v in (a,b,expected)) else ''
    result.update(expectedAnswer=numeric(expected), knowledgeId=f'math:{grade}:{kind}:{boundary}{decimal_scope}',knowledgeLabel=f'{boundary[5:]}以内{label}'+('（小数）' if decimal_scope else ''),
        hint=f'先看清两个数和运算符，再一步一步计算。',
        explanation=f'{numeric(a)}{operator}{numeric(b)}等于{numeric(expected)}。', method='decimal_arithmetic.v1')
    inverse = (f'可以用{numeric(expected)}减去{numeric(b)}，得到{numeric(a)}，检查结果。' if kind=='addition' else
        f'可以用{numeric(expected)}加上{numeric(b)}，得到{numeric(a)}，检查结果。' if kind=='subtraction' else
        f'可以用{numeric(expected)}除以{numeric(b)}，得到{numeric(a)}，检查结果。' if kind=='multiplication' and b else
        f'可以用{numeric(expected)}乘{numeric(b)}，得到{numeric(a)}，检查结果。' if kind=='division' else '')
    result['explanation']+=inverse
    if (result['recognitionNeedsConfirmation'] or not confirmed
            and (confidence < policy['minimumRecognitionConfidence'] or result['annotationAmbiguous'])):
        # Missing/invalid provider fields are not proof of an unanswered paper.
        # Neither low confidence nor ambiguous annotations confirm a blank.
        result['status']='pending'
    elif not answer or state=='blank':
        result['status']='blank'
    else:
        try:
            # Decimal accepts Python-only separators such as "0_5" as 5.
            # An OCR string with underscores/internal spaces is not a reliable
            # decimal answer. Decimal digits and explicit scientific notation
            # remain accepted, including numeric JSON normalized by the parser.
            if ANSWER_PATTERN.fullmatch(answer) is None:
                raise InvalidOperation()
            value = Decimal(answer)
            if not value.is_finite():
                raise InvalidOperation()
            result['status']='correct' if value == expected else 'incorrect'
        except InvalidOperation:
            result['status']='pending'
    if kind in {'addition','subtraction'} and all(v == int(v) and 0 <= v <= policy['studentQuantityMax'] for v in (a,b,expected)):
        target = int(expected)
        choices = sorted({target,max(0,target-1), min(policy['studentQuantityMax'],target+1)})
        if len(choices)<3:
            choices.append(2 if target==0 else target-2)
        # Stable shuffled order, no correct-choice style or array flag.
        choices.sort(key=lambda n:hashlib.sha256(f'{prompt}:{n}'.encode()).hexdigest())
        operation = 'add' if kind=='addition' else 'subtract'
        speech = f'这里有{int(a)}个小圆片，'+(f'再放来{int(b)}个' if operation=='add' else f'拿走{int(b)}个')+'。现在有几个？点一张数量正确的图。'
        result['answerMode']='picture_choice'
        result['picture']={'kind':'quantity_arithmetic','operation':operation,'left':int(a),'right':int(b),
            'choices':[{'id':f'n{n}','count':n} for n in choices]}
        result['hint']='可以数一数图里的小圆片。'+('把两组放在一起。' if operation=='add' else '先数还没有拿走的小圆片。')
        result['voiceTexts']={'prompt':speech,'hint':result['hint'],'explanation':result['explanation'],
            'success':'这次你找对啦！','retry':'再数一数，听听提示也可以。'}
    if grade not in {'primary_1','primary_2'}:
        result['picture']=None
        result['hint']='先看清两个数和运算符，再一步一步计算。'
        result['answerMode']='numeric'
        spoken_operator={'addition':'加','subtraction':'减','multiplication':'乘','division':'除以'}[kind]
        result['voiceTexts']={'prompt':f'{numeric(a)}{spoken_operator}{numeric(b)}等于多少？算一算，再输入答案。',
            'hint':result['hint'],'explanation':f'{numeric(a)}{spoken_operator}{numeric(b)}等于{numeric(expected)}。'+inverse,
            'success':'这次你算对啦！','retry':'再算一算，也可以先听老师的提示。'}
    return result
