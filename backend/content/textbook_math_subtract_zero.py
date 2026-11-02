"""Bounded domain evidence for the two frozen subtraction / zero lessons.

The adapter projects real authored objects to stable integers 1..n per scene;
it must never manufacture work from a success flag. Ink uses the actual input
points normalized to [0, 1]. These are client-reported, picture-supported
operations, not proof of identity, independent reading, oral or paper skills.

WORK_FIELDS is the projection contract. No client completion, score, help count
or first-attempt field is accepted. Prediction must precede the visible event.
The server preserves first responses and separates replay, hint, demonstration,
undo and retry. Authored HTML/checkpoint acceptance remains a separate gate.
"""
from copy import deepcopy
import math
import re

from content.textbook_catalog import digest
from content.textbook_math_interaction import fields, integer, choice, fail

EDITION = 'pep-math-g1-upper-2022-standard'
REVISION = 'directory-ede7a8c63c337cf95a03fe79'
NODES = {'0da8a119-4bc0-48c7-9fd7-9dc8c1c1fd34': 'subtract',
         '43bbcbb2-3898-444e-9da5-5302124adc63': 'zero'}
PAGE_COUNTS = {'subtract': 12, 'zero': 14}
WORK_FIELDS = {
    'subtract': {
        1: 'removed remaining prediction',
        2: 'removed remaining answer',
        3: 'total removed remaining equation links',
        4: 'total removed remaining symbol strokes mode',
        5: 'removed remaining pairs',
        6: 'removed remaining equation evidence',
        7: 'removed remaining method counted countdown answer',
        8: 'groupA groupB removed remaining answer',
        9: 'removedA remainingA removedB remainingB prediction',
        10: 'removed remaining answer',
        11: 'story saved',
        12: 'story saved links sourceWorkSha256 storyVersion recordVersion',
    },
    'zero': {
        1: 'removed remaining answer',
        2: 'context objects position meaning',
        3: 'order quantities',
        4: 'mode strokes',
        5: 'removed remaining equation links',
        6: 'total removed remaining prediction',
        7: 'incoming remaining gateOpen prediction',
        8: 'removed remaining executed equation',
        9: 'context total changed remaining executed operator equation',
        10: 'operator changed remaining executed equation',
        11: 'total operator changed remaining executed equation',
        12: 'context objects position meaning',
        13: 'story saved',
        14: 'story saved zeroRole sourceWorkSha256 storyVersion recordVersion',
    },
}
TASKS = {kind: {p: ['task'] for p in range(1, count+1)} for kind, count in PAGE_COUNTS.items()}
TASKS['zero'].update({2: ['harbour', 'ruler'], 4: ['trace', 'free'],
                      9: ['incoming', 'departing'], 10: ['add', 'subtract'],
                      11: ['add', 'subtract', 'different-n'], 12: ['tools', 'path']})
PREDICTION_PAGES = {('subtract', 1), ('subtract', 9), ('zero', 6), ('zero', 7)}
SUPPORT = ('replay', 'hint', 'demonstration')
OPERATIONS = ('work', 'submit', 'predict', *SUPPORT, 'undo', 'retry')
BOUNDARY = 'client_reported_picture_supported_practice'


def validators(binding):
    if (not isinstance(binding, dict) or set(binding) != {'editionId', 'revisionId', 'nodeId'}
            or binding['editionId'] != EDITION or binding['revisionId'] != REVISION):
        return None
    kind = NODES.get(binding['nodeId'])
    return {f'scene-p{p}': f'math-{kind}-p{p}.v1'
            for p in range(1, PAGE_COUNTS[kind]+1)} if kind else None


def identity(validator):
    match = re.fullmatch(r'math-(subtract|zero)-p([1-9]|1[0-4])\.v1', validator or '')
    if not match or int(match[2]) > PAGE_COUNTS[match[1]]:
        fail()
    return match[1], int(match[2])


def initial_page(validator):
    kind, _ = identity(validator)
    return {'kind': f'math-{kind}', 'validator': validator, 'phase': 'playing',
            'completed': False, 'lastWork': None, 'workVersion': 0, 'attempts': [],
            'firstAttempts': {}, 'firstPredictions': {}, 'latestPredictions': {},
            'passedTasks': [], 'support': dict.fromkeys(SUPPORT, 0),
            'undoCount': 0, 'retryCount': 0, 'exposureCount': 0, 'history': [],
            'evidenceBoundary': BOUNDARY, 'oralSkill': 'unobserved',
            'paperHandwriting': 'unobserved'}


def ids(value, maximum=5):
    if not isinstance(value, list) or len(value) > maximum:
        fail()
    for item in value:
        integer(item, 1, maximum)
    if len(set(value)) != len(value):
        fail()
    return set(value)


def number(value):
    if value is not None:
        integer(value, 0, 5)
    return value


def boolean(value):
    if type(value) is not bool:
        fail()
    return value


def removal(total, removed, remaining):
    original = set(range(1, total+1))
    gone, rest = ids(removed), ids(remaining)
    if gone & rest or gone | rest != original:
        fail()
    return len(gone), len(rest)


def equation(value, a, b, c):
    fields(value, 'whole change result')
    for item in value.values():
        number(item)
    return value == {'whole': a, 'change': b, 'result': c}


def links(value):
    fields(value, 'whole change result')
    for item in value.values():
        if item is not None:
            choice(item, ['before', 'removed', 'remaining'])
    return value == {'whole': 'before', 'change': 'removed', 'result': 'remaining'}


def ink(strokes):
    if not isinstance(strokes, list) or len(strokes) > 12:
        fail()
    if sum(len(s) for s in strokes if isinstance(s, list)) > 1200:
        fail()
    for stroke in strokes:
        if not isinstance(stroke, list) or not 2 <= len(stroke) <= 600:
            fail()
        for point in stroke:
            if (not isinstance(point, list) or len(point) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in point)):
                fail()
    return strokes


def minus_trace(strokes):
    ink(strokes)
    if len(strokes) != 1:
        return False
    points = strokes[0]; a, b = points[0], points[-1]
    return (b[0]-a[0] >= .25 and abs(b[1]-a[1]) <= .12
            and all(abs(p[1]-(a[1]+b[1])/2) <= .12 for p in points)
            and all(points[i+1][0] >= points[i][0]-.08 for i in range(len(points)-1)))


def zero_trace(strokes):
    """Generous shape/direction check, not a paper-handwriting grade."""
    ink(strokes)
    if len(strokes) != 1 or len(strokes[0]) < 12:
        return False
    points = strokes[0]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    width, height = max(xs)-min(xs), max(ys)-min(ys)
    if not (.2 <= width <= .85 and .4 <= height <= .95 and height >= width*1.05):
        return False
    cx, cy = (max(xs)+min(xs))/2, (max(ys)+min(ys))/2
    rx, ry = width/2, height/2
    if (abs(points[0][0]-cx) > width*.25 or points[0][1] > min(ys)+height*.18
            or math.dist(points[0], points[-1]) > min(width, height)*.25):
        return False
    radii = [math.hypot((x-cx)/rx, (y-cy)/ry) for x, y in points]
    # Reject zigzags through the middle and sparse polygons across the oval.
    if (any(not .55 <= r <= 1.45 for r in radii)
            or max(math.dist(a, b) for a, b in zip(points, points[1:])) > height*.4):
        return False
    left = next((i for i, (x, y) in enumerate(points) if x < cx-rx*.65 and abs(y-cy) < ry*.65), None)
    bottom = next((i for i, (_, y) in enumerate(points) if y > cy+ry*.7), None)
    right = next((i for i, (x, y) in enumerate(points) if x > cx+rx*.65 and abs(y-cy) < ry*.65), None)
    # Screen y grows downwards: top -> left -> bottom -> right has negative area.
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]))
    angles = [math.atan2((y-cy)/ry, (x-cx)/rx) for x, y in points]
    turns = [(b-a+math.pi) % (2*math.pi)-math.pi for a, b in zip(angles, angles[1:])]
    return bool(None not in (left, bottom, right) and left < bottom < right
                and area < -width*height*.65 and -2.5*math.pi < sum(turns) < -1.5*math.pi
                and sum(abs(v) for v in turns) < 2.8*math.pi)


def subtraction_story(story):
    fields(story, 'total removed remaining equation')
    total = integer(story['total'], 2, 5)
    gone, rest = removal(total, story['removed'], story['remaining'])
    return equation(story['equation'], total, gone, rest) and 0 < gone < total


def zero_event(total, operator, changed, remaining):
    choice(operator, ['add', 'subtract'])
    if operator == 'subtract':
        count, rest = removal(total, changed, remaining)
    else:
        original = set(range(1, total+1)); added, result = ids(changed, 10), ids(remaining, 10)
        if added & original or result != original | added:
            fail()
        count, rest = len(added), len(result)
    return count, rest


def zero_story(story):
    fields(story, 'type total operator changed remaining equation')
    typ = choice(story['type'], ['empty', 'all-left', 'no-arrivals', 'no-departures'])
    total = integer(story['total'], 0, 5)
    operator = choice(story['operator'], ['add', 'subtract'])
    count, rest = zero_event(total, operator, story['changed'], story['remaining'])
    eq = equation(story['equation'], total, count, rest)
    if typ == 'empty':
        return eq and total == count == rest == 0
    if typ == 'all-left':
        return eq and operator == 'subtract' and total > 0 and count == total and rest == 0
    return eq and operator == ('add' if typ == 'no-arrivals' else 'subtract') and count == 0 and rest == total


def saved_story(work, kind):
    check = subtraction_story if kind == 'subtract' else zero_story
    correct = check(work['story'])
    if work['saved'] is not None:
        check(work['saved'])
    return correct and work['saved'] == work['story']


def source_story(work, previous):
    if (not isinstance(previous, dict) or previous.get('completed') is not True
            or not previous.get('lastWork') or previous['lastWork'].get('saved') is None
            or work['sourceWorkSha256'] != digest(previous['lastWork']['saved'])
            or work['story'] != previous['lastWork']['saved']
            or work['saved'] != previous['lastWork']['saved']):
        fail()
    integer(work['storyVersion'], 1, 128); integer(work['recordVersion'], 1, 128)
    return work['storyVersion'] == work['recordVersion']


def source_evidence(previous):
    return {'sourceWorkSha256': digest(previous['lastWork']['saved']),
            'support': deepcopy(previous['support']), 'priorAttempts': len(previous['attempts']),
            'assistanceOutsideApp': 'unobserved'}


def subtract_work(page, w, previous):
    extra = {}
    if page in (1, 2, 6, 7, 10):
        total, target = {1: (5, 2), 2: (4, 1), 6: (5, 2), 7: (4, 1), 10: (3, 1)}[page]
        gone, rest = removal(total, w['removed'], w['remaining'])
        if page == 1:
            number(w['prediction'])
            return 'task', gone == target and w['prediction'] == rest, extra
        if page in (2, 10):
            number(w['answer'])
            return 'task', gone == target and w['answer'] == rest, extra
        if page == 6:
            if w['evidence'] is not None:
                choice(w['evidence'], ['before', 'removed', 'remaining'])
            return 'task', equation(w['equation'], total, gone, rest) and gone == target and w['evidence'] == 'before', extra
        choice(w['method'], ['count-remaining', 'count-back'])
        counted = ids(w['counted']); number(w['answer'])
        if not isinstance(w['countdown'], list) or len(w['countdown']) > 6:
            fail()
        for n in w['countdown']:
            integer(n, 0, 5)
        process = counted == set(w['remaining']) if w['method'] == 'count-remaining' else w['countdown'] == [4, 3]
        return 'task', gone == target and w['answer'] == rest and process, extra
    if page in (3, 4):
        total = integer(w['total'], 2, 5)
        gone, rest = removal(total, w['removed'], w['remaining'])
        if page == 3:
            eq, mapped = equation(w['equation'], total, gone, rest), links(w['links'])
            return 'task', 0 < gone < total and eq and mapped, extra
        if w['symbol'] is not None:
            choice(w['symbol'], ['add', 'subtract'])
        mode = choice(w['mode'], ['trace', 'point'])
        extra = {'screenTraceMatches': minus_trace(w['strokes']), 'motorEvidence': 'screen-input-only'}
        extra['writingEvidence'] = 'screen-trace-only' if mode == 'trace' else 'unobserved'
        return 'task', 0 < gone < total and w['symbol'] == 'subtract' and (mode == 'point' or extra['screenTraceMatches']), extra
    if page == 5:
        gone, rest = removal(5, w['removed'], w['remaining'])
        pairs = w['pairs']
        if not isinstance(pairs, list) or len(pairs) > 3:
            fail()
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2:
                fail()
            integer(pair[0], 1, 5); integer(pair[1], 1, 3)
        a, b = [p[0] for p in pairs], [p[1] for p in pairs]
        if len(set(a)) != len(a) or len(set(b)) != len(b) or not set(a) <= set(w['remaining']):
            fail()
        return 'task', gone == 2 and rest == 3 and set(a) == set(w['remaining']) and set(b) == {1, 2, 3}, extra
    if page == 8:
        a, b = ids(w['groupA']), ids(w['groupB'])
        if a & b or a | b != {1, 2, 3, 4, 5}:
            fail()
        gone, rest = removal(5, w['removed'], w['remaining']); number(w['answer'])
        return 'task', len(a) == 3 and len(b) == 2 and set(w['removed']) == a and w['answer'] == rest == 2, extra
    if page == 9:
        ga, ra = removal(5, w['removedA'], w['remainingA'])
        gb, rb = removal(5, w['removedB'], w['remainingB'])
        if w['prediction'] is not None:
            choice(w['prediction'], ['A', 'B', 'same'])
        return 'task', (ga, gb, ra, rb) == (1, 3, 4, 2) and w['prediction'] == 'A', extra
    correct = saved_story(w, 'subtract')
    if page == 12:
        mapped, consistent = links(w['links']), source_story(w, previous)
        correct = mapped and consistent and correct
        extra['sourceEvidence'] = source_evidence(previous)
    return 'task', correct, extra


def zero_work(page, w, previous):
    extra = {}
    if page in (1, 5, 6, 8):
        total = integer(w['total'], 1, 5) if page == 6 else {1: 2, 5: 4, 8: 2}[page]
        gone, rest = removal(total, w['removed'], w['remaining'])
        if page == 1:
            number(w['answer'])
            return 'task', gone == 2 and w['answer'] == rest == 0, extra
        if page == 5:
            eq, mapped = equation(w['equation'], total, gone, rest), links(w['links'])
            return 'task', gone == total and eq and mapped, extra
        if page == 6:
            number(w['prediction'])
            return 'task', gone == total and w['prediction'] == rest == 0, extra
        boolean(w['executed'])
        return 'task', equation(w['equation'], total, gone, rest) and gone == 0 and w['executed'], extra
    if page in (2, 12):
        empty, origin = ('harbour', 'ruler') if page == 2 else ('tools', 'path')
        context = choice(w['context'], [empty, origin]); objects = ids(w['objects'])
        integer(w['position'], 0, 5)
        if w['meaning'] is not None:
            choice(w['meaning'], ['empty', 'origin'])
        if objects != (set() if context == empty else {1}) or w['position'] != 0:
            fail()
        return context, w['meaning'] == ('empty' if context == empty else 'origin'), extra
    if page == 3:
        if not isinstance(w['order'], list) or len(w['order']) != 6 or not isinstance(w['quantities'], list) or len(w['quantities']) != 6:
            fail()
        for n in w['order']:
            integer(n, 0, 5)
        if len(set(w['order'])) != 6:
            fail()
        counts = [len(ids(items)) for items in w['quantities']]
        return 'task', w['order'] == counts == list(range(6)), extra
    if page == 4:
        mode = choice(w['mode'], ['trace', 'free'])
        correct = zero_trace(w['strokes'])
        return mode, correct, {'screenTraceMatches': correct, 'motorEvidence': 'screen-input-only'}
    if page == 7:
        added, rest = zero_event(3, 'add', w['incoming'], w['remaining'])
        boolean(w['gateOpen']); number(w['prediction'])
        return 'task', added == 0 and w['gateOpen'] and w['prediction'] == rest == 3, extra
    if page in (9, 10, 11):
        total = 0 if page == 10 else integer(w['total'], 0, 5)
        operator = choice(w['operator'], ['add', 'subtract'])
        count, rest = zero_event(total, operator, w['changed'], w['remaining'])
        boolean(w['executed'])
        eq = equation(w['equation'], total, count, rest)
        task = operator
        semantic = True
        if page == 9:
            task = choice(w['context'], ['incoming', 'departing'])
            semantic = operator == ('add' if task == 'incoming' else 'subtract')
        return task, count == 0 and rest == total and w['executed'] and semantic and eq, extra
    correct = saved_story(w, 'zero')
    if page == 14:
        role = w['zeroRole']
        if role is not None:
            choice(role, ['whole', 'change', 'result', 'origin'])
        consistent = source_story(w, previous)
        correct = correct and consistent and role not in (None, 'origin') and w['story']['equation'][role] == 0
        extra['sourceEvidence'] = source_evidence(previous)
    return 'task', correct, extra


def prediction_before(kind, page, w):
    if kind == 'subtract':
        return not w['removed'] if page == 1 else not w['removedA'] and not w['removedB']
    return not w['removed'] if page == 6 else not w['gateOpen'] and not w['incoming']


def reconcile_zero_p11_trials(state):
    """Project completed trials from accepted attempts, without adding evidence.

    P11 is a collection of independent experiments: editing a later draft must
    not invalidate an earlier completed experiment.  Rechecking the recorded
    work also permits a safe read-only projection of an older affected state.
    """
    if not isinstance(state, dict) or state.get('validator') != 'math-zero-p11.v1':
        fail()
    attempts, history = state.get('attempts'), state.get('history')
    if (not isinstance(attempts, list) or len(attempts) > 128
            or not isinstance(history, list) or len(history) > 512):
        fail()
    submits = []
    for item in history:
        fields(item, 'name task workVersion work support')
        if item['name'] not in OPERATIONS or item['name'] == 'predict':
            fail()
        if item['name'] == 'submit':
            submits.append(item)
    if len(submits) != len(attempts):
        fail()
    verified = []
    # Check all attempts, even those outside the page's visible 64-trial window.
    for index, (attempt, recorded) in enumerate(zip(attempts, submits)):
        if not isinstance(attempt, dict) or type(attempt.get('correct')) is not bool:
            fail()
        for entry in (attempt, recorded):
            if (type(entry.get('workVersion')) is not int or not 1 <= entry['workVersion'] <= len(history)
                    or not isinstance(entry.get('support'), dict)
                    or set(entry['support']) != set(SUPPORT)
                    or any(type(v) is not int or not 0 <= v <= len(history) for v in entry['support'].values())):
                fail()
            work = entry.get('work')
            fields(work, WORK_FIELDS['zero'][11])
            task, correct, _ = zero_work(11, work, None)
            if task != entry.get('task') or correct is not attempt['correct']:
                fail()
        if any(attempt.get(key) != recorded.get(key) for key in ('task', 'work', 'workVersion', 'support')):
            fail()
        # The authored page retains the most recent 64 trials.
        if index >= len(attempts) - 64 and attempt['correct']:
            verified.append(attempt['work'])
    tasks = {w['operator'] for w in verified}
    if len({w['total'] for w in verified}) >= 2 and {'add', 'subtract'} <= tasks:
        tasks.add('different-n')
    state['passedTasks'] = [task for task in TASKS['zero'][11] if task in tasks]
    state['completed'] = len(state['passedTasks']) == len(TASKS['zero'][11])
    state['phase'] = 'complete' if state['completed'] else 'playing'


def apply_page(validator, state, operation, *, previous=None):
    """Apply atomically; malformed or unsupported projections leave state intact."""
    kind, page = identity(validator)
    fields(operation, 'name work')
    name = choice(operation['name'], OPERATIONS)
    if state.get('validator') != validator or len(state['attempts']) >= 128 or len(state['history']) >= 512:
        fail()
    w = operation['work']; fields(w, WORK_FIELDS[kind][page])
    task, correct, extra = subtract_work(page, w, previous) if kind == 'subtract' else zero_work(page, w, previous)
    if task not in TASKS[kind][page]:
        fail()
    nxt = deepcopy(state)
    changed = nxt['lastWork'] != w
    if name in SUPPORT and nxt['lastWork'] is not None and changed:
        fail()  # Replay/help itself must not mutate, reset or solve the scene.
    if name == 'predict':
        if (kind, page) not in PREDICTION_PAGES or w['prediction'] is None:
            fail()
        after_reveal = not prediction_before(kind, page, w)
        if after_reveal:
            # A child may revise a prediction while keeping the revealed world
            # visible. This is a revision, never a new independent prediction.
            # The operation cannot also move objects or change the experiment.
            previous_work = nxt['lastWork']
            if (task not in nxt['firstPredictions'] or not previous_work
                    or nxt['exposureCount'] < 1
                    or {k: v for k, v in previous_work.items() if k != 'prediction'}
                    != {k: v for k, v in w.items() if k != 'prediction'}):
                fail()
        prediction = {'value': w['prediction'], 'work': deepcopy(w), 'support': deepcopy(nxt['support']),
                      'priorExposure': nxt['exposureCount'], 'afterReveal': after_reveal,
                      'priorAttempts': len(nxt['attempts']), 'evidenceBoundary': BOUNDARY}
        nxt['firstPredictions'].setdefault(task, deepcopy(prediction))
        nxt['latestPredictions'][task] = prediction
    if name == 'submit' and (kind, page) in PREDICTION_PAGES:
        prediction = nxt['latestPredictions'].get(task)
        if not prediction or prediction['value'] != w['prediction']:
            fail()
        if kind == 'zero' and page == 6 and prediction['work']['total'] != w['total']:
            fail()
    if kind == 'zero' and page == 4 and name == 'submit' and task == 'free' and 'trace' not in nxt['passedTasks']:
        fail()
    if ((kind, page) in PREDICTION_PAGES and not prediction_before(kind, page, w)
            and (nxt['lastWork'] is None or prediction_before(kind, page, nxt['lastWork']))):
        # Merely revealing then undoing is still exposure, even without submit.
        nxt['exposureCount'] += 1
    if changed:
        nxt['workVersion'] += 1
        # A changed current answer/work must be checked again, even after success.
        if task in nxt['passedTasks']:
            nxt['passedTasks'].remove(task)
    nxt['lastWork'] = deepcopy(w)
    if name in SUPPORT:
        nxt['support'][name] += 1
    if name in ('undo', 'retry'):
        nxt[name+'Count'] += 1
    if name == 'submit':
        attempt = {'task': task, 'work': deepcopy(w), 'correct': bool(correct),
                   'workVersion': nxt['workVersion'], 'support': deepcopy(nxt['support']),
                   'retryCount': nxt['retryCount'], 'undoCount': nxt['undoCount'],
                   'priorAttempts': sum(a['task'] == task for a in nxt['attempts']),
                   'priorPageAttempts': len(nxt['attempts']),
                   'priorReveals': nxt['exposureCount'],
                   'pictureSupport': True, 'assistanceOutsideApp': 'unobserved', **extra}
        nxt['firstAttempts'].setdefault(task, deepcopy(attempt))
        nxt['attempts'].append(attempt)
        if correct and task not in nxt['passedTasks']:
            nxt['passedTasks'].append(task)
    nxt['history'].append({'name': name, 'task': task, 'workVersion': nxt['workVersion'],
                           'work': deepcopy(w), 'support': deepcopy(nxt['support'])})
    if kind == 'zero' and page == 11:
        reconcile_zero_p11_trials(nxt)
    nxt['completed'] = set(nxt['passedTasks']) == set(TASKS[kind][page])
    nxt['phase'] = 'complete' if nxt['completed'] else 'playing'
    state.clear(); state.update(nxt)


def invalidate_changed_story(scenes, validator):
    """Changing a saved source invalidates its later explanation, not history."""
    kind, page = identity(validator)
    if page != (11 if kind == 'subtract' else 13):
        return
    source = scenes.get(f'scene-p{page}', {})
    target = scenes.get(f'scene-p{page+1}', {})
    work = target.get('lastWork')
    if work and (source.get('completed') is not True
                 or work['sourceWorkSha256'] != digest(source['lastWork']['saved'])):
        target['completed'] = False
        target['phase'] = 'playing'
        target['passedTasks'] = []


def story_source_context(scenes, kind):
    """Derive the next page's story only from authenticated server state."""
    source_page = 11 if kind == 'subtract' else 13
    source_id = f'scene-p{source_page}'
    source = scenes.get(source_id, {})
    last = source.get('lastWork')
    available = bool(source.get('completed') is True and isinstance(last, dict)
                     and last.get('saved') is not None)
    saved = None
    if available:
        if not saved_story(last, kind):
            fail()
        saved = deepcopy(last['saved'])
    return {f'scene-p{source_page+1}': {
        'schemaVersion': 'mira.math-story-source.v1', 'sourceSceneId': source_id,
        'available': available, 'sourceWorkSha256': digest(saved) if available else None,
        'saved': saved}}
