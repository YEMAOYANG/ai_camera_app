"""Bounded domain evidence for the frozen tidy-review lesson (13 pages).

Client-reported, picture-supported operations; not proof of identity,
independent reading, oral or paper skills. The adapter projects authored
objects to stable integers and validates the reviewed page contracts.
"""
import re

from content.textbook_math_interaction import fields, integer, choice, fail

EDITION = 'pep-math-g1-upper-2022-standard'
REVISION = 'directory-ede7a8c63c337cf95a03fe79'
NODE = '5cd47ba3-5d21-48a1-9fc8-a41358ecc4bd'
PAGE_COUNT = 13
SUPPORT = ('replay', 'hint', 'demonstration')
OPERATIONS = ('work', 'submit', 'predict', *SUPPORT, 'undo', 'retry')
BOUNDARY = 'client_reported_picture_supported_practice'

WORK_FIELDS = {'tidy': {p: 'items prediction' if p in (5, 6, 7, 8, 11) else 'items'
                        for p in range(1, PAGE_COUNT + 1)}}
KEYS = {
    1: {'b0', 'b1', 'b2', 'b3', 'b4', 'b5'},
    2: {'slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5'},
    3: {'compare', 'ordinal'},
    4: {'left', 'right', 'total'},
    5: {'row', 'result'},
    6: {'column', 'slant'},
    7: {'row', 'result'},
    8: {'check', 'missing'},
    9: {'nodes', 'links'},
    10: {'link', 'explained'},
    11: {'anticipations', 'comparison'},
    12: {'order', 'compare', 'table'},
    13: {'marked', 'saved'},
}


def validators(binding):
    if (not isinstance(binding, dict) or set(binding) != {'editionId', 'revisionId', 'nodeId'}
            or binding['editionId'] != EDITION or binding['revisionId'] != REVISION
            or binding['nodeId'] != NODE):
        return None
    return {f'scene-p{p}': f'math-tidy-p{p}.v1' for p in range(1, PAGE_COUNT + 1)}


def identity(validator):
    match = re.fullmatch(r'math-tidy-p([1-9]|1[0-3])\.v1', validator or '')
    if not match:
        fail()
    return 'tidy', int(match[1])


def initial_page(validator):
    _, _ = identity(validator)
    return {'kind': 'math-tidy', 'validator': validator, 'phase': 'playing',
            'completed': False, 'lastWork': None, 'workVersion': 0, 'attempts': [],
            'firstAttempts': {}, 'firstPredictions': {}, 'latestPredictions': {},
            'passedTasks': [], 'support': dict.fromkeys(SUPPORT, 0),
            'undoCount': 0, 'retryCount': 0, 'exposureCount': 0, 'history': [],
            'evidenceBoundary': BOUNDARY, 'oralSkill': 'unobserved',
            'paperHandwriting': 'unobserved'}


def entries(value, keys):
    if not isinstance(value, list) or not value or len(value) > 12:
        fail()
    seen = set()
    result = {}
    for item in value:
        fields(item, 'key value')
        key = choice(item['key'], sorted(keys))
        if key in seen:
            fail()
        seen.add(key)
        result[key] = item['value']
    return result


def table_sum(result):
    integer(result, 0, 10)
    return result


def _check(page, work):
    if page == 1:
        for key in ('b0', 'b1', 'b2', 'b3', 'b4', 'b5'):
            integer(work[key], 0, 5)
        return all(work[f'b{k}'] == k for k in range(6))
    if page == 2:
        for key in ('slot0', 'slot1', 'slot2', 'slot3', 'slot4', 'slot5'):
            integer(work[key], 0, 5)
        return all(work[f'slot{k}'] == k for k in range(6))
    if page == 3:
        choice(work['compare'], ('more', 'less', 'same'))
        integer(work['ordinal'], 1, 6)
        return work['compare'] == 'less' and work['ordinal'] == 3
    if page == 4:
        integer(work['left'], 0, 5)
        integer(work['right'], 0, 5)
        integer(work['total'], 2, 5)
        return 0 < work['left'] and work['right'] > 0 and work['left'] + work['right'] == work['total']
    if page == 5:
        integer(work['row'], 0, 5)
        integer(work['result'], 0, 10)
        return 0 <= work['result'] <= 5 and work['row'] <= work['result']
    if page == 6:
        integer(work['column'], 0, 5)
        integer(work['slant'], 0, 10)
        return 0 <= work['slant'] <= 5
    if page == 7:
        integer(work['row'], 0, 5)
        integer(work['result'], 0, 5)
        return work['result'] <= work['row']
    if page == 8:
        choice(work['check'], ('addition', 'subtraction'))
        integer(work['missing'], 0, 5)
        return True
    if page == 9:
        if not isinstance(work['nodes'], list) or not 3 <= len(work['nodes']) <= 7:
            fail()
        for node in work['nodes']:
            choice(node, ('count', 'order', 'compare', 'ordinal', 'split', 'addition', 'subtraction'))
        if not isinstance(work['links'], list) or not work['links']:
            fail()
        for link in work['links']:
            fields(link, 'a b')
            choice(link['a'], ('count', 'order', 'compare', 'ordinal', 'split', 'addition', 'subtraction'))
            choice(link['b'], ('count', 'order', 'compare', 'ordinal', 'split', 'addition', 'subtraction'))
        return True
    if page == 10:
        fields(work['link'], 'a b')
        choice(work['link']['a'], ('count', 'order', 'compare', 'ordinal', 'split', 'addition', 'subtraction'))
        choice(work['link']['b'], ('count', 'order', 'compare', 'ordinal', 'split', 'addition', 'subtraction'))
        if type(work['explained']) is not bool:
            fail()
        return work['explained'] is True
    if page == 11:
        if not isinstance(work['anticipations'], list) or not work['anticipations']:
            fail()
        for item in work['anticipations']:
            choice(item, ('count', 'order', 'compare', 'split', 'addition', 'subtraction'))
        fields(work['comparison'], 'matched different')
        return type(work['comparison']['matched']) is int and type(work['comparison']['different']) is int
    if page == 12:
        fields(work['order'], 'value')
        integer(work['order']['value'], 0, 5)
        choice(work['compare'], ('more', 'less', 'same'))
        fields(work['table'], 'value')
        integer(work['table']['value'], 0, 10)
        return True
    if page == 13:
        choice(work['marked'], ('split', 'order', 'compare', 'addition', 'subtraction', 'split-addition', 'addition-subtraction'))
        if type(work['saved']) is not bool:
            fail()
        return work['saved'] is True
    fail()


def apply_page(validator, state, operation, *, previous=None):
    kind, page = identity(validator)
    fields(operation, 'name work')
    name = choice(operation['name'], OPERATIONS)
    w = operation['work']
    fields(w, WORK_FIELDS[kind][page])
    data = entries(w['items'], KEYS[page])
    if 'prediction' in WORK_FIELDS[kind][page]:
        pred = w.get('prediction')
        if pred is not None and type(pred) is not bool:
            fail()
        if pred is not None:
            state['firstPredictions'].setdefault(page, pred)
            state['latestPredictions'][page] = pred
    if name in SUPPORT:
        state['support'][name] += 1
        state['exposureCount'] += 1
        state['history'].append({'name': name})
        return state
    if name == 'undo':
        state['undoCount'] += 1
        state['history'].append({'name': name})
        return state
    if name == 'retry':
        state['retryCount'] += 1
        state['history'].append({'name': name})
        return state
    if name == 'predict':
        state['history'].append({'name': name, 'prediction': w.get('prediction')})
        return state
    correct = _check(page, data)
    state['lastWork'] = w
    state['workVersion'] += 1
    state['attempts'].append({'page': page, 'correct': correct, 'helpCount': sum(state['support'].values())})
    state['firstAttempts'].setdefault(page, correct)
    state['passedTasks'] = sorted(set(state['passedTasks']) | ({page} if correct else set()))
    if name == 'submit' and correct:
        state['completed'] = True
        state['phase'] = 'complete'
    state['history'].append({'name': name, 'correct': correct})
    return state
