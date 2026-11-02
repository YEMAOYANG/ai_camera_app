"""Validate reported mathematical work, never a client completion flag.

These two fixed lessons submit bounded object arrangements, choices and ink.
The server computes each outcome against its frozen task. Evidence is explicitly
client-reported picture-supported practice, not independent mastery or speech.
"""
from copy import deepcopy
import math
import re

from core.errors import ApiError

EDITION = 'pep-math-g1-upper-2022-standard'
REVISION = 'directory-ede7a8c63c337cf95a03fe79'
NODES = {'32aff930-d2cb-475f-8263-acf853fd4edf': 'compare',
         '803c9ac0-d35c-47a6-9a86-019581b8f4f7': 'ordinal'}
ROLES = [f'r{i}' for i in range(1, 6)]
TOOLS = ['telescope', 'compass', 'magnifier', 'ruler', 'tweezers']
INK = [[[110,112,290,112],[110,168,290,168]],
       [[95,90,305,140],[305,140,95,190]], [[305,90,95,140],[95,140,305,190]]]
TASKS = {'compare': {2: ['0','1'], 3: ['pairs'], 4: ['left','right'],
                    5: ['0','1','2'], 6: ['0','1','2'], 7: ['0','1','2'], 8: ['creation']},
         'ordinal': {2: ['quantity','ordinal'], 3: ['0','1','2'], 4: ['0','1'],
                    5: ['0','1'], 6: ['left','right'], 7: ['0','1','2','3'], 8: ['ordinal','quantity']}}


def fail():
    raise ApiError('textbook_interaction_operation_invalid', '数学互动记录与本课任务不一致', 409)


def validators(binding):
    if not isinstance(binding, dict) or binding.get('editionId') != EDITION or binding.get('revisionId') != REVISION:
        return None
    kind = NODES.get(binding.get('nodeId'))
    return {f'scene-p{i}': f'math-{kind}-p{i}.v1' for i in range(2, 9)} if kind else None


def identity(validator):
    match = re.fullmatch(r'math-(compare|ordinal)-p([2-8])\.v1', validator or '')
    if not match:
        fail()
    return match[1], int(match[2])


def initial_page(validator):
    kind, page = identity(validator)
    return {'kind': f'math-{kind}', 'validator': validator, 'phase': 'playing',
            'completed': False, 'lastWork': None, 'attempts': [], 'passedTasks': [],
            'helpCount': 0, 'evidenceBoundary': 'client_reported_picture_supported_practice'}


def fields(work, names):
    if not isinstance(work, dict) or set(work) != set(names.split()):
        fail()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail()
    return value


def choice(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        fail()
    return value


def selected(value, allowed, maximum=None):
    if (not isinstance(value, list) or len(value) > (len(allowed) if maximum is None else maximum)
            or any(not isinstance(v, str) or v not in allowed for v in value)
            or len(value) != len(set(value))):
        fail()
    return value


def distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx*dx + dy*dy
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def ink_covered(index, strokes):
    if not isinstance(strokes, list) or len(strokes) > 50:
        fail()
    for stroke in strokes:
        if not isinstance(stroke, list) or not 2 <= len(stroke) <= 300:
            fail()
        for p in stroke:
            if (not isinstance(p, list) or len(p) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                    or not 0 <= p[0] <= 400 or not 0 <= p[1] <= 280):
                fail()
    segments = INK[index]
    lines = [(s[i-1], s[i]) for s in strokes for i in range(1, len(s))]
    length = sum(math.dist(a, b) for a, b in lines)
    on = sum(any(distance(b, seg[:2], seg[2:]) <= 25 for seg in segments) for _, b in lines)
    target_length = sum(math.dist(s[:2], s[2:]) for s in segments)
    return bool(lines and length >= target_length*.7 and on/len(lines) >= .7
        and all(sum(any(distance([a+(c-a)*i/10, b+(d-b)*i/10], p, q) <= 20 for p,q in lines)
                    for i in range(11)) >= 8 for a,b,c,d in segments))


def compare_work(page, w):
    if page == 2:
        fields(w, 'preset assignments'); p = integer(w['preset'], 0, 1)
        people, cups = [(4,3),(2,4)][p]; values = w['assignments']
        if not isinstance(values, list) or len(values) != cups:
            fail()
        used = [v for v in values if v is not None]
        selected(used, [f'p{i}' for i in range(people)])
        return str(p), len(used) == min(people, cups)
    if page == 3:
        fields(w, 'pairs'); pairs = w['pairs']
        if not isinstance(pairs, list) or len(pairs) > 4:
            fail()
        for p in pairs:
            fields(p, 'left right')
        selected([p['left'] for p in pairs], ['L1','L2','L3','L4'])
        selected([p['right'] for p in pairs], ['R1','R2','R3','R4'])
        return 'pairs', len(pairs) == 4
    if page == 4:
        fields(w, 'leftCount rightCount openSide')
        if (w['leftCount'], w['rightCount']) not in [(5,3),(3,5)] or any(type(w[k]) is not int for k in ['leftCount','rightCount']):
            fail()
        side = choice(w['openSide'], ['left','right'])
        target = 'left' if w['leftCount'] > w['rightCount'] else 'right'
        return target, side == target
    if page == 5:
        fields(w, 'round left right'); r = integer(w['round'], 0, 2)
        left, right = (integer(w[k], 0, 5) for k in ['left','right'])
        return str(r), bool(left and right and [left == right, left > right, left < right][r])
    if page == 6:
        fields(w, 'index strokes'); index = integer(w['index'], 0, 2)
        return str(index), ink_covered(index, w['strokes'])
    if page == 7:
        fields(w, 'round marked sign'); r = integer(w['round'], 0, 2)
        l, n = [(4,4),(3,5),(5,2)][r]
        targets = [f'l{i}' for i in range(1,l+1)] + [f'r{i}' for i in range(1,n+1)]
        # Distractors are valid submitted choices but never count as targets.
        allowed = targets + ['ld1','ld2','rd1','rd2']
        selected(w['marked'], allowed)
        if w['sign'] not in [None,'<','=','>']:
            fail()
        return str(r), set(w['marked']) == set(targets) and w['sign'] == ['=','<','>'][r]
    fields(w, 'relation left right')
    relation = choice(w['relation'], ['eq','gt','lt'])
    items = w['left'] + w['right'] if isinstance(w['left'], list) and isinstance(w['right'], list) else None
    if items is None or len(w['left']) > 5 or len(w['right']) > 5:
        fail()
    for item in items:
        fields(item, 'uid type')
        integer(item['uid'], 1, 100000)
        choice(item['type'], ['cup','bottle','box','lantern','flower','fish','kid','boy'])
    if len({x['uid'] for x in items}) != len(items):
        fail()
    l, r = len(w['left']), len(w['right'])
    return 'creation', bool(l and r and {'eq':l==r,'gt':l>r,'lt':l<r}[relation])


def ordinal_work(page, w):
    if page == 2:
        fields(w, 'phase inside')
        phase = choice(w['phase'], ['quantity','ordinal']); selected(w['inside'], ROLES)
        return phase, len(w['inside']) == 5 if phase == 'quantity' else w['inside'] == ['r2']
    if page == 3:
        fields(w, 'mode task atDoor'); mode = choice(w['mode'], ['demo','practice'])
        task = integer(w['task'], 0, 2)
        if w['atDoor'] is not None:
            choice(w['atDoor'], ROLES)
        return str(task), mode == 'practice' and w['atDoor'] == ['r5','r1','r2'][task]
    if page == 4:
        fields(w, 'round left right'); r = integer(w['round'], 0, 1)
        for key in ['left','right']:
            if w[key] is not None:
                integer(w[key], 1, 5)
        return str(r), (w['left'], w['right']) == [(1,5),(3,3)][r]
    if page == 5:
        fields(w, 'phase order'); p = integer(w['phase'], 0, 1)
        selected(w['order'], TOOLS)
        if len(w['order']) != 5:
            fail()
        return str(p), w['order'][1] == 'telescope' and (p == 0 or w['order'][4] == 'compass')
    if page == 6:
        fields(w, 'direction answer')
        if w['direction'] is None and w['answer'] is None:
            return 'left', False
        direction = choice(w['direction'], ['left','right'])
        if w['answer'] is not None:
            choice(w['answer'], ROLES)
        return direction, w['answer'] == ('r2' if direction == 'left' else 'r4')
    if page == 7:
        fields(w, 'round opened direction rank'); r = integer(w['round'], 0, 3)
        selected(w['opened'], [f'w{i}' for i in range(1,6)])
        if w['direction'] is not None:
            choice(w['direction'], ['left','right'])
        if w['rank'] is not None:
            integer(w['rank'], 1, 5)
        if r < 2:
            return str(r), w['opened'] == ['w3' if r == 0 else 'w4']
        target = 4 if r == 2 else 2
        return str(r), w['direction'] is not None and w['rank'] == (target+1 if w['direction']=='left' else 5-target)
    fields(w, 'phase departure docked')
    phase = choice(w['phase'], ['ordinal','quantity'])
    boats = [f'boat-{i}' for i in range(5)]
    selected(w['docked'], boats)
    if w['departure'] is not None:
        choice(w['departure'], boats)
    return phase, w['departure'] == 'boat-2' if phase == 'ordinal' else len(w['docked']) == 3


def apply_page(validator, state, operation):
    kind, page = identity(validator)
    if (not isinstance(operation, dict) or set(operation) != {'name','work'}
            or operation.get('name') not in ['work','submit','help']
            or state.get('validator') != validator or len(state['attempts']) >= 128):
        fail()
    work = operation['work']
    task, correct = (compare_work if kind == 'compare' else ordinal_work)(page, work)
    tasks = TASKS[kind][page]
    if task not in tasks:
        fail()
    # Explicitly sequential tasks cannot be credited by jumping to a later one.
    sequential = page in ([5,7] if kind == 'compare' else [2,3,4,5,7,8])
    if sequential and any(t not in state['passedTasks'] for t in tasks[:tasks.index(task)]):
        # The untouched demonstration on ordinal p3 still belongs to task 0.
        fail()
    state['lastWork'] = deepcopy(work)
    if operation['name'] == 'help':
        state['helpCount'] += 1
    elif operation['name'] == 'submit':
        state['attempts'].append({'task': task, 'work': deepcopy(work), 'correct': bool(correct),
                                  'helpCount': state['helpCount'], 'assistanceOutsideApp': 'unobserved'})
        if correct and task not in state['passedTasks']:
            state['passedTasks'].append(task)
    state['completed'] = set(state['passedTasks']) == set(tasks)
    state['phase'] = 'complete' if state['completed'] else 'playing'
