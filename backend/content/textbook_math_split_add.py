"""Bounded work evidence for the two fixed five-within math lessons.

The server recomputes counts, partitions and written representations. These are
client-reported picture-supported activities, never proof of oral skill,
unassisted performance, identity or mastery. Completion flags are not inputs.
"""
from copy import deepcopy
import math
import re

from content.textbook_math_interaction import fields, integer, choice, fail

EDITION = 'pep-math-g1-upper-2022-standard'
REVISION = 'directory-ede7a8c63c337cf95a03fe79'
NODES = {'2a0eae67-3639-46ec-abde-d3f879f88245': 'split',
         '21fab431-9322-4bb0-aee8-1c4ad644bf55': 'add'}
TASKS = {
    'split': {2: ['1', '2'], 3: ['1-4', '2-3', '3-2', '4-1'],
              4: ['move'], 5: ['0', '1'], 6: ['0', '1', '2'],
              7: ['card'], 8: ['0', '1', '2'], 9: ['2', '3', '4', '5'],
              10: ['0', '1', '2'], 11: ['creation']},
    'add': {2: ['0', '1'], 3: ['equation'], 4: ['symbol'], 5: ['timeline'],
            6: ['method'], 7: ['balance'], 8: ['AB', 'BA'], 9: ['repair'],
            10: ['0', '1', '2'], 11: ['creation']},
}
PHOTOS = {f'p{n}{chr(96 + left)}': (n, left, n-left)
          for n in range(2, 6) for left in range(1, n)}


def validators(binding):
    if (not isinstance(binding, dict) or binding.get('editionId') != EDITION
            or binding.get('revisionId') != REVISION):
        return None
    kind = NODES.get(binding.get('nodeId'))
    return {f'scene-p{i}': f'math-{kind}-p{i}.v1' for i in range(2, 12)} if kind else None


def identity(validator):
    match = re.fullmatch(r'math-(split|add)-p(2|3|4|5|6|7|8|9|10|11)\.v1', validator or '')
    if not match:
        fail()
    return match[1], int(match[2])


def initial_page(validator):
    kind, _ = identity(validator)
    return {'kind': f'math-{kind}', 'validator': validator, 'phase': 'playing',
            'completed': False, 'lastWork': None, 'attempts': [], 'passedTasks': [],
            'helpCount': 0, 'seenPartitions': {},
            'evidenceBoundary': 'client_reported_picture_supported_practice'}


def nullable_number(value, low=1, high=5):
    if value is not None:
        integer(value, low, high)
    return value


def boolean(value):
    if type(value) is not bool:
        fail()
    return value


def ids(value, allowed=None, maximum=10):
    if not isinstance(value, list) or len(value) > maximum:
        fail()
    for v in value:
        if type(v) is int:
            integer(v, 0, 10)
        elif not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', v):
            fail()
    if len(set(value)) != len(value) or (allowed is not None and not set(value) <= set(allowed)):
        fail()
    return value


def partition(left, right, allowed, unassigned=None):
    left, right = ids(left, allowed), ids(right, allowed)
    rest = [] if unassigned is None else ids(unassigned, allowed)
    if len(set(left+right+rest)) != len(left+right+rest):
        fail()
    if unassigned is not None and set(left+right+rest) != set(allowed):
        fail()
    return bool(left and right and set(left+right) == set(allowed))


def plus_trace(strokes):
    if not isinstance(strokes, list) or len(strokes) > 24:
        fail()
    ends = []
    for stroke in strokes:
        if not isinstance(stroke, list) or not 2 <= len(stroke) <= 600:
            fail()
        for p in stroke:
            if (not isinstance(p, list) or len(p) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not -20 <= v <= 240 for v in p)):
                fail()
        ends.append((stroke[0], stroke[-1]))
    # Generous geometry tolerances; no reliance on a client's stroke label.
    if len(ends) != 2:
        return False
    (h0, h1), (v0, v1) = ends
    hy, vx = (h0[1]+h1[1])/2, (v0[0]+v1[0])/2
    return (h1[0]-h0[0] >= 50 and v1[1]-v0[1] >= 50
            and abs(h1[1]-h0[1]) <= 25 and abs(v1[0]-v0[0]) <= 25
            and h0[0]+10 < vx < h1[0]-10 and v0[1]+10 < hy < v1[1]-10
            and all(abs(p[1]-hy) <= 25 for p in strokes[0])
            and all(abs(p[0]-vx) <= 25 for p in strokes[1]))


def split_work(page, w, state):
    if page == 2:
        fields(w, 'phase left right unsent')
        phase = integer(w['phase'], 1, 2)
        return str(phase), partition(w['left'], w['right'], [f'ball-{i}' for i in range(1, phase+2)], w['unsent'])
    if page == 3:
        fields(w, 'left right')
        ok = partition(w['left'], w['right'], [f'lamp-{c}' for c in 'abcde'])
        key = f"{len(w['left'])}-{len(w['right'])}"
        return key if key in TASKS['split'][3] else '1-4', ok
    if page == 4:
        fields(w, 'left right beforeLeft beforeRight predictionLeft predictionTotal')
        allowed = [f'L{i}' for i in range(1, 6)]
        ok = partition(w['left'], w['right'], allowed)
        partition(w['beforeLeft'], w['beforeRight'], allowed)
        if w['beforeLeft'] != ['L1', 'L2'] or w['beforeRight'] != ['L3', 'L4', 'L5']:
            fail()
        if w['predictionLeft'] is not None:
            choice(w['predictionLeft'], ['more', 'less'])
        if w['predictionTotal'] is not None:
            choice(w['predictionTotal'], ['same', 'change'])
        delta = len(w['left']) - 2
        moved = len(set(w['left']) ^ set(w['beforeLeft']))
        return 'move', ok and moved == 1 and delta in [-1, 1] and w['predictionTotal'] == 'same' and w['predictionLeft'] == ('more' if delta == 1 else 'less')
    if page == 5:
        fields(w, 'round left right prediction swaps')
        r = integer(w['round'], 0, 1); swaps = integer(w['swaps'], 0, 100)
        ok = partition(w['left'], w['right'], ['m1', 'm2', 'm3', 'm4'])
        if w['prediction'] is not None:
            boolean(w['prediction'])
        expected = (3, 1) if r == 0 else (2, 2)
        return str(r), ok and swaps % 2 == 1 and (len(w['left']), len(w['right'])) == expected and w['prediction'] is (r == 1)
    if page == 6:
        fields(w, 'round left right prediction gateOpen')
        r = integer(w['round'], 0, 2); total = [4, 3, 5][r]
        ok = partition(w['left'], w['right'], list(range(1, total+1)))
        nullable_number(w['prediction']); boolean(w['gateOpen'])
        return str(r), ok and w['gateOpen'] and w['prediction'] == total
    if page == 7:
        fields(w, 'photo whole left right')
        for k in ['whole', 'left', 'right']:
            nullable_number(w[k])
        if w['photo'] is None:
            return 'card', False
        choice(w['photo'], PHOTOS)
        return 'card', (w['whole'], w['left'], w['right']) == PHOTOS[w['photo']]
    if page == 8:
        fields(w, 'round prediction revealed')
        r = integer(w['round'], 0, 2)
        nullable_number(w['prediction'], 0, 5); boolean(w['revealed'])
        return str(r), w['revealed'] and w['prediction'] == [1, 2, 2][r]
    if page == 9:
        fields(w, 'total left right supply')
        if w['total'] is None:
            if w['left'] != [] or w['right'] != [] or w['supply'] != []:
                fail()
            return '2', False
        total = integer(w['total'], 2, 5)
        ok = partition(w['left'], w['right'], list(range(total)), w['supply'])
        seen = state['seenPartitions'].setdefault(str(total), [])
        if ok and len(w['left']) not in seen:
            seen.append(len(w['left']))
        exhausted = set(seen) == set(range(1, total))
        return str(total), ok and (len(w['left']) == len(w['right']) or total % 2 == 1 and exhausted)
    if page == 10:
        fields(w, 'level left right prediction revealed')
        level = integer(w['level'], 0, 2); boolean(w['revealed']); nullable_number(w['prediction'], 0, 5)
        allowed = [['lamp-a', 'lamp-b', 'lamp-c'],
                   ['converge-l1', 'converge-l2', 'converge-r1', 'converge-r2', 'converge-r3'],
                   ['hide-v1', 'hide-v2', 'hide-h1', 'hide-h2']][level]
        ok = partition(w['left'], w['right'], allowed)
        return str(level), ok and (level == 0 or w['revealed'] and w['prediction'] == (5 if level == 1 else 2))
    fields(w, 'total left right hiddenSide partnerGuess revealed saved')
    total = integer(w['total'], 2, 5)
    ok = partition(w['left'], w['right'], list(range(1, total+1)))
    if w['hiddenSide'] is not None:
        choice(w['hiddenSide'], ['left', 'right'])
    nullable_number(w['partnerGuess']); boolean(w['revealed'])
    saved = w['saved']
    if saved is not None:
        fields(saved, 'total left right hiddenDock')
        integer(saved['total'], 2, 5)
        partition(saved['left'], saved['right'], list(range(1, saved['total']+1)))
        choice(saved['hiddenDock'], ['left', 'right'])
    matches = saved == {'total': total, 'left': w['left'], 'right': w['right'], 'hiddenDock': w['hiddenSide']}
    return 'creation', ok and w['hiddenSide'] is not None and w['partnerGuess'] is not None and w['revealed'] and matches


def add_work(page, w):
    if page == 2:
        fields(w, 'round prediction gates')
        r = integer(w['round'], 0, 1); nullable_number(w['prediction'])
        if not isinstance(w['gates'], list) or len(w['gates']) != 2:
            fail()
        for v in w['gates']:
            boolean(v)
        return str(r), all(w['gates']) and w['prediction'] == [3, 4][r]
    if page == 3:
        fields(w, 'A B C')
        for v in w.values():
            nullable_number(v)
        return 'equation', (w['A'], w['B'], w['C']) == (2, 1, 3)
    if page == 4:
        fields(w, 'strokes a b')
        trace = plus_trace(w['strokes']); ids(w['a'], maximum=3); ids(w['b'], maximum=3)
        if len(set(w['a']+w['b'])) != len(w['a']+w['b']) or len(w['a']+w['b']) > 5:
            fail()
        return 'symbol', trace and bool(w['a'] and w['b'])
    if page == 5:
        fields(w, 'original new total')
        ids(w['original'], list(range(1, 6))); ids(w['new'], list(range(1, 6))); nullable_number(w['total'])
        if set(w['original']) & set(w['new']):
            fail()
        return 'timeline', set(w['original']) == {1, 2} and set(w['new']) == {3, 4, 5} and w['total'] == 5
    if page == 6:
        fields(w, 'method original new order left right')
        orig, new = ['orig-1', 'orig-2'], ['new-1', 'new-2']; allowed = orig+new
        ids(w['original'], orig); ids(w['new'], new); ids(w['order'], allowed)
        p = partition(w['left'], w['right'], allowed)
        if w['method'] is None:
            return 'method', False
        choice(w['method'], ['countAll', 'countOn', 'partition'])
        counted = set(w['original']+w['new']) == set(allowed) and set(w['order']) == set(allowed)
        if w['method'] == 'countOn':
            counted = counted and set(w['order'][:2]) == set(orig)
        return 'method', p if w['method'] == 'partition' else counted
    if page == 7:
        fields(w, 'left right plan')
        for v in w.values():
            ids(v, maximum=5)
        all_ids = w['left']+w['right']+w['plan']
        if len(all_ids) != len(set(all_ids)):
            fail()
        return 'balance', len(w['left']) == len(w['right']) == 4 and not w['plan']
    if page == 8:
        fields(w, 'order prediction'); order = choice(w['order'], ['AB', 'BA'])
        nullable_number(w['prediction'])
        return order, w['prediction'] == 3
    if page == 9:
        fields(w, 'leftDots rightDots eqLeft eqRight eqTotal')
        for v in w.values():
            integer(v, 0, 5)
        return 'repair', list(w[k] for k in ['leftDots', 'rightDots', 'eqLeft', 'eqRight', 'eqTotal']) == [2, 2, 2, 2, 4]
    if page == 10:
        fields(w, 'level answer'); level = integer(w['level'], 0, 2)
        if w['answer'] is not None:
            if level < 2:
                integer(w['answer'], 0, 5)
            else:
                choice(w['answer'], ['left', 'right', 'all'])
        return str(level), w['answer'] == [5, 2, 'right'][level]
    fields(w, 'part1 part2 equation')
    arrays = []
    for part in ['part1', 'part2']:
        items = w[part]
        if not isinstance(items, list) or len(items) > 5:
            fail()
        for item in items:
            fields(item, 'id prop'); choice(item['prop'], ['boat', 'ball', 'crate'])
        arrays.append(ids([i['id'] for i in items]))
    if len(set(arrays[0]+arrays[1])) != len(arrays[0]+arrays[1]) or len(arrays[0]+arrays[1]) > 5:
        fail()
    fields(w['equation'], 'num1 num2 sum')
    for v in w['equation'].values():
        nullable_number(v)
    n1, n2 = map(len, arrays)
    return 'creation', bool(n1 and n2) and w['equation'] == {'num1': n1, 'num2': n2, 'sum': n1+n2}


def apply_page(validator, state, operation):
    kind, page = identity(validator)
    if (not isinstance(operation, dict) or set(operation) != {'name', 'work'}
            or operation.get('name') not in ['work', 'submit', 'help']
            or state.get('validator') != validator or len(state['attempts']) >= 128):
        fail()
    w = operation['work']
    task, correct = split_work(page, w, state) if kind == 'split' else add_work(page, w)
    tasks = TASKS[kind][page]
    if task not in tasks:
        fail()
    sequential = page in ([2, 5, 6, 8, 10] if kind == 'split' else [2, 10])
    if sequential and any(t not in state['passedTasks'] for t in tasks[:tasks.index(task)]):
        fail()
    state['lastWork'] = deepcopy(w)
    if operation['name'] == 'help':
        state['helpCount'] += 1
    elif operation['name'] == 'submit':
        state['attempts'].append({'task': task, 'work': deepcopy(w), 'correct': bool(correct),
                                  'helpCount': state['helpCount'], 'assistanceOutsideApp': 'unobserved'})
        if correct and task not in state['passedTasks']:
            state['passedTasks'].append(task)
    state['completed'] = set(state['passedTasks']) == set(tasks)
    state['phase'] = 'complete' if state['completed'] else 'playing'
