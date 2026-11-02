"""Bounded classroom-command practice; never infer spoken accuracy or mastery.

The server recomputes each submitted pose, object state or route. Client flags,
checkpoints, replay and self-reported speech cannot grant correctness.
"""
from copy import deepcopy
import math
import re

from core.errors import ApiError

BINDING = {'editionId': 'smartedu-english-six-year-g1-upper-sync-af05bc77',
           'revisionId': '20260928-metadata-1',
           'nodeId': '316c0483-c742-34be-a40f-2f508379017a'}
VALIDATORS = {f'scene-p{i}': f'english-classroom-p{i}.v1' for i in range(2, 10)}
COMMANDS = {2: ['stand', 'sit', 'sit', 'stand'], 3: ['door', 'window', 'window', 'door'],
            5: ['stand', 'sit', 'stand', 'sit'], 6: ['door', 'window', 'stand', 'sit'],
            7: ['stand', 'sit', 'door', 'window'], 8: ['window', 'stand', 'door', 'sit'],
            9: ['sit', 'door', 'stand', 'window']}
ROUTES = [['stand', 'door', 'window'], ['window', 'sit', 'door']]
NAMES = {'stand', 'sit', 'door', 'window'}


def fail():
    raise ApiError('textbook_interaction_operation_invalid', '英语互动记录与本课任务不一致', 409)


def validators(binding):
    return VALIDATORS if binding == BINDING else None


def identity(validator):
    match = re.fullmatch(r'english-classroom-p([2-9])\.v1', validator or '')
    if not match:
        fail()
    return int(match[1])


def initial_page(validator):
    identity(validator)
    return {'kind': 'english-classroom', 'validator': validator, 'phase': 'playing',
            'completed': False, 'lastWork': None, 'attempts': [], 'passedTasks': [],
            'helpCount': 0, 'evidenceBoundary': 'client_reported_picture_supported_practice_not_speech_assessment'}


def integer(value, high):
    if type(value) is not int or not 0 <= value <= high:
        fail()
    return value


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        fail()


def unit(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        fail()
    return value


def validate_work(page, w):
    fields(w, 'round seed started poses door window selected turnSwap lastAction route oral chosen')
    r = integer(w['round'], 1 if page == 4 else 3)
    integer(w['seed'], 999999); integer(w['selected'], 1); integer(w['turnSwap'], 1)
    if type(w['started']) is not bool or not isinstance(w['poses'], list) or len(w['poses']) != 2:
        fail()
    for value in [*w['poses'], w['door'], w['window']]:
        unit(value)
    if (not isinstance(w['chosen'], str) or w['chosen'] not in NAMES
            or w['oral'] not in ['none', 'chosen', 'waiting', 'self-reported']):
        fail()
    action = w['lastAction']
    if action is not None:
        fields(action, 'cmd actor'); integer(action['actor'], 1)
        if not isinstance(action['cmd'], str) or action['cmd'] not in NAMES:
            fail()
    if not isinstance(w['route'], list) or len(w['route']) > 3:
        fail()
    for step in w['route']:
        if step is not None:
            fields(step, 'cmd actor'); integer(step['actor'], 1)
            if not isinstance(step['cmd'], str) or step['cmd'] not in NAMES:
                fail()
    if not w['started']:
        return r, False, 'not_started'
    if page == 4:
        correct = len(w['route']) == 3 and all(step and step['actor'] == 0 and step['cmd'] == target
            for step, target in zip(w['route'], ROUTES[r]))
        return r, correct, 'route_correct' if correct else 'route_mismatch'
    # Creative oral practice has no microphone capture or pronunciation score.
    if page == 7:
        return r, w['oral'] == 'self-reported', 'self_reported_practice_not_assessed'
    target = COMMANDS[page][r]
    actor = (r + w['turnSwap']) % 2 if page == 5 else (w['seed'] + r) % 2 if page in [8, 9] else 0
    if action is None:
        return r, False, 'no_action'
    if target in ['stand', 'sit']:
        if action['actor'] != actor:
            return r, False, 'wrong_person'
        if abs(w['poses'][actor] - (1 if target == 'stand' else 0)) > .1:
            return r, False, 'wrong_pose'
        correct = w['door'] <= .1 and w['window'] <= .1
    else:
        if w[target] < .85:
            return r, False, 'wrong_object'
        correct = w['window' if target == 'door' else 'door'] <= .1
    return r, correct, 'correct' if correct else 'extra_open_object'


def apply_page(validator, state, operation):
    page = identity(validator)
    fields(operation, 'name work')
    if operation['name'] not in ['work', 'submit', 'help'] or state.get('validator') != validator or len(state['attempts']) >= 128:
        fail()
    w = operation['work']
    r, correct, reason = validate_work(page, w)
    old = state['lastWork']
    if old is not None and old['seed'] != w['seed']:
        fail()
    # Every preceding round must have a recorded attempt that met its task.
    if any(i not in state['passedTasks'] for i in range(r)):
        fail()
    state['lastWork'] = deepcopy(w)
    if operation['name'] == 'help':
        state['helpCount'] += 1
    elif operation['name'] == 'submit':
        state['attempts'].append({'round': r, 'work': deepcopy(w), 'correct': bool(correct) if page != 7 else None,
            'practiceCompleted': bool(correct), 'reason': reason, 'helpCount': state['helpCount'],
            'oralAccuracy': 'unobserved', 'assistanceOutsideApp': 'unobserved'})
        if correct and r not in state['passedTasks']:
            state['passedTasks'].append(r)
    state['completed'] = set(state['passedTasks']) == set(range(2 if page == 4 else 4))
    state['phase'] = 'complete' if state['completed'] else 'playing'
