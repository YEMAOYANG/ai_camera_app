"""Validate paper and derived private-review evidence on read, without writes."""
import json
from fractions import Fraction

from services.homework_answer_quality import (reviewed_result, reference_for_correction,
    canonical_correction_answer, attach_reference_answer_layout)


def _owned_source(conn, key, cache):
    if key not in cache:
        source = conn.execute('''SELECT i.*,s.family_id,s.child_id,s.subject,s.grade_code,
            s.revision AS submission_revision,p.content_sha256 FROM homework_items i
            JOIN homework_submissions s ON s.id=i.submission_id
            JOIN homework_pages p ON p.id=i.page_id AND p.submission_id=s.id
            WHERE s.family_id=? AND s.child_id=? AND s.id=? AND i.id=? AND s.deleted_at IS NULL''', key).fetchone()
        if source is None:
            cache[key] = None
        else:
            row = {'id': source['submission_id'], 'revision': source['submission_revision']}
            result = reviewed_result(row, source, {'id':source['page_id'], 'content_sha256':source['content_sha256']})
            result = attach_reference_answer_layout(conn,row,source,result)
            cache[key] = (source, reference_for_correction(result), result)
    return cache[key]


def _quantity_review(question):
    return (question.get('renderer') == 'quantity_arithmetic'
        and isinstance(question.get('visual'),dict)
        and question['visual'].get('kind') == 'quantity_arithmetic')


def _review_answer(question, answer):
    """Only an explicit picture option supplies the meaning of its value ID."""
    if _quantity_review(question):
        options = question.get('options')
        if not isinstance(options,list):
            return None
        matches = [option for option in options if isinstance(option,dict) and option.get('value') == answer]
        if matches:
            if len(matches) != 1 or not isinstance(matches[0].get('picture'),dict):
                return None
            count = matches[0]['picture'].get('count')
            return str(count) if type(count) is int and count >= 0 else None
        # The earlier scalar-count adapter stored a number directly. Never
        # infer an option's count by stripping a prefix such as "n".
        scalar = canonical_correction_answer(str(answer) if type(answer) in {int,float} else answer)
        try:
            count = Fraction(scalar)
            return scalar if count >= 0 and count.denominator == 1 else None
        except (ValueError,TypeError,ZeroDivisionError):
            return None
    return canonical_correction_answer(str(answer) if type(answer) in {int,float} else answer)


def _current_quantity_picture(question, result):
    if (not _quantity_review(question) or result.get('answerMode') != 'picture_choice'
            or question.get('visual') != result.get('picture')):
        return False
    choices = result['picture'].get('choices')
    options = question.get('options')
    return (isinstance(choices,list) and isinstance(options,list)
        and len(choices) == len(options)
        and all(isinstance(choice,dict) and isinstance(option,dict)
            and option.get('value') == choice.get('id')
            and option.get('picture') == {'count':choice.get('count')}
            for choice,option in zip(choices,options)))


def _legacy_arithmetic_expected(item, result):
    """Recompute the old local arithmetic contract; a saved answer key is not proof."""
    if (result.get('method') != 'decimal_arithmetic.v1'
            or result.get('status') not in {'correct','incorrect'}
            or result.get('recognitionNeedsConfirmation')):
        return None
    from services.homework_math import check_item
    from services.homework_service import POLICY
    exact = check_item(result,grade=item['grade_code'],subject=item['subject'],policy=POLICY,
        confirmed=result.get('recognitionConfirmed') is True)
    expected = canonical_correction_answer(exact.get('expectedAnswer'))
    if (exact.get('method') != 'decimal_arithmetic.v1' or exact.get('status') not in {'correct','incorrect'}
            or exact.get('recognitionNeedsConfirmation') or expected is None
            or expected != canonical_correction_answer(result.get('expectedAnswer'))):
        return None
    return expected


def _private_review_reference_current(conn, *, family_id, child_id, question, cache):
    """A real photographed review stays bound to its owned current reference.

    Older non-photo adapters have their own stable contracts. Their fake/legacy
    source identities do not authorize a query into any family's photo data.
    """
    if not isinstance(question,dict):
        return False
    source_id = question.get('sourceSubmissionId')
    if not question.get('private') or not isinstance(source_id,str) or not source_id.startswith('hw_'):
        return True
    source = _owned_source(conn,(family_id,child_id,source_id,question.get('sourceItemId')),cache)
    if source is None:
        return False
    item, reference, result = source
    if str(item['revision']) != str(question.get('sourceRevision')):
        return False
    expected = _review_answer(question,question.get('correctAnswer'))
    if _quantity_review(question):
        # These already-materialized picture questions predate referenceDigest.
        # Their option IDs are meaningful only through their frozen count and
        # the same current, locally verified source picture.
        current_expected = (reference['canonicalExpectedAnswer'] if reference is not None
            and reference['authority'] == 'exact' else _legacy_arithmetic_expected(item,result))
        current = bool(_current_quantity_picture(question,result) and expected is not None
            and expected == current_expected
            and (question.get('referenceDigest') is None
                or reference is not None and question['referenceDigest'] == reference['digest']))
    else:
        current = bool(reference is not None
            and question.get('referenceDigest') == reference['digest']
            and expected is not None and expected == reference['canonicalExpectedAnswer'])
    if not current:
        return False
    if question.get('sourceEventId') is not None:
        return conn.execute('''SELECT id FROM learning_answer_events
            WHERE id=? AND family_id=? AND child_id=? AND source_kind='homework'
              AND source_id=? AND revoked_at IS NULL''',
            (question['sourceEventId'],family_id,child_id,source_id)).fetchone() is not None
    return True


def private_review_reference_current(conn, *, family_id, child_id, question):
    """Shared fail-closed source check for weak points and completed reports."""
    try:
        return _private_review_reference_current(conn,family_id=family_id,child_id=child_id,
            question=question,cache={})
    except (ValueError,TypeError,KeyError,AttributeError):
        return False


def _verdict_matches(event, expected, question=None):
    answer = json.loads(event['answer_json'])
    actual = (_review_answer(question,answer) if question is not None else
        canonical_correction_answer(str(answer) if type(answer) in {int,float} else answer))
    verdict = event['correct']
    return (actual is not None and type(verdict) in {bool,int} and verdict in {0,1}
        and bool(verdict) == (actual == expected))


def current_homework_events(conn, rows):
    retained, cache = [], {}
    for event in rows:
        if event['source_kind'] not in {'homework','review'}:
            retained.append(event)
            continue
        try:
            question = json.loads(event['question_json'])
            if event['source_kind'] == 'review':
                if not _private_review_reference_current(conn,family_id=event['family_id'],
                        child_id=event['child_id'],question=question,cache=cache):
                    continue
                if (question.get('private') and str(question.get('sourceSubmissionId','')).startswith('hw_')
                        and not _verdict_matches(event,_review_answer(question,question.get('correctAnswer')),question)):
                    continue
                retained.append(event)
                continue
            # Older arithmetic adapters also use this domain with their own
            # stable source identities. Only photo submissions have hw_ IDs.
            if not str(event['source_id']).startswith('hw_'):
                retained.append(event)
                continue
            key = (event['family_id'], event['child_id'], event['source_id'], question['id'])
            source = _owned_source(conn,key,cache)
            if source is None:
                continue
            item, reference, result = source
            if str(item['revision']) != str(question.get('version')):
                continue
            # Legacy locally computed arithmetic already has its own immutable
            # confirmation contract. Tencent must pass the same new reference
            # gate used by student correction and parent display.
            if result.get('method') != 'tencent_question.v1':
                if result.get('status') in {'correct','incorrect'} and not result.get('recognitionNeedsConfirmation'):
                    retained.append(event)
                continue
            if reference is None:
                continue
            expected = canonical_correction_answer(question.get('correctAnswer'))
            if expected is None or expected != reference['canonicalExpectedAnswer']:
                continue
            if not _verdict_matches(event,expected):
                continue
            diagnosis = json.loads(event.get('diagnosis_json') or 'null') or {}
            if diagnosis.get('referenceDigest') not in {None, reference['digest']}:
                continue
            retained.append(event)
        except (ValueError,TypeError,KeyError,AttributeError):
            continue
    return retained
