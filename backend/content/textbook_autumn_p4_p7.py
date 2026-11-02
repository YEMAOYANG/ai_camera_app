"""Recompute reported inputs for four Autumn activities, not mastery.

These validators neither consume iframe checkpoints nor trust a client result.
They record bounded client-reported operations; they cannot establish a child's
identity, unaided reading, correct speech, or paper handwriting.
"""
import math

from core.errors import ApiError

VALIDATORS = {'scene-p4': 'autumn-paragraphs.v1', 'scene-p5': 'autumn-characters.v1',
              'scene-p6': 'autumn-strokes-liao-zi.v1', 'scene-p7': 'autumn-sky.v1'}
_MAX = 128
_TOKENS = {'token1', 'token2', 'token3'}
_SLOTS = {'slot1', 'slot2', 'slot3'}
_OBJECTS = [
    ('winter', 'autumn', 'summer'), ('leaf', 'bird', 'weather'), ('change', 'bird', 'single'),
    ('bird', 'tree', 'leaf'), ('tree', 'bird', 'leaf'), ('green', 'yellow', 'red'),
    ('many', 'tree', 'single'), ('from-ground', 'from-tree', 'flying'), ('away', 'still', 'toward'),
    ('standing', 'leaf', 'flying')]
_CORRECT = ('autumn', 'weather', 'change', 'tree', 'leaf', 'yellow', 'single', 'from-tree', 'toward', 'flying')
_GUIDE = {
    '了': (((48, 38), (128, 38), (90, 78)), ((90, 78), (104, 104), (110, 130), (106, 149), (94, 158), (82, 146))),
    '子': (((48, 36), (126, 36), (88, 72)), ((88, 72), (102, 100), (108, 128), (104, 148), (92, 158), (80, 146)),
          ((32, 100), (148, 100))),
}


def _fail(message='互动操作无效，请继续当前练习'):
    raise ApiError('textbook_interaction_operation_invalid', message, 409)


def _record(state, value):
    if len(state['attempts']) >= _MAX:
        _fail('本页练习次数已达到上限')
    state['attempts'].append(value)


def _event(operation, fields):
    if not isinstance(operation, dict) or set(operation) != fields or not isinstance(operation.get('name'), str):
        _fail()
    return operation['name']


def initial_page(validator):
    base = {'phase': 'ready', 'completed': False, 'attempts': [], 'helpCount': 0}
    if validator == VALIDATORS['scene-p4']:
        return {**base, 'slots': {slot: None for slot in sorted(_SLOTS)}}
    if validator == VALIDATORS['scene-p5']:
        return {**base, 'index': 0, 'listenRequested': [], 'placed': {}, 'compareRequested': [], 'compared': False}
    if validator == VALIDATORS['scene-p6']:
        return {**base, 'strokes': {'了': [], '子': []}, 'versions': {'try': {'了': [], '子': []}, 'redo': {'了': [], '子': []}}, 'versionMode': 'try', 'revisions': 0}
    if validator == VALIDATORS['scene-p7']:
        return {**base, 'level': 1, 'blue': 0.0, 'horizon': 0.66, 'choices': {'1': None, '2': None}}
    _fail('互动验证器不可用')


def _common(state, operation):
    if operation == {'name': 'start'} and state['phase'] == 'ready':
        state['phase'] = 'playing'
        return True
    if state['phase'] == 'ready':
        _fail('请先开始当前练习')
    if operation == {'name': 'hint'}:
        if state['helpCount'] >= _MAX:
            _fail('本页帮助次数已达到上限')
        state['helpCount'] += 1
        return True
    return False


def _paragraphs(state, op):
    if _common(state, op): return
    if op == {'name': 'reset'}:
        state.update(slots={slot: None for slot in sorted(_SLOTS)}, phase='playing', completed=False)
    elif set(op) == {'name', 'token'} and op.get('name') == 'return' and isinstance(op.get('token'), str) and op.get('token') in _TOKENS:
        for key in state['slots']:
            if state['slots'][key] == op['token']: state['slots'][key] = None
        state.update(completed=False, phase='playing')
    elif _event(op, {'name', 'token', 'slot'}) == 'place' and op['token'] in _TOKENS and op['slot'] in _SLOTS:
        if state['completed']: _fail('本页已完成，可先重新开始')
        for key in state['slots']:
            if state['slots'][key] == op['token']: state['slots'][key] = None
        state['slots'][op['slot']] = op['token']
        passed = state['slots'] == {'slot1': 'token1', 'slot2': 'token2', 'slot3': 'token3'}
        _record(state, {'token': op['token'], 'slot': op['slot'], 'passed': passed, 'helpCount': state['helpCount']})
        # The page automatically plays its self-check cue when all three
        # slots are filled incorrectly. Record support only after the failed
        # attempt, so the first unaided attempt remains distinguishable.
        if not passed and all(state['slots'].values()):
            state['helpCount'] += 1
        state.update(completed=passed, phase='complete' if passed else 'playing')
    else: _fail()


def _characters(state, op):
    if _common(state, op): return
    if state['completed']: _fail('本页已完成')
    idx = state['index']
    if op == {'name': 'listen'}:
        if idx not in state['listenRequested']: state['listenRequested'].append(idx)
    elif op == {'name': 'reset'} and state['phase'] != 'compare':
        state['placed'].pop(str(idx), None); state['phase'] = 'playing'
    elif set(op) == {'name', 'object'} and op['name'] == 'choose' and op['object'] in _OBJECTS[idx]:
        if state['phase'] == 'compare' or idx not in state['listenRequested'] or str(idx) in state['placed']:
            _fail('请先听本字，再选择图片')
        passed = op['object'] == _CORRECT[idx]
        _record(state, {'index': idx, 'object': op['object'], 'passed': passed,
                        'helpCount': state['helpCount'], 'support': 'picture_and_teacher_audio'})
        if passed:
            state['placed'][str(idx)] = op['object']
            state.update(completed=idx == 9, phase='complete' if idx == 9 else 'feedback')
        else:
            # The page supplies spoken correction after the initial attempt.
            state['helpCount'] += 1
            state['phase'] = 'feedback'
    elif op == {'name': 'next'} and str(idx) in state['placed']:
        if idx == 0 and not state['compared']: state['phase'] = 'compare'
        elif idx < 9: state.update(index=idx + 1, phase='playing')
        else: _fail()
    elif set(op) == {'name', 'value'} and op['name'] == 'compareListen' and state['phase'] == 'compare' and op['value'] in ('qiu', 'hui'):
        if op['value'] not in state['compareRequested']: state['compareRequested'].append(op['value'])
    elif op == {'name': 'compareDone'} and state['phase'] == 'compare' and set(state['compareRequested']) == {'qiu', 'hui'}:
        state.update(compared=True, index=1, phase='playing')
    else: _fail()


def _stroke_valid(points, char, index):
    if len(points) < 3: return False
    path = _GUIDE[char][index]
    distance = lambda a, b: math.hypot(a[0]-b[0], a[1]-b[1])
    length = sum(distance(a, b) for a, b in zip(points, points[1:]))
    expected = sum(distance(a, b) for a, b in zip(path, path[1:]))
    if (length < expected * .65 or length > expected * 1.7 or distance(points[0], path[0]) > 27
            or distance(points[-1], path[-1]) > 27): return False
    cumulative = [0.0]
    for a, b in zip(path, path[1:]): cumulative.append(cumulative[-1] + distance(a, b))
    previous = backwards = 0.0
    for point in points:
        best, progress = math.inf, 0.0
        for i, (a, b) in enumerate(zip(path, path[1:])):
            dx, dy = b[0]-a[0], b[1]-a[1]
            t = max(0.0, min(1.0, ((point[0]-a[0])*dx + (point[1]-a[1])*dy) / (dx*dx + dy*dy)))
            d = distance(point, (a[0] + t*dx, a[1] + t*dy))
            if d < best: best, progress = d, (cumulative[i] + t*distance(a, b))/expected
        if best > 24: return False
        if progress < previous: backwards += previous - progress
        previous = progress
    if backwards > .32: return False
    cursor = 0
    for waypoint in path[1:-1]:
        while cursor < len(points) and distance(points[cursor], waypoint) > 23: cursor += 1
        if cursor == len(points): return False
    return True


def _valid_points(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 256: _fail('笔迹格式无效')
    result = []
    for point in value:
        if not isinstance(point, dict) or set(point) != {'x', 'y'}: _fail('笔迹坐标无效')
        try:
            valid = all(type(point[k]) in (int, float) and math.isfinite(point[k]) and -1_000_000 <= point[k] <= 1_000_000 for k in ('x', 'y'))
        except (OverflowError, TypeError):
            valid = False
        if not valid: _fail('笔迹坐标无效')
        result.append((point['x'], point['y']))
    return result


def _stroke_complete(state):
    return all(len(state['strokes'][char]) == len(paths) and all(
        _stroke_valid(points, char, index) for index, points in enumerate(state['strokes'][char]))
        for char, paths in _GUIDE.items())


def _strokes(state, op):
    if _common(state, op): return
    if op == {'name': 'retry'}:
        state['versions'][state['versionMode']] = {k:list(v) for k,v in state['strokes'].items()}
        state['versions']['redo'] = {'了': [], '子': []}
        state.update(strokes={'了': [], '子': []}, versionMode='redo', completed=False, phase='playing', revisions=state['revisions'] + 1)
    elif set(op) == {'name', 'mode'} and op['name'] == 'version' and op['mode'] in ('try', 'redo'):
        state['versions'][state['versionMode']] = {k:list(v) for k,v in state['strokes'].items()}
        state['versionMode'] = op['mode']; state['strokes'] = {k:list(v) for k,v in state['versions'][op['mode']].items()}
        done = _stroke_complete(state); state.update(completed=done, phase='complete' if done else 'playing')
    elif set(op) == {'name', 'character'} and op['name'] == 'undo' and op['character'] in _GUIDE:
        strokes = state['strokes'][op['character']]
        if not strokes: _fail()
        strokes.pop(); state.update(completed=_stroke_complete(state), phase='playing')
    elif set(op) == {'name', 'character', 'points'} and op['name'] == 'stroke' and op['character'] in _GUIDE:
        char, points = op['character'], _valid_points(op['points'])
        strokes = state['strokes'][char]
        if strokes and not _stroke_valid(strokes[-1], char, len(strokes)-1): strokes.pop()
        if len(strokes) >= len(_GUIDE[char]): _fail()
        index = len(strokes); passed = _stroke_valid(points, char, index); strokes.append(points)
        _record(state, {'character': char, 'strokeIndex': index, 'passed': passed, 'helpCount': state['helpCount']})
        # A failed stroke triggers a direction-specific teacher cue. Do not
        # retroactively mark the failed attempt as helped, but retain support
        # for any subsequent correction.
        if not passed:
            state['helpCount'] += 1
        done = _stroke_complete(state); state.update(completed=done, phase='complete' if done else 'feedback')
    else: _fail()
    state['versions'][state['versionMode']] = {k: [list(stroke) for stroke in v] for k,v in state['strokes'].items()}


def _sky(state, op):
    if _common(state, op): return
    level = state['level']
    if op == {'name': 'blue'}:
        state['blue'] = 0.0 if state['blue'] >= 1 else min(1.0, state['blue'] + .14)
    elif op == {'name': 'height'}:
        state['horizon'] = .52 if state['horizon'] >= .88 else min(.88, state['horizon'] + .06)
    elif op == {'name': 'reset'}:
        state['blue'] = .1 if level == 1 else .15
        state['horizon'] = .66 if level == 1 else .58
        state['choices'][str(level)] = None
    elif set(op) == {'name', 'value'} and op['name'] == 'choose' and op['value'] in ('so', 'both'):
        if state['blue'] < .75 or state['horizon'] < .8: _fail('先调整蓝度和高度')
        state['choices'][str(level)] = op['value']
        _record(state, {'level': level, 'choice': op['value'], 'helpCount': state['helpCount']})
    elif op == {'name': 'nextSky'}:
        if level != 1 or state['blue'] < .75 or state['horizon'] < .8 or state['choices']['1'] is None: _fail()
        state.update(level=2, blue=.15, horizon=.58)
    else: _fail()
    done = state['level'] == 2 and state['blue'] >= .75 and state['horizon'] >= .8 and state['choices']['2'] is not None
    state.update(completed=done, phase='complete' if done else 'playing')


def apply_page(validator, state, operation):
    if not isinstance(state, dict) or not isinstance(operation, dict): _fail()
    handlers = {VALIDATORS['scene-p4']: _paragraphs, VALIDATORS['scene-p5']: _characters,
                VALIDATORS['scene-p6']: _strokes, VALIDATORS['scene-p7']: _sky}
    handler = handlers.get(validator)
    if handler is None: _fail('互动验证器不可用')
    handler(state, operation)
