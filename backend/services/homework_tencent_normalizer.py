"""Question-level Tencent evidence without fabricated OCR confidence or scores."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from core.errors import ApiError
from services.homework_math import check_item, PATTERN

SCHEMA = 'mira.homework-tencent-normalized.v1'
NORMALIZER_VERSION = 'mira.homework-tencent-normalizer.v3'
MAX_ITEMS_PER_PAGE = json.loads((Path(__file__).parents[1] / 'content/homework_tencent_grading_policy.v1.json').read_text())['maxItemsPerPage']


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def _angle_verified(value):
    # Tencent's rotated output coordinate system is not assumed to match our
    # transformed input. Only explicit zero guarantees that mapping here.
    return type(value) in {int, float} and math.isfinite(value) and value == 0


def _region(position, width, height, *, angle_verified):
    if (not angle_verified or type(width) is not int or type(height) is not int or width <= 0 or height <= 0
            or not isinstance(position, list) or len(position) != 8 or any(type(v) is not int for v in position)):
        return None
    xs, ys = position[::2], position[1::2]
    if min(xs) < 0 or min(ys) < 0 or max(xs) > width or max(ys) > height or max(xs) <= min(xs) or max(ys) <= min(ys):
        return None
    return {'x': min(xs) / width, 'y': min(ys) / height,
        'width': (max(xs) - min(xs)) / width, 'height': (max(ys) - min(ys)) / height}


def _response(raw):
    response = raw.get('Response') if isinstance(raw, dict) else None
    if not isinstance(response, dict):
        raise ApiError('homework_recognition_invalid_schema', '已保存的腾讯回执缺少结果结构', 409)
    return response


def _base(prompt, answer, region, *, method, type_, page_id):
    return {'prompt': prompt, 'studentAnswer': answer, 'expectedAnswer': None, 'confidence': None,
        'region': region, 'recognitionConfirmed': False, 'recognitionNeedsConfirmation': False,
        'annotationAmbiguous': False, 'type': type_, 'status': 'pending', 'knowledgeId': None,
        'knowledgeLabel': '待确认知识点', 'hint': '', 'explanation': '', 'method': method,
        'picture': None, 'answerMode': None, 'voiceTexts': {}, 'pageId': page_id,
        'answerState': 'written' if answer else 'blank'}


def _polygon(position):
    if not isinstance(position, dict):
        return None
    points = [position.get(name) for name in ('LeftTop', 'RightTop', 'RightBottom', 'LeftBottom')]
    if any(not isinstance(point, dict) for point in points):
        return None
    return [coordinate for point in points for coordinate in (point.get('X'), point.get('Y'))]


def _question_sources(submit_receipts, width, height):
    candidates = []
    frame_verified = False
    def visit(entries):
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            elements = entry.get('Question')
            if isinstance(elements, list):
                # Only Question text belongs to the source prompt. Answer and
                # Parse are deliberately never copied into it.
                valid = [e for e in elements if isinstance(e, dict)]
                text = '\n'.join(_text(e.get('Text')) for e in valid if _text(e.get('Text')))
                page_ok = all(type(e.get('PageIndex', 1)) is int and e.get('PageIndex', 1) == 1 for e in valid)
                coords, indexes = entry.get('Coord'), entry.get('CoordPageIndex') or []
                if (_leaf_question_text(text, []) and page_ok and isinstance(coords, list) and len(coords) == 1
                        and isinstance(indexes, list) and indexes in ([], [1])):
                    region = _region(_polygon(coords[0]), width, height, angle_verified=True)
                    if region:
                        candidates.append({'prompt': text, 'region': region, 'raw': entry})
                for element in valid:
                    visit(element.get('ResultList'))
    for raw in submit_receipts or []:
        info = _response(raw).get('QuestionInfo')
        info = [info] if isinstance(info, dict) else info
        if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
            continue
        source = info[0]
        if (not _angle_verified(source.get('Angle')) or source.get('Width') != width or source.get('Height') != height
                or source.get('OrgWidth') != width or source.get('OrgHeight') != height):
            continue
        frame_verified = True
        visit(source.get('ResultList'))
    return candidates, frame_verified


def _matching_source(candidates, region):
    if region is None:
        return None
    # There is no official linking identifier. Require a unique, almost exact
    # spatial match, never array order or a nearest-neighbour guess.
    matches = []
    for candidate in candidates:
        other = candidate['region']
        left, top = max(region['x'], other['x']), max(region['y'], other['y'])
        right = min(region['x'] + region['width'], other['x'] + other['width'])
        bottom = min(region['y'] + region['height'], other['y'] + other['height'])
        intersection = max(0, right-left) * max(0, bottom-top)
        union = region['width']*region['height'] + other['width']*other['height'] - intersection
        if union > 0 and intersection/union >= .95:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _leaf_question_text(title, children):
    if children or not title or len(title) > 4000:
        return False
    if PATTERN.fullmatch(title):
        return True
    content = re.sub(r'^\s*(?:第[一二三四五六七八九十\d]+题|[（(]?\d{1,3}[.．、）)])\s*', '', title)
    if PATTERN.fullmatch(content):
        return True
    if len(content) < 4 or content in {'选择题', '填空题', '计算题', '应用题', '判断题', '阅读理解', '作文'}:
        return False
    return bool(re.search(r'[?？]|(?:请|选择|填写|圈出|找出|写出|比较|连线|判断|组词|造句|计算|回答|填入|补全|改写)|\b(?:what|which|how|where|when|why|choose|fill|calculate|write|match|complete|is|are)\b', content, re.I))


def _question_label(title):
    if PATTERN.fullmatch(title):
        return None
    match = re.match(r'^\s*(第[一二三四五六七八九十\d]+题|[（(]?\d{1,3}[.．、）)])', title)
    return match.group(1)[:120] if match else None


def _union(first, second):
    if first is None or second is None:
        return first
    x, y = min(first['x'], second['x']), min(first['y'], second['y'])
    return {k: round(v, 6) for k, v in {'x': x, 'y': y,
        'width': max(first['x']+first['width'], second['x']+second['width'])-x,
        'height': max(first['y']+first['height'], second['y']+second['height'])-y}.items()}


def _normalized_region(value):
    if not isinstance(value, dict):
        return None
    numbers = [value.get(key) for key in ('x', 'y', 'width', 'height')]
    if any(type(v) not in {int, float} or not math.isfinite(v) for v in numbers):
        return None
    x, y, width, height = numbers
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.000001 or y + height > 1.000001:
        return None
    return dict(zip(('x', 'y', 'width', 'height'), numbers))


def question_source_hierarchy(result):
    """Read old saved items without inventing a provider tree path or OCR stem."""
    if result.get('method') != 'tencent_question.v1':
        return None
    saved = result.get('sourceHierarchy')
    if isinstance(saved, dict):
        return saved
    ancestors = result.get('ancestorContext')
    titles = [_text(v) for v in ancestors if _text(v)] if isinstance(ancestors, list) else []
    title = _text(result.get('sourceTitle'))
    if title:
        titles.append(title)
    ordinal, count = result.get('sourceAnswerOrdinal'), result.get('sourceAnswerCount')
    valid_answer = type(ordinal) is int and type(count) is int and 1 <= ordinal <= count
    validation = result.get('sourceValidation')
    validation = validation if isinstance(validation, dict) else {}
    return {'schemaVersion': 'mira.homework-source-hierarchy.v1', 'sourcePath': titles,
        'receiptIndex': None, 'markPath': [], 'hierarchyVerified': False,
        'answerIndex': ordinal if valid_answer else None, 'answerCount': count if valid_answer else 0,
        'scope': 'answer_blank', 'questionTextScope': 'shared_question' if valid_answer and count > 1
            else 'single_answer' if validation.get('questionTextPresent') is True else 'image_only'}


def grading_reference(result):
    """A provider verdict is original-paper guidance, not independent mastery.

    This projection also works for v2 items already stored in the database.
    References are taken from the saved AnswerInfo, never from a tutor reply or
    a calculated replacement for the photographed question.
    """
    if result.get('method') != 'tencent_question.v1':
        return None
    raw = result.get('tencentRaw')
    answer = raw.get('answer') if isinstance(raw, dict) else None
    answer = answer if isinstance(answer, dict) else {}
    assessment = result.get('providerAssessment')
    assessment = assessment if isinstance(assessment, dict) else {}
    verdict = answer.get('IsCorrect', assessment.get('isCorrect'))
    validation = result.get('sourceValidation')
    validation = validation if isinstance(validation, dict) else {}
    # A malformed raw verdict must not fall back to a more permissive copy.
    original_answer = answer.get('HandwriteInfo', result.get('studentAnswer'))
    answer_state = ('written' if _text(original_answer) else 'blank') if isinstance(original_answer, str) else 'unclear'
    status = ('correct' if verdict is True else 'incorrect' if verdict is False else 'unknown') if answer_state=='written' else 'unknown'
    points = answer.get('KnowledgePoints', result.get('knowledgePoints', []))
    points = list(dict.fromkeys(_text(p) for p in points if _text(p))) if isinstance(points, list) else []
    regions = result.get('answerRegions')
    region = _normalized_region(assessment.get('answerRegion'))
    if region is None and isinstance(regions, list) and regions:
        region = _normalized_region(regions[0])
    geometry_verified = validation.get('angleVerified') is True and region is not None
    value = {'provider': 'tencent', 'source': 'tencent', 'status': status,
        'providerIsCorrect': verdict if type(verdict) is bool else None, 'answerState': answer_state,
        'knowledgePoints': points, 'geometryVerified': geometry_verified,
        'sourceValidationTrusted': validation.get('trusted') is True,
        'countsForAbility': False, 'referenceScope': 'answer_blank'}
    if geometry_verified:
        value['answerRegion'] = region
    reference = _text(answer.get('RightAnswer', result.get('expectedAnswer')))
    analysis = _text(answer.get('AnswerAnalysis', result.get('explanation')))
    if reference:
        value['referenceAnswer'] = reference
    if analysis:
        value['analysis'] = analysis
    return value


def normalize_question_page(receipts, *, page_id, width, height, grade, subject, policy, submit_receipts=None, maximum_items=MAX_ITEMS_PER_PAGE):
    if type(maximum_items) is not int or not 1 <= maximum_items <= MAX_ITEMS_PER_PAGE:
        raise ValueError('bounded Tencent item limit required')
    items = []
    sources, source_frame_verified = _question_sources(submit_receipts, width, height)
    def walk(mark, angle, ancestors=(), *, receipt_index, mark_path):
        if not isinstance(mark, dict):
            raise ApiError('homework_recognition_invalid_schema', '腾讯题目结果结构无效', 409)
        title = _text(mark.get('MarkItemTitle'))
        children = mark.get('MarkInfos') or []
        source_region = _region(mark.get('QuestionPositions'), width, height,
            angle_verified=_angle_verified(angle) and source_frame_verified)
        source = _matching_source(sources, source_region)
        leaf_text = _leaf_question_text(title, children)
        question_text_present = source is not None or leaf_text
        prompt = source['prompt'] if source else title if leaf_text else f'请看原图中的这道题{("（" + title[:120] + "）") if title else ""}。'
        printed_label = _question_label(title)
        if printed_label and prompt.startswith(printed_label):
            body = prompt[len(printed_label):].strip()
            if PATTERN.fullmatch(body):
                prompt = body
        answers = mark.get('AnswerInfos')
        if answers is None:
            answers = []
        if not isinstance(answers, list) or not isinstance(children, list):
            raise ApiError('homework_recognition_invalid_schema', '腾讯题目和作答列表无效', 409)
        for answer_index, answer in enumerate(answers):
            if not isinstance(answer, dict):
                raise ApiError('homework_recognition_invalid_schema', '腾讯作答结构无效', 409)
            student = _text(answer.get('HandwriteInfo'))
            right = _text(answer.get('RightAnswer'))
            aligned = _angle_verified(angle) and source_frame_verified
            region = _region(mark.get('QuestionPositions'), width, height, angle_verified=aligned)
            answer_region = _region(answer.get('HandwriteInfoPositions'), width, height, angle_verified=aligned)
            region = _union(region, answer_region)
            result = _base(prompt, student, region, method='tencent_question.v1', type_='other', page_id=page_id)
            if subject == 'math':
                result['type'] = 'arithmetic' if mark.get('QuestionType') in {'口算题', '计算题', 'arithmetic'} else 'word_problem'
            elif subject in {'chinese', 'english'}:
                result['type'] = 'language'
            result.update(expectedAnswer=right or None, explanation=_text(answer.get('AnswerAnalysis')),
                sourceQuestionLabel=_question_label(title), sourceTitle=title, ancestorContext=list(ancestors), answerRegions=[answer_region] if answer_region else [],
                # The complete receipt lives in its private journal. Do not
                # duplicate every AnswerInfo and nested question in each item.
                tencentRaw={'mark': {k: mark[k] for k in ('MarkItemTitle', 'QuestionType', 'QuestionPositions', 'RightAnswer') if k in mark},
                    'answer': answer, 'angle': angle, 'sourceQuestion': source['raw'] if source else None},
                sourceAnswerOrdinal=answer_index+1, sourceAnswerCount=len(answers),
                referenceSteps=_text(mark.get('RightAnswer')) or None,
                sourceQuestionType=_text(mark.get('QuestionType')) or None)
            result['providerAssessment'] = {'provider': 'tencent', 'provisional': True,
                'isCorrect': answer.get('IsCorrect') if type(answer.get('IsCorrect')) is bool else None,
                'answerRegion': answer_region, 'countsForAbility': False}
            points = answer.get('KnowledgePoints')
            points = list(dict.fromkeys(_text(p) for p in points if _text(p))) if isinstance(points, list) else []
            result['knowledgePoints'] = points
            result['sourceHierarchy'] = {'schemaVersion': 'mira.homework-source-hierarchy.v1',
                'receiptIndex': receipt_index, 'markPath': list(mark_path), 'hierarchyVerified': True,
                'sourcePath': [*ancestors, title] if title else list(ancestors),
                'answerIndex': answer_index+1, 'answerCount': len(answers), 'scope': 'answer_blank',
                'questionTextScope': 'shared_question' if len(answers)>1 else 'single_answer' if question_text_present else 'image_only'}
            result['knowledgeId'] = f'{subject}:{grade}:tencent-question:' + _hash([prompt, points])[:24]
            result['knowledgeLabel'] = '、'.join(points) or '待确认知识点'
            validation = {'provider': 'tencent', 'scope': 'paper_answer_unknown_help',
                'strictIsCorrect': type(answer.get('IsCorrect')) is bool,
                'studentAnswerPresent': isinstance(answer.get('HandwriteInfo'), str),
                'referenceAnswerPresent': isinstance(answer.get('RightAnswer'), str) and bool(right),
                'geometryVerified': region is not None, 'angleVerified': aligned, 'questionTextPresent': question_text_present,
                'questionTextSource': 'submit_question_info' if source else 'mark_item_title' if leaf_text else 'original_image_required', 'issues': []}
            if not question_text_present:
                validation['issues'].append('question_text_missing')
            if len(answers) > 1:
                validation['issues'].append('multiple_answer_alignment_unverified')
            if not validation['strictIsCorrect']:
                validation['issues'].append('correctness_unknown')
            if not validation['studentAnswerPresent']:
                validation['issues'].append('student_answer_missing')
            if not validation['referenceAnswerPresent']:
                validation['issues'].append('reference_answer_missing')
            if student and answer_region is None:
                validation['issues'].append('answer_region_unverified')
            if not aligned:
                validation['issues'].append('coordinate_angle_unverified')
            if region is None:
                validation['issues'].append('question_region_unverified')
            if subject not in {'math', 'chinese', 'english'}:
                validation['issues'].append('subject_not_validated')
            # Use the existing whitelist only as an independent calculation.
            # It does not supply invented recognition confidence or source proof.
            # A shared multiblank stem does not identify the calculation for an
            # individual AnswerInfo, even if the full stem looks arithmetic.
            exact = check_item({'prompt': prompt if len(answers)==1 else '', 'studentAnswer': student, 'type': 'arithmetic',
                'annotationAmbiguous': False, 'region': region}, grade=grade, subject=subject, policy=policy, confirmed=True)
            if exact.get('method') == 'decimal_arithmetic.v1':
                result['deterministicValidation'] = {'method': exact['method'], 'status': exact['status'],
                    'expectedAnswer': exact['expectedAnswer']}
                result.update(type='arithmetic', knowledgeId=exact['knowledgeId'], knowledgeLabel=exact['knowledgeLabel'])
                if validation['strictIsCorrect'] and exact['status'] in {'correct', 'incorrect'} and answer['IsCorrect'] != (exact['status'] == 'correct'):
                    validation['issues'].append('provider_arithmetic_contradiction')
                if right and exact['expectedAnswer'] != right:
                    # Numerically equivalent formatting is allowed.
                    from decimal import Decimal, InvalidOperation
                    try:
                        reference_matches = Decimal(right) == Decimal(exact['expectedAnswer'])
                    except InvalidOperation:
                        reference_matches = False
                    if not reference_matches:
                        validation['issues'].append('reference_arithmetic_contradiction')
            validation['trusted'] = not validation['issues']
            result['sourceValidation'] = validation
            result['recognitionNeedsConfirmation'] = not validation['trusted']
            if validation['trusted']:
                result['status'] = 'blank' if not student else 'correct' if answer['IsCorrect'] else 'incorrect'
                if exact.get('method') == 'decimal_arithmetic.v1' and exact['status'] in {'correct','incorrect','blank'}:
                    # Existing exact arithmetic supplies materialized, picture
                    # supported correction/review content. Its source confidence
                    # and parent-confirmed flags never replace Tencent evidence.
                    for field in ('picture','answerMode','voiceTexts','hint','explanation'):
                        result[field]=exact[field]
                    result['expectedAnswer']=exact['expectedAnswer']
                    result['correctionMethod']='decimal_arithmetic.v1'
            elif not validation['studentAnswerPresent']:
                result['answerState'] = 'unclear'
            result['gradingReference'] = grading_reference(result)
            items.append(result)
            if len(items) > maximum_items:
                raise ApiError('homework_recognition_over_limit', '腾讯返回题数超过单页安全上限，已保留原始回执', 409)
        # A cut question without any answer entry is unknown, not a wrong answer.
        if not answers and not children:
            region = _region(mark.get('QuestionPositions'), width, height, angle_verified=_angle_verified(angle))
            value = _base(prompt, '', region, method='tencent_question.v1', type_='other', page_id=page_id)
            value.update(answerState='unclear', recognitionNeedsConfirmation=True, sourceQuestionLabel=_question_label(title), sourceTitle=title, ancestorContext=list(ancestors),
                tencentRaw={'mark': {k: mark[k] for k in ('MarkItemTitle', 'QuestionType', 'QuestionPositions', 'RightAnswer') if k in mark}, 'angle': angle}, knowledgePoints=[],
                knowledgeId=f'{subject}:{grade}:tencent-question:' + _hash(prompt)[:24],
                sourceValidation={'provider': 'tencent', 'scope': 'paper_answer_unknown_help', 'trusted': False,
                    'strictIsCorrect': False, 'studentAnswerPresent': False, 'referenceAnswerPresent': False,
                    'geometryVerified': region is not None, 'angleVerified': _angle_verified(angle), 'issues': ['answer_entry_missing']})
            value['sourceHierarchy'] = {'schemaVersion': 'mira.homework-source-hierarchy.v1',
                'receiptIndex': receipt_index, 'markPath': list(mark_path), 'hierarchyVerified': True,
                'sourcePath': [*ancestors, title] if title else list(ancestors),
                'answerIndex': None, 'answerCount': 0, 'scope': 'answer_blank', 'questionTextScope': 'image_only'}
            value['gradingReference'] = grading_reference(value)
            items.append(value)
            if len(items) > maximum_items:
                raise ApiError('homework_recognition_over_limit', '单页题目超过处理上限，已保留原始回执', 409)
        for child_index, child in enumerate(children,1):
            walk(child, angle, (*ancestors, title) if title else ancestors,
                receipt_index=receipt_index, mark_path=(*mark_path,child_index))
    for receipt_index, raw in enumerate(receipts,1):
        response = _response(raw)
        marks = response.get('MarkInfos')
        if not isinstance(marks, list):
            raise ApiError('homework_recognition_invalid_schema', '腾讯已完成结果缺少题目列表', 409)
        for mark_index, mark in enumerate(marks,1):
            walk(mark, response.get('Angle'), receipt_index=receipt_index, mark_path=(mark_index,))
    if len(items) > maximum_items:
        raise ApiError('homework_recognition_over_limit', '单页题目超过处理上限', 409)
    return {'schemaVersion': SCHEMA, 'normalizerVersion': NORMALIZER_VERSION, 'analysisKind': 'questions', 'pageReadable': bool(items), 'items': items}


def normalize_essay_page(receipts, *, page_id, width, height, grade, subject, policy, submit_receipts=None):
    if subject not in {'chinese', 'english'}:
        raise ApiError('homework_essay_subject_unsupported', '作文点评仅支持语文和英语', 400)
    suggestions = []
    for job_index, raw in enumerate(receipts):
        response = _response(raw)
        values = response.get('SentenceSuggests')
        if not isinstance(values, list):
            raise ApiError('homework_recognition_invalid_schema', '作文点评回执缺少建议列表', 409)
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                raise ApiError('homework_recognition_invalid_schema', '作文建议结构无效', 409)
            suggestion = {'id': f'{page_id}:{job_index}:{value.get("ID", index)}', 'type': _text(value.get('Type')),
                'subType': _text(value.get('SubType')), 'origin': _text(value.get('Origin')),
                'replace': _text(value.get('Replace')), 'message': _text(value.get('Message')), 'pageId': page_id}
            positions = value.get('Positions')
            regions = [_region(v.get('Position'), width, height, angle_verified=_angle_verified(response.get('Angle')))
                for v in positions if isinstance(v, dict)] if isinstance(positions, list) else []
            regions = [region for region in regions if region]
            if regions:
                suggestion['region'] = regions[0]
                suggestion['regions'] = regions
            suggestions.append(suggestion)
    result = _base('请根据这页原作文和已保存的点评建议，带孩子理解并改进表达。建议中的原句片段不是完整作文。', '', None,
        method='tencent_essay.v1', type_='writing', page_id=page_id)
    result.update(status='unsupported', answerState='unclear', essaySuggestions=suggestions, countsForAbility=False,
        sourceValidation={'provider': 'tencent', 'scope': 'guidance_only', 'trusted': False, 'issues': []},
        tencentRaw=receipts)
    return {'schemaVersion': SCHEMA, 'normalizerVersion': NORMALIZER_VERSION, 'analysisKind': 'essay', 'pageReadable': True, 'items': [result]}
