"""Exact fruit lesson: bounded, server-computed picture-supported practice.

Reported simulation inputs do not establish real tasting, touching, independent
reading or mastery. UI 'done' flags never grant course completion.
"""
from copy import deepcopy
import math
import re
from core.errors import ApiError

BINDING = {'editionId': 'smartedu-science-six-year-g1-upper-64e96b25',
           'revisionId': 'directory-0e2e092fb846ac493525aece',
           'nodeId': '55cd6f6c-5773-4de7-9ad3-f35b510ba856'}
VALIDATORS = {f'scene-p{p}': f'science-fruit-p{p}.v1' for p in range(2, 12)}
SOURCES = {'ev-color': 'vision', 'ev-shape': 'vision', 'ev-texture': 'probe',
           'ev-softness': 'probe', 'ev-smell': 'smell', 'ev-taste': 'taste'}
VENN = {'ev-round': 'both', 'ev-red-apple': 'both', 'ev-stem': 'apple',
        'ev-shiny': 'both', 'ev-small': 'apple', 'ev-seed-many': 'tomato'}
FRUITS = {'apple_red': ('red', 'round', 'small'), 'apple_green': ('green', 'round', 'small'),
          'banana': ('yellow', 'long', 'medium'), 'orange': ('orange', 'round', 'medium'),
          'lemon': ('yellow', 'long', 'small'), 'watermelon': ('green', 'round', 'large'),
          'melon': ('yellow', 'round', 'medium')}
TRANSFER = {'seedpod': ('angled', 'textured'), 'shell': ('rounded', 'smooth'), 'cork': ('rounded', 'textured')}


def fail():
    raise ApiError('textbook_interaction_operation_invalid', '水果观察记录与本页任务不一致', 409)


def validators(binding):
    return VALIDATORS if binding == BINDING else None


def identity(validator):
    if validator not in VALIDATORS.values():
        fail()
    return int(re.search(r'p(\d+)\.', validator)[1])


def fields(v, names):
    if not isinstance(v, dict) or set(v) != set(names.split()):
        fail()


def choice(v, choices):
    if v not in choices or not isinstance(v, (str, type(None))):
        fail()
    return v


def integer(v, high=128):
    if type(v) is not int or not 0 <= v <= high:
        fail()
    return v


def boolean(v):
    if type(v) is not bool:
        fail()


def ordered_senses(v, eye):
    if not isinstance(v, list) or len(v) > 4 or any(x not in [eye, 'hand', 'nose', 'tongue'] for x in v) or len(set(v)) != len(v):
        fail()
    return all(all(t in v[:i] for t in [eye, 'hand']) for i, x in enumerate(v) if x in ['nose', 'tongue'])


def mapping(v, ids, destinations, *, sparse=False):
    if not isinstance(v, dict) or (not set(v) <= set(ids) if sparse else set(v) != set(ids)):
        fail()
    for x in v.values():
        choice(x, destinations)


def bounded_record(v, depth=0):
    if depth > 5:
        fail()
    if v is None or type(v) is bool:
        return
    if type(v) in (int, float):
        if not math.isfinite(v) or abs(v) > 10**15:
            fail()
    elif isinstance(v, str):
        if len(v) > 300:
            fail()
    elif isinstance(v, list):
        if len(v) > 20:
            fail()
        for item in v:
            bounded_record(item, depth + 1)
    elif isinstance(v, dict):
        if len(v) > 20 or any(not isinstance(k, str) or len(k) > 60 for k in v):
            fail()
        for item in v.values():
            bounded_record(item, depth + 1)
    else:
        fail()


def initial_page(validator):
    identity(validator)
    return {'kind': 'science-fruit', 'validator': validator, 'phase': 'playing', 'completed': False,
            'lastWork': None, 'firstWork': None, 'firstAnswer': None, 'attempts': [], 'helpCount': 0, 'milestones': [],
            'evidenceBoundary': 'client_reported_picture_supported_simulation_not_real_sensory_skill_or_mastery'}


def evaluate(page, w, state, action):
    fields(w, 'started decision domain help first response')
    bounded_record(w['first']); bounded_record(w['response'])
    boolean(w['started']); integer(w['help'])
    if not w['started']:
        fail()
    d, x = w['decision'], w['domain']
    old = state['lastWork']; marks = state['milestones']
    correct = False
    if page == 2:
        fields(x, '')
        correct = ordered_senses(d, 'eyes') and len(d) == 4
    elif page == 3:
        fields(x, '')
        if not isinstance(d, list) or len(d) > 4:
            fail()
        labels = []
        for e in d:
            fields(e, 'label region rotation')
            choice(e['region'], ['顶部', '侧面', '底部'])
            allowed = ['果蒂', '橙色', '接近球形'] if e['region'] == '顶部' else ['橙色', '接近球形', '表面有小点']
            choice(e['label'], allowed)
            r = e['rotation']
            if type(r) not in (int, float) or not math.isfinite(r) or abs(r) > 36000:
                fail()
            labels.append(e['label'])
        if len(set(labels)) != len(labels):
            fail()
        correct = len(d) >= 3 and len({e['region'] for e in d}) >= 2
    elif page == 4:
        fields(x, 'force'); integer(x['force'], 3)
        if x['force'] == 0 or not isinstance(d, list) or len(d) > 8:
            fail()
        kinds = set()
        for e in d:
            fields(e, 'text kind')
            choice(e['kind'], ['press', 'texture'])
            texts = ['软硬·轻压回弹 (弹性)', '软硬·中压有弹性 (弹性)'] if e['kind'] == 'press' else ['纹理·小凸点/粗糙 (表面)']
            choice(e['text'], texts); kinds.add(e['kind'])
        correct = kinds == {'press', 'texture'}
    elif page == 5:
        fields(x, ''); fields(d, 'vision probe smell taste')
        seen = []
        for bucket, items in d.items():
            if not isinstance(items, list) or len(items) > 6:
                fail()
            for item in items:
                choice(item, list(SOURCES)); seen.append(item)
        if len(set(seen)) != len(seen):
            fail()
        correct = len(seen) == 6 and all(SOURCES[item] == bucket for bucket, items in d.items() for item in items)
    elif page == 6:
        fields(d, 'positions mode force'); fields(d['positions'], 'left right')
        for fruit in d['positions'].values():
            choice(fruit, ['apple', 'tomato'])
        if set(d['positions'].values()) != {'apple', 'tomato'}:
            fail()
        choice(d['mode'], ['angle', 'probe']); choice(d['force'], ['light', 'heavy'])
        fields(x, 'fruits swaps'); integer(x['swaps']); fields(x['fruits'], 'apple tomato')
        for f in x['fruits'].values():
            fields(f, 'angle force'); integer(f['angle'], 2); choice(f['force'], [None, 'light'])
        aligned = len({f['angle'] for f in x['fruits'].values()}) == 1 and all(f['force'] == 'light' for f in x['fruits'].values())
        if x['swaps'] == 0 and aligned and 'before-swap' not in marks:
            marks.append('before-swap')
        if old and x['swaps'] == old['domain']['swaps'] + 1 and d['positions']['left'] == old['decision']['positions']['right'] and all(f['force'] is None for f in x['fruits'].values()) and 'before-swap' in marks:
            if 'swap' not in marks:
                marks.append('swap')
        correct = 'swap' in marks and x['swaps'] > 0 and aligned
    elif page == 7:
        fields(x, ''); mapping(d, VENN, [None, 'apple', 'both', 'tomato'])
        correct = d == VENN
    elif page == 8:
        fields(x, 'standard'); choice(x['standard'], [None, 'color', 'shape', 'size'])
        mapping(d, FRUITS, ['left', 'right'], sparse=True)
        i = ['color', 'shape', 'size'].index(x['standard']) if x['standard'] else 0
        def target(v):
            return 'left' if (v[i] == 'red' if i == 0 else v[i] == 'round' if i == 1 else v[i] != 'large') else 'right'
        correct = x['standard'] is not None and len(d) == 7 and all(d[k] == target(v) for k, v in FRUITS.items())
    elif page == 9:
        fields(x, 'standard'); choice(x['standard'], [None, 'edge', 'surface'])
        mapping(d, TRANSFER, [None, 'A', 'B'])
        i = 0 if x['standard'] == 'edge' else 1
        groups = [{TRANSFER[k][i] for k in d if d[k] == side} for side in ['A', 'B']]
        correct = action == 'shakeBtn' and x['standard'] is not None and all(d.values()) and all(len(g) == 1 for g in groups) and groups[0] != groups[1]
    elif page == 10:
        choice(d, [None, 'top', 'bottom', 'same']); fields(x, 'phase tool top bottom count')
        choice(x['phase'], ['judge', 'tool', 'measure', 'revise', 'done']); choice(x['tool'], [None, 'ruler', 'overlay', 'magnifier'])
        boolean(x['top']); boolean(x['bottom']); integer(x['count'])
        if d is not None and x['count'] > 0 and 'judged' not in marks:
            marks.append('judged')
        newly_measured = [side for side in ['top', 'bottom'] if x[side] and (old is None or not old['domain'][side])]
        if newly_measured:
            if old is None or old['decision'] is None or len(newly_measured) != 1 or x['tool'] not in ['ruler', 'overlay']:
                fail()
            for side in newly_measured:
                if side not in marks:
                    marks.append(side)
        correct = action == 'applyReviseBtn' and all(k in marks for k in ['judged', 'top', 'bottom']) and x['top'] and x['bottom'] and x['tool'] in ['ruler', 'overlay']
    else:
        fields(d, 'F1 F2'); integer(d['F1'], 1); integer(d['F2'], 1)
        fields(x, 'phase senses force view probes exchanged standard')
        integer(x['phase'], 3)
        if x['phase'] < 1:
            fail()
        ordered = ordered_senses(x['senses'], 'eye')
        choice(x['force'], ['light', 'heavy']); choice(x['view'], ['front', 'top'])
        boolean(x['exchanged']); choice(x['standard'], [None, 'color', 'shape', 'size'])
        fields(x['probes'], 'F1 F2')
        for p in x['probes'].values():
            if p is not None:
                fields(p, 'force view'); choice(p['force'], ['light']); choice(p['view'], ['front', 'top'])
        both = all(p and p['view'] == x['view'] for p in x['probes'].values())
        if ordered and all(s in x['senses'] for s in ['eye', 'hand']) and x['phase'] == 1 and 'senses' not in marks:
            marks.append('senses')
        if x['phase'] >= 2 and 'senses' not in marks:
            fail()
        if x['phase'] == 2 and not x['exchanged'] and both and 'before-swap' not in marks:
            marks.append('before-swap')
        if old and x['phase'] == 2 and x['exchanged'] and not old['domain']['exchanged'] and 'before-swap' in marks and not any(x['probes'].values()) and 'swap' not in marks:
            marks.append('swap')
        if x['phase'] == 2 and x['exchanged'] and both and 'swap' in marks and 'comparison' not in marks:
            marks.append('comparison')
        if x['phase'] == 3 and 'comparison' not in marks:
            fail()
        correct = x['phase'] == 3 and x['standard'] is not None and d == {'F1': 0, 'F2': 1}
    return bool(w['started'] and correct)


def apply_page(validator, state, operation):
    page = identity(validator)
    fields(operation, 'name action work')
    if operation['name'] not in ['work', 'submit', 'help'] or state.get('validator') != validator or len(state['attempts']) >= 128:
        fail()
    if not isinstance(operation['action'], str) or not re.fullmatch(r'[\w: .-]{0,120}', operation['action']):
        fail()
    # The original p6 adapter omitted `started`: that page's checkpoint stores
    # it at the top level, unlike other pages. The initial click was invisible
    # to that adapter, so the queued first operation can be a later real input.
    # Preserve the raw event; the ordinary validator still checks its world and
    # refuses a first operation that creates a milestone or completion.
    work = operation['work']
    if (page == 6 and state['lastWork'] is None and operation['name'] == 'work'
            and operation['action'] in {'startExploreBtn', 'leftCard', 'rightCard', 'modeAngleBtn',
                                        'modeProbeBtn', 'forceLightBtn', 'forceHeavyBtn', 'swapBtn',
                                        'resetBtn', 'replayBtn', 'helpBtn'}
            and isinstance(work, dict)
            and set(work) == {'decision', 'domain', 'help', 'first', 'response'}):
        operation = {**operation, 'work': {**work, 'started': True}}
    trial = deepcopy(state)
    correct = evaluate(page, operation['work'], trial, operation['action'])
    w = operation['work']
    if trial['lastWork'] is None and w['started']:
        # The initial start must be recorded before any answer can earn credit.
        if correct or trial['milestones']:
            fail()
    trial['lastWork'] = deepcopy(w)
    if trial['firstAnswer'] is None and w['first'] is not None:
        trial['firstAnswer'] = deepcopy(w['first'])
    trial['helpCount'] = max(trial['helpCount'], w['help'])
    if operation['name'] == 'submit':
        if trial['firstWork'] is None:
            trial['firstWork'] = deepcopy(w)
        trial['attempts'].append({'action': operation['action'], 'work': deepcopy(w), 'taskSatisfied': correct,
                                  'helpCount': trial['helpCount'], 'realSensorySkills': 'unobserved'})
        trial['completed'] = bool(trial['completed'] or correct)
    trial['phase'] = 'complete' if trial['completed'] else 'playing'
    state.clear(); state.update(trial)
