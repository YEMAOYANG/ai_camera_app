"""Server-owned answer authority, separate from provider confidence and grades.

Local operator reviews are family-private, source-bound adjudications. A model
asserting that it saw a diagram, or two providers agreeing, is not a review.
No read of this module dispatches a provider or rewrites a photographed answer.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata
from fractions import Fraction

from services.homework_tencent_normalizer import grading_reference, _normalized_region

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / 'data/homework/answer-reviews.v1.json'
SCHEMA = 'mira.homework-answer-reviews.v1'
QUALITY_SCHEMA = 'mira.homework-answer-quality.v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def _parsed(value):
    return json.loads(value) if isinstance(value, str) else deepcopy(value or {})


def reversal_answer(facts):
    """Compute a reversed ordinal only after the diagram facts are adjudicated.

    The formula proves reasoning, not image recognition. Handwritten ordinals
    cannot satisfy printedTargetConfirmed or supply originalOrdinal.
    """
    required = {'total', 'targetLabel', 'originalOrdinal', 'originalFront',
        'transform', 'printedTargetConfirmed', 'handwrittenAnnotationsExcluded'}
    if not isinstance(facts, dict) or set(facts) != required:
        raise ValueError('incomplete reviewed diagram facts')
    total, ordinal = facts['total'], facts['originalOrdinal']
    if (type(total) is not int or not 1 <= total <= 200 or type(ordinal) is not int
            or not 1 <= ordinal <= total or facts['originalFront'] not in {'left', 'right'}
            or facts['transform'] != 'turn_around' or facts['printedTargetConfirmed'] is not True
            or facts['handwrittenAnnotationsExcluded'] is not True
            or not isinstance(facts['targetLabel'], str) or not 1 <= len(facts['targetLabel']) <= 40):
        raise ValueError('unverified diagram fact')
    return str(total + 1 - ordinal)


@lru_cache(maxsize=4)
def _load_reviews(path, mtime, size):
    if size > 65536:
        return []
    try:
        value = json.loads(Path(path).read_text())
        if value.get('schemaVersion') != SCHEMA or not isinstance(value.get('reviews'), list):
            return []
        return value['reviews'][:100]
    except (ValueError, OSError, AttributeError):
        return []


def reviewed_result(row, item, page=None):
    """Attach a review only to its exact immutable source and item revision."""
    result = _parsed(item.get('result_json'))
    # Never trust a provider/persisted private-looking field as server authority.
    result.pop('_confirmedAnswerReview', None)
    result.pop('_confirmedGuidanceReviews', None)
    result.pop('_confirmedTencentReferenceTurns', None)
    result.pop('_referenceAnswerLayout', None)
    if not isinstance(page, dict):
        return result
    path = Path(os.environ.get('HOMEWORK_ANSWER_REVIEW_PATH') or REVIEW_PATH)
    try:
        stat = path.stat()
    except OSError:
        return result
    scope = {'submissionId': row['id'], 'submissionRevision': row['revision'],
        'itemId': item['id'], 'itemRevision': item['revision'], 'pageId': page['id'],
        'sourceImageSha256': page['content_sha256'], 'resultSha256': digest(result)}
    matches = [record for record in _load_reviews(str(path), stat.st_mtime_ns, stat.st_size)
        if isinstance(record, dict) and record.get('scope') == scope]
    if len(matches) != 1:
        return result
    record = matches[0]
    try:
        if (record.get('method') != 'operator_reviewed_order_reversal.v1'
                or record.get('reviewBasis') != 'human_confirmed_original'
                or not re.fullmatch(r'[0-9a-f]{64}', record.get('reviewId', ''))
                or record['reviewId'] != digest({key: value for key, value in record.items() if key != 'reviewId'})
                or record.get('expectedAnswer') != reversal_answer(record.get('teacherFacts'))):
            return result
        review = {key: deepcopy(record[key]) for key in ('method', 'expectedAnswer', 'teacherFacts')}
        review['digest'] = digest(record)
        review['analysis'] = _reversal_explanation(review['teacherFacts'])
        result['_confirmedAnswerReview'] = review
    except (ValueError, KeyError, TypeError):
        pass
    return result


def _reversal_explanation(facts):
    label, total, original = facts['targetLabel'], facts['total'], facts['originalOrdinal']
    front = '左' if facts['originalFront'] == 'left' else '右'
    turned = '右' if front == '左' else '左'
    answer = reversal_answer(facts)
    return (f'印刷名字确认{label}原来从{front}边数是第{original}位。'
        f'{total}位同学向后转，队伍前面从{front}边变成{turned}边。'
        f'位置没有移动，从新的前面数是{total}＋1－{original}＝{answer}，所以答案是{answer}。'
        '孩子写的辅助编号不是印刷条件，不能拿来确定人物位置。')


def _quality(status, reason, method):
    return {'schemaVersion': QUALITY_SCHEMA, 'status': status, 'reason': reason,
        'method': method, 'countsForAbility': False}


def _exact_reference(result):
    from services.homework_tutor_service import trusted_exact_reference
    reference = trusted_exact_reference(result)
    if reference is None:
        return None
    from services.homework_math import check_item
    from services.homework_service import POLICY
    exact = check_item({**result, 'type': 'arithmetic'}, grade='primary_1', subject='math',
        policy=POLICY, confirmed=True)
    if exact.get('status') in {'pending', 'unsupported'} or exact.get('expectedAnswer') is None:
        return None
    try:
        if Fraction(exact['expectedAnswer']) != Fraction(reference['expectedAnswer']):
            return None
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return exact


def _numeric_answer(value):
    """Compare scalar answers only; never interpret lists or an OCR expression."""
    if not isinstance(value, str) or len(value) > 80:
        return None
    text = unicodedata.normalize('NFKC', value).strip()
    text = re.sub(r'^第|[个位。.!！]+$', '', text).strip()
    chinese = {'零': '0', '〇': '0', '一': '1', '二': '2', '两': '2', '三': '3',
        '四': '4', '五': '5', '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
    text = chinese.get(text, text)
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/[+-]?\d+)?', text):
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def _direction_reversal(result, answer):
    hierarchy = result.get('sourceHierarchy')
    hierarchy = hierarchy if isinstance(hierarchy, dict) else {}
    raw = result.get('tencentRaw')
    raw = raw if isinstance(raw, dict) else {}
    mark = raw.get('mark')
    mark = mark if isinstance(mark, dict) else {}
    values = [result.get(key) for key in ('prompt', 'sourceTitle', 'sourcePath', 'ancestorContext', 'explanation')]
    values.extend([hierarchy.get('sourcePath'), mark.get('MarkItemTitle'), answer.get('AnswerAnalysis')])
    def texts(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str):
                    yield entry
    text = ' '.join(entry for value in values for entry in texts(value))
    return bool(re.search(r'向后转|转身|转过身|方向反转|反转方向|掉头|调头|'
        r'\bturn(?:ed|ing)?\s*(?:around|back)\b|\babout[- ]face\b|'
        r'\breverse(?:d)?\s+(?:direction|order)\b', text, re.I))


def _provider_verdict(result, reference):
    """Publish a labelled initial verdict, never an answer or score authority.

    Missing OCR stems and shared stems limit explanation, not the provider's
    answer-position verdict. Source geometry and explicit contradictions remain
    barriers, including the independently disproved turn-around interpretation.
    """
    raw = result.get('tencentRaw')
    answer = raw.get('answer') if isinstance(raw, dict) else None
    answer = answer if isinstance(answer, dict) else {}
    if _direction_reversal(result, answer):
        return None, 'direction_reversal_requires_review'
    verdict, written = answer.get('IsCorrect'), answer.get('HandwriteInfo')
    if type(verdict) is not bool:
        return None, 'provider_correctness_unknown'
    if not isinstance(written, str) or not written.strip():
        return None, 'student_answer_missing'
    if not isinstance(result.get('studentAnswer'), str) or result['studentAnswer'].strip() != written.strip():
        return None, 'student_answer_mismatch'
    validation = result.get('sourceValidation')
    validation = validation if isinstance(validation, dict) else {}
    angle = raw.get('angle') if isinstance(raw, dict) else None
    if (validation.get('angleVerified') is not True or type(angle) not in {int, float}
            or not math.isfinite(angle) or angle != 0):
        return None, 'coordinate_angle_unverified'
    if (validation.get('geometryVerified') is not True or _normalized_region(result.get('region')) is None
            or reference.get('geometryVerified') is not True
            or _normalized_region(reference.get('answerRegion')) is None):
        return None, 'answer_geometry_unverified'
    if result.get('annotationAmbiguous') is True:
        return None, 'handwriting_source_ambiguous'
    issues = validation.get('issues', [])
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        return None, 'source_validation_unknown'
    # These missing text/reference fields are not needed to show an initial
    # provider verdict and must not suppress every item on a multiblank page.
    soft_issues = {'question_text_missing', 'multiple_answer_alignment_unverified', 'reference_answer_missing'}
    if any(issue not in soft_issues for issue in issues):
        return None, 'provider_source_contradiction' if any('contradiction' in issue for issue in issues) else 'source_validation_unverified'
    supplied, expected = _numeric_answer(written), _numeric_answer(answer.get('RightAnswer'))
    if supplied is not None and expected is not None and verdict != (supplied == expected):
        return None, 'numeric_verdict_contradiction'
    return {'status': 'correct' if verdict else 'incorrect', 'source': 'tencent',
        'provisional': True, 'countsForAbility': False}, None


def canonical_correction_answer(value):
    """Compare short real answers; never infer an answer from free reasoning."""
    if not isinstance(value,str) or not value.strip() or len(value)>120:
        return None
    text=unicodedata.normalize('NFKC',value).strip()
    for _ in range(4):
        changed=re.sub(r'\\(?:boxed|text|mathrm)\{([^{}]*)\}',r'\1',text)
        changed=re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}',r'\1/\2',changed)
        if changed==text:break
        text=changed
    text=text.replace('$','').replace('\\(','').replace('\\)','')
    text=re.sub(r'\s+','',text).rstrip('。.!！?？')
    text=re.sub(r'^(?:我的答案是|答案是|答案为|我觉得是|我认为是|我选|我填|有|是)', '',text)
    numeric=re.fullmatch(r'(?:第)?([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/\d+)?|[零〇一二两三四五六七八九十百]{1,4})(?:个|棵|只|位|朵|本|条|张|颗|题)?',text)
    if numeric:
        raw=numeric[1]
        digits={'零':0,'〇':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        if raw=='一百': raw='100'
        elif re.fullmatch(r'[一二两三四五六七八九]?十[一二三四五六七八九]?',raw):
            parts=raw.split('十');raw=str(digits.get(parts[0],1)*10+digits.get(parts[1],0))
        number=_numeric_answer(raw)
        return str(number) if number is not None else None
    if not text or len(text)>40 or re.search(r'[，,；;。!?！？\n]|因为|所以|我不知道|不知道|为什么|可能|或者|答案',text):
        return None
    return text.casefold()


def attach_reference_answer_layout(conn,row,item,result,*,siblings=None):
    """Attach current owned sibling geometry, never trust a provider flag."""
    value=deepcopy(result);value.pop('_referenceAnswerLayout',None)
    hierarchy=value.get('sourceHierarchy')
    if not isinstance(hierarchy,dict) or hierarchy.get('hierarchyVerified') is not True:
        return value
    key=(hierarchy.get('receiptIndex'),hierarchy.get('markPath'))
    entries=[]
    if siblings is None:
        siblings=conn.execute('SELECT * FROM homework_items WHERE submission_id=? AND page_id=?',
            (row['id'],item['page_id'])).fetchall()
    for sibling in siblings:
        if sibling['submission_id']!=row['id'] or sibling['page_id']!=item['page_id']:continue
        raw=_parsed(sibling['result_json']);other=raw.get('sourceHierarchy')
        if (raw.get('method')!='tencent_question.v1' or not isinstance(other,dict)
                or other.get('hierarchyVerified') is not True
                or (other.get('receiptIndex'),other.get('markPath'))!=key): continue
        reference=grading_reference(raw) or {}
        entries.append({'ordinal':other.get('answerIndex'),'count':other.get('answerCount'),
            'region':reference.get('answerRegion'),'geometryVerified':reference.get('geometryVerified') is True})
    value['_referenceAnswerLayout']=sorted(entries,key=lambda entry:entry.get('ordinal') if type(entry.get('ordinal')) is int else -1)
    return value


def _reference_layout_valid(result,reference):
    count,ordinal=result.get('sourceAnswerCount'),result.get('sourceAnswerOrdinal')
    hierarchy=result.get('sourceHierarchy')
    if (type(count) is not int or not 1<=count<=200 or type(ordinal) is not int or not 1<=ordinal<=count
            or not isinstance(hierarchy,dict) or hierarchy.get('hierarchyVerified') is not True
            or hierarchy.get('scope')!='answer_blank' or hierarchy.get('answerIndex')!=ordinal
            or hierarchy.get('answerCount')!=count): return False
    if count==1: return True
    entries=result.get('_referenceAnswerLayout')
    if not isinstance(entries,list) or len(entries)!=count: return False
    indexed={entry.get('ordinal'):entry for entry in entries if isinstance(entry,dict)}
    if any(type(entry.get('ordinal')) is not int or type(entry.get('count')) is not int
            for entry in entries if isinstance(entry,dict)):return False
    if set(indexed)!=set(range(1,count+1)): return False
    regions=[]
    for index in range(1,count+1):
        entry=indexed[index];region=_normalized_region(entry.get('region'))
        if entry.get('count')!=count or entry.get('geometryVerified') is not True or region is None: return False
        regions.append(region)
    if regions[ordinal-1]!=reference.get('answerRegion'): return False
    for index,a in enumerate(regions):
        for b in regions[index+1:]:
            if min(a['x']+a['width'],b['x']+b['width'])>max(a['x'],b['x'])+1e-6 and min(a['y']+a['height'],b['y']+b['height'])>max(a['y'],b['y'])+1e-6:
                return False
    return True


def reference_for_correction(result):
    """Source-bound same-question reference, never independent mastery proof."""
    reference=grading_reference(result)
    if reference is None: return None
    review=result.get('_confirmedAnswerReview')
    exact=_exact_reference(result)
    if isinstance(review,dict):
        answer,analysis=review['expectedAnswer'],review['analysis']
        status,authority,method='verified','human_verified',review['method']
        source={'reviewDigest':review['digest']}
    elif exact is not None:
        answer,analysis=exact['expectedAnswer'],exact['explanation']
        status,authority,method='verified','exact','exact_arithmetic.v1'
        source={'raw':result.get('tencentRaw'),'hierarchy':result.get('sourceHierarchy'),
            'validation':result.get('sourceValidation'),'exact':result.get('deterministicValidation')}
    else:
        raw=result.get('tencentRaw') or {};entry=raw.get('answer') or {}
        answer,analysis=entry.get('RightAnswer'),entry.get('AnswerAnalysis')
        if (not isinstance(answer,str) or not answer.strip() or len(answer)>1000
                or not isinstance(analysis,str) or not analysis.strip() or len(analysis)>4000
                or _direction_reversal(result,entry) or result.get('annotationAmbiguous') is True
                or not _reference_layout_valid(result,reference)):
            return None
        validation=result.get('sourceValidation') or {}
        issues=validation.get('issues',[])
        if (not isinstance(issues,list) or any(issue not in {'question_text_missing','multiple_answer_alignment_unverified'} for issue in issues)
                or validation.get('provider')!='tencent' or validation.get('geometryVerified') is not True
                or validation.get('angleVerified') is not True or type(raw.get('angle')) not in {int,float}
                or not math.isfinite(raw['angle']) or raw['angle']!=0
                or _normalized_region(result.get('region')) is None or reference.get('geometryVerified') is not True
                or type(entry.get('IsCorrect')) is not bool or not isinstance(entry.get('HandwriteInfo'),str)
                or entry['HandwriteInfo'].strip()!=str(result.get('studentAnswer') or '').strip()): return None
        supplied,expected=canonical_correction_answer(entry['HandwriteInfo']),canonical_correction_answer(answer)
        if supplied is not None and expected is not None and entry['IsCorrect']!=(supplied==expected): return None
        numeric=_numeric_answer(answer)
        if numeric is not None and not _arithmetic_claims_consistent(analysis,str(numeric)): return None
        status,authority,method='provider_consistent','provider_consistent','tencent_reference.v1'
        source={'raw':raw,'hierarchy':result.get('sourceHierarchy'),'region':result.get('region'),
            'validation':validation,'layout':result.get('_referenceAnswerLayout')}
    canonical=canonical_correction_answer(answer)
    if canonical is None: return None
    written=canonical_correction_answer(str(result.get('studentAnswer') or ''))
    original='unknown' if written is None else 'correct' if written==canonical else 'incorrect'
    return {'expectedAnswer':answer,'canonicalExpectedAnswer':canonical,'analysis':analysis,
        'knowledgePoints':reference.get('knowledgePoints',[]),'method':method,'status':status,
        'authority':authority,'originalStatus':original,'countsForAbility':False,
        'digest':digest({'method':method,'source':source,'answer':answer,'analysis':analysis})}


def student_grading(result):
    """The raw Tencent reference remains in storage, outside student authority."""
    reference = grading_reference(result)
    if reference is None:
        return None
    allowed=reference_for_correction(result)
    gate={'available':allowed is not None,'method':allowed['method'] if allowed else 'unverified_provider_reference',
        'status':allowed['authority'] if allowed else 'needs_review'}
    review = result.get('_confirmedAnswerReview')
    if isinstance(review, dict):
        value = deepcopy(reference)
        answer = str(result.get('studentAnswer') or '').strip()
        value.update(status='correct' if answer == review['expectedAnswer'] else 'incorrect'
            if answer and reference.get('answerState') == 'written' else 'unknown',
            referenceAnswer=review['expectedAnswer'], analysis=review['analysis'],
            studentQuality=_quality('verified', '已按原图核对人物、朝向和手写标注，再独立计算。', review['method']))
        # A superseded provider verdict is not a second student-visible answer.
        value.pop('providerIsCorrect', None)
        value['referenceGate']=gate
        return value
    exact = _exact_reference(result)
    if exact is not None:
        value = deepcopy(reference)
        value.update(status=exact['status'] if exact['status'] in {'correct', 'incorrect'} else 'unknown',
            referenceAnswer=exact['expectedAnswer'], analysis=exact['explanation'],
            studentQuality=_quality('verified', '来源已确认的原算式已重新计算。', 'exact_arithmetic.v1'))
        value.pop('providerIsCorrect', None)
        value['referenceGate']=gate
        return value
    value = {key: deepcopy(reference[key]) for key in (
        'provider', 'source', 'answerState', 'knowledgePoints', 'geometryVerified',
        'answerRegion', 'countsForAbility', 'referenceScope') if key in reference}
    value.update(status='unknown', studentQuality=_quality('needs_review',
        '批改参考还没有独立核实，先保留原图和你的作答，不判错。', 'unverified_provider_reference'))
    value['referenceGate']=gate
    if allowed is not None:
        value.update(status=allowed['originalStatus'],referenceAnswer=allowed['expectedAnswer'],analysis=allowed['analysis'],
            knowledgePoints=deepcopy(allowed['knowledgePoints']),studentQuality=_quality('needs_review',
                '已有批改参考的来源和当前小题一致，可用于同题订正；尚非人工核实或独立掌握。',allowed['method']))
    verdict, blocked_reason = _provider_verdict(result, reference)
    if verdict is not None:
        value['providerVerdict'] = verdict
    else:
        value['providerVerdictBlockedReason'] = blocked_reason
    return value


def reviewed_lesson(result, mode='explain', message=''):
    """An approved demonstrative lesson; it is not a new independent answer."""
    review = result.get('_confirmedAnswerReview')
    if not isinstance(review, dict):
        return None
    facts = review['teacherFacts']
    total, ordinal, label = facts['total'], facts['originalOrdinal'], facts['targetLabel']
    front = '左' if facts['originalFront'] == 'left' else '右'
    turned = '右' if front == '左' else '左'
    answer = reversal_answer(facts)
    texts = [f'先看原图，从{front}边数第{ordinal}位小朋友就是{label}。下方手写的数字是作答标记，我们先不拿它来排队。',
        f'{total}位同学原来面朝{front}边，{label}从前面数是第{ordinal}位。向后转后，{turned}边变成队伍前面，人物的位置没有移动。',
        f'现在从{turned}边数，{label}在第{answer}位。也可以算：{total}加一，再减{ordinal}，等于{answer}。所以这道题的答案是{answer}。']
    if mode == 'followup':
        if message == '我还没有听懂，请用更简单的图片和短句再讲一次。':
            texts[1] = f'看着{label}，他站的位置没有动。刚才从{front}边开始数，现在换到{turned}边开始数。'
        elif message == '为什么要这样做？请看着原题再解释一下。':
            texts[0] = '向后转是转身，大家不会换位置。转身以后，队伍前面换了一边。'
        elif message == '还有别的方法吗？请用另一种方法给我讲讲这道原题。':
            texts[0] = f'还有一种方法：总共有{total}人，同一个人从两头数的序号，加起来等于{total+1}。'
            texts[1] = f'{label}原来从前面数是{ordinal}，所以从另一头数，用{total+1}减{ordinal}。'
        else:
            return None
    elif mode == 'answer':
        normalized = re.sub(r'\s+|[。！!，,]', '', message)
        if not re.fullmatch(r'(?:答案(?:是)?|我觉得(?:是)?|第)?\d+(?:位|个)?', normalized):
            return None
        supplied = re.search(r'\d+', normalized).group()
        texts[0] = ('你这次说的数字与核对后的结果相同，我们再看一遍为什么。' if supplied == answer
            else '我们先看核对后的原图，再从转身后的队伍前面数一遍。')
    elif mode != 'explain':
        return None
    region = result.get('region')
    if not isinstance(region, dict):
        region = {'x': 0.0, 'y': 0.0, 'width': 1.0, 'height': 1.0}
    value = {'teachingSource': 'operator_reviewed_lesson', 'answerReviewDigest': review['digest'],
        'teacherText': ''.join(texts),
        'sourceCheck': {'status': 'matched', 'basis': 'original_image', 'questionLocated': True,
            'questionReadable': True, 'answerLocated': True, 'studentAnswerReadable': True,
            'answerOrdinal': result.get('sourceAnswerOrdinal', 1),
            'prompt': review['analysis'], 'studentAnswer': str(result.get('studentAnswer') or ''),
            'reason': '原图信息经人工核对，手写辅助编号已排除，位置变化用确定规则计算。'},
        'steps': [{'id': f'step-{i+1}', 'text': text, 'visual': {'kind': 'paper_region',
            'region': deepcopy(region)}} for i, text in enumerate(texts)],
        'assessment': {'status': 'guidance_only', 'reason': '按已核对原图示范讲解，不作为独立掌握证据。',
            'expectedAnswer': answer, 'method': 'ai_guidance', 'countsForAbility': False, 'independent': None}}
    value['teachingQuality'] = _quality('verified', '原图事实已核对，排序结果已确定计算。', review['method'])
    return value


def guidance_candidate(value, result):
    """A correctly located source can request a blind teaching check, not score."""
    from services.homework_tutor_image_target import target_contract_valid, target_observation_matches
    contract = value.get('sourceImageContract')
    check = value.get('sourceCheck')
    assessment = value.get('assessment') or {}
    if (not target_contract_valid(contract)
            or not target_observation_matches(check, contract['targetReference'])
            or contract['targetReference'].get('ordinal') != result.get('sourceAnswerOrdinal')
            or contract['targetReference'].get('count') != result.get('sourceAnswerCount')
            or not isinstance(assessment.get('expectedAnswer'), str)
            or not assessment['expectedAnswer'].strip()
            or assessment.get('status') != 'guidance_only'
            or result.get('_confirmedAnswerReview') or _exact_reference(result) is not None
            or result.get('type') == 'writing'):
        return False
    # Tiny printed person labels plus handwritten sequence numbers caused a
    # known wrong reversal. Agreement alone cannot adjudicate that source.
    if _direction_reversal(result, {}) or _direction_reversal({'prompt': check.get('prompt')}, {}):
        return False
    answer = assessment['expectedAnswer']
    if contract['targetReference']['count'] > 1:
        if re.search(r'[;；、\n]|第.{0,6}空', answer):
            return False
        ordinal = contract['targetReference']['ordinal']
        for step in value.get('steps', []):
            for named in re.findall(r'第([一二三四五六七八九十\d]+)(?:个)?空', str(step.get('text') or '')):
                if _numeric_answer(named) != ordinal:
                    return False
    narration = ' '.join([str(value.get('teacherText') or '')] + [str(step.get('text') or '') for step in value.get('steps', [])])
    return _numeric_answer(answer) is None or _arithmetic_claims_consistent(narration, str(_numeric_answer(answer)))


def _guidance_quality(value, result):
    """Proofs are reconstructed from owned immutable server journals on reads."""
    from services.homework_source_review import primary_digest, SCHEMA as REVIEW_SCHEMA
    from services.homework_tutor_image_target import target_observation_matches
    reviews = result.get('_confirmedGuidanceReviews')
    approval = reviews.get(value.get('id')) if isinstance(reviews, dict) else None
    if (not isinstance(approval, dict) or not guidance_candidate(value, result)
            or approval.get('schemaVersion') != REVIEW_SCHEMA
            or approval.get('authority') != 'bounded_guidance_not_grade'
            or approval.get('countsForAbility') is not False
            or approval.get('primaryDigest') != primary_digest(value)
            or approval.get('sourceImageContract') != value.get('sourceImageContract')
            or not target_observation_matches(approval.get('sourceCheck'), value['sourceImageContract']['targetReference'])
            or not approval.get('printedEvidence')):
        return None
    expected = (value.get('assessment') or {}).get('expectedAnswer', '')
    independent = approval.get('expectedAnswer', '')
    a, b = _numeric_answer(expected), _numeric_answer(independent)
    agrees = a == b if a is not None and b is not None else re.sub(r'\s+', '', expected) == re.sub(r'\s+', '', independent)
    if not agrees or not independent.strip():
        return None
    return _quality('guidance', '当前小题已定位，并分别看图核对讲解；仅作教学指导，不计入原卷成绩或独立掌握。',
        'independent_image_guidance.v1')


def teaching_quality(value, result):
    """Fail closed on visual conclusions with only model self-attestation."""
    review = result.get('_confirmedAnswerReview')
    if isinstance(review, dict):
        approved = reviewed_lesson(result, value.get('mode', 'explain'), value.get('message', ''))
        if (approved is not None and value.get('teachingSource') == 'operator_reviewed_lesson'
                and value.get('answerReviewDigest') == review['digest']
                and all(value.get(key) == approved[key] for key in ('teacherText', 'steps', 'assessment'))):
            return approved['teachingQuality']
        return _quality('needs_review', '旧讲解与核对后的原题不一致，不能继续播放。', 'reviewed_source_changed')
    from services.homework_tencent_lesson import matches_lesson, grounded_followup, FOLLOWUP_SOURCE
    reference=reference_for_correction(result)
    if reference is not None and matches_lesson(value,result,reference):
        return _quality('guidance','复用当前小题来源完整且内部一致的批改解析，仅作同题教学订正。',reference['method'])
    # A free follow-up is admitted only from its owned succeeded provider call,
    # reconstructed on each read, not a provider-supplied authority flag.
    proofs=result.get('_confirmedTencentReferenceTurns')
    proof=proofs.get(value.get('id')) if isinstance(proofs,dict) else None
    if (reference is not None and value.get('teachingSource')==FOLLOWUP_SOURCE
            and value.get('referenceDigest')==reference['digest']
            and isinstance(proof,dict) and proof.get('referenceDigest')==reference['digest']
            and proof.get('replyDigest')==digest({key:value.get(key) for key in ('teacherText','steps','assessment','sourceCheck','mode','message')})
            and grounded_followup(value,result,reference)):
        return _quality('guidance','依据当前小题已有解析回答追问，不重新认定原卷答案或独立掌握。','tencent_reference_followup.v1')
    if reference is not None and reference['authority']=='provider_consistent':
        return _quality('needs_review','已保存的批改原解析可复用；旧模型重新解题的讲解不能替代当前原解析。','tencent_reference_lesson_superseded')
    guidance = _guidance_quality(value, result)
    if guidance is not None:
        return guidance
    # Exact arithmetic has an existing source-confirmed contract. Recalculate
    # rather than certify a teacher's self-reported expression or confidence.
    exact = _exact_reference(result)
    if exact is not None:
        check = value.get('sourceCheck') or {}
        source_matches = not check or (check.get('status') == 'matched'
            and re.sub(r'\s+', '', check.get('prompt', result['prompt'])) == re.sub(r'\s+', '', result['prompt']))
        narration = ' '.join([str(value.get('teacherText') or '')] + [str(step.get('text') or '') for step in value.get('steps', [])])
        if (source_matches and _arithmetic_claims_consistent(narration, exact['expectedAnswer'])
                and str((value.get('assessment') or {}).get('expectedAnswer') or '').strip() == exact['expectedAnswer']):
            return _quality('verified', '原算式来源已确认，参考结果已重新计算。', 'exact_arithmetic.v1')
    if result.get('type') == 'writing':
        check = value.get('sourceCheck') or {}
        if (check.get('basis') == 'original_image' and check.get('questionReadable') is True
                and not (value.get('assessment') or {}).get('expectedAnswer')):
            return _quality('verified', '仅对原作文提供建议，不批分或判定标准答案。', 'essay_guidance_only')
    return _quality('needs_review', '原题图意和作答还没有可靠核实，不能用批改参考或手写编号给出结论。',
        'visual_source_unverified')


def _arithmetic_claims_consistent(text, expected):
    """Reject explicit false equalities in narration, not just its JSON answer."""
    number = r'\d+(?:\.\d+)?'
    text = text.translate(str.maketrans('零〇一二三四五六七八九', '00123456789'))
    text = text.replace('加', '+').replace('减', '-').replace('乘以', '*').replace('乘', '*')
    text = text.replace('除以', '/').replace('等于', '=').replace('×', '*').replace('÷', '/')
    for match in re.finditer(rf'({number})\s*([+*/-])\s*({number})\s*=\s*({number})', text):
        a, op, b, stated = match.groups(); a, b, stated = Fraction(a), Fraction(b), Fraction(stated)
        if op == '/' and not b:
            return False
        actual = a+b if op == '+' else a-b if op == '-' else a*b if op == '*' else a/b
        if actual != stated:
            return False
    for match in re.finditer(rf'(?:正确答案|答案|结果)\s*(?:是|为|=)\s*({number})', text):
        if Fraction(match[1]) != Fraction(expected):
            return False
    return True
