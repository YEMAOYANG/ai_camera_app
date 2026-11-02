"""Recompute the fixed sensory-lab course from bounded reported actions.

This is picture-supported simulation evidence. It proves neither real touching,
smelling/tasting, hearing ability, child identity nor independent mastery.
Completion and first guesses are derived here, never accepted from a checkpoint.
"""
from copy import deepcopy
import re

from core.errors import ApiError
from content.textbook_catalog import canonical

BINDING = {'editionId': 'smartedu-science-six-year-g1-upper-64e96b25',
           'revisionId': 'directory-0e2e092fb846ac493525aece',
           'nodeId': '417d307a-c422-470e-92b6-6269bcb67c1b'}
PAGES = (2, 3, 4, 5, 7, 8, 9, 10, 11, 12)
VALIDATORS = {f'scene-p{p}': f'science-sensory-p{p}.v1' for p in PAGES}
BOUNDARY = 'client_reported_picture_supported_simulation_not_real_sensory_or_mastery'


def fail():
    raise ApiError('textbook_interaction_operation_invalid', '实验操作与当前页面不一致，请重新进入课堂', 409)


def validators(binding):
    return VALIDATORS if binding == BINDING else None


def page_number(validator):
    if validator not in VALIDATORS.values():
        fail()
    return int(re.fullmatch(r'science-sensory-p(\d+)\.v1', validator)[1])


def fresh_work():
    return dict(started=False, phase=0, selected='', channels=[], clues=[], excluded=[],
                guess='', firstGuess='', revealed=False, revised=False, rotation=0,
                force=1, probes=[], direction=0, heard=[], links={}, route=[], robot=0, help=0)


def initial_page(validator):
    page_number(validator)
    return dict(kind='science-sensory', validator=validator, phase='ready', completed=False,
                lastWork=None, attempts=[], helpCount=0, evidenceBoundary=BOUNDARY)


def toggle(values, item):
    if item in values:
        values.remove(item)
    else:
        values.append(item)


def add(values, item):
    if item not in values:
        values.append(item)


def transition(page, w, action):
    """Only domain actions are inputs. Reveal and correction order is enforced."""
    if action == 'start':
        if w['started']:
            fail()
        w['started'] = True
        return 'started'
    if action == 'reset':
        w.clear(); w.update(fresh_work())
        return 'reset_without_erasing_history'
    if not w['started']:
        fail()
    if action in ('help', 'replay'):
        if action == 'help':
            w['help'] += 1
        return 'assisted_replay'
    if page == 2:
        if action in ('nose', 'tongue'):
            return 'unsafe_blocked'
        if action not in ('eye', 'ear', 'hand'):
            fail()
        toggle(w['channels'], action)
        return 'safe_route_changed'
    if page == 3:
        if action not in ('eye', 'ear', 'hand'):
            fail()
        add(w['clues'], action)
        return 'virtual_clue_collected'
    if page == 4:
        if action not in ('bell', 'ball', 'chime'):
            fail()
        w['guess'] = action
        if action != 'chime':
            add(w['excluded'], action)
        return 'compatible' if action == 'chime' else 'conflicting_clue'
    if page == 5:
        if action in ('bell', 'ball', 'chime'):
            w['guess'] = action
            w['firstGuess'] = w['firstGuess'] or action
            return 'revised_after_reveal' if w['revealed'] else 'unverified_guess'
        if action == 'open' and not w['revealed']:
            if w['firstGuess']:
                w['revealed'] = True
                return 'revealed'
            return 'guess_required'
        if action == 'revise' and w['revealed']:
            w['revised'] = True
            return 'verified' if w['guess'] == 'chime' else 'conflict_remains'
        fail()
    if page == 7:
        if action == 'rotate':
            w['rotation'] = (w['rotation'] + 1) % 8
            return 'rotated'
        traits = dict(eye='colour', hand='texture', nose='smell', tongue='taste')
        if action not in traits:
            fail()
        add(w['clues'], traits[action])
        return 'teacher_information' if action in ('nose', 'tongue') else 'virtual_observation'
    if page == 8:
        if action == 'probe':
            w['probes'] = ['stoneA', 'stoneB']; w['phase'] = 1
            return 'same_probe_same_force'
        if action not in ('stoneA', 'stoneB'):
            fail()
        w['selected'] = action
        return 'selected_before_scan' if not w['phase'] else 'rougher' if action == 'stoneA' else 'smoother'
    if page == 9:
        if action in ('left', 'right'):
            w['direction'] = max(-1, min(1, w['direction'] + (-1 if action == 'left' else 1)))
            return 'changed_direction'
        if action == 'listen':
            add(w['heard'], ['wind', 'bird', 'water'][w['direction'] + 1])
            return 'client_reported_simulation_ended'
        if action not in ('wind', 'bird', 'water'):
            fail()
        w['guess'] = action
        return 'matched' if len(w['heard']) == 3 and action == 'bird' else 'comparison_incomplete_or_wrong'
    if page == 10:
        if action in ('colour', 'texture', 'taste'):
            w['selected'] = action
            return 'selected_trait'
        if action not in ('source', 'infer'):
            fail()
        if not w['selected']:
            return 'trait_required'
        w['links'][w['selected']] = action
        expected = 'infer' if w['selected'] == 'taste' else 'source'
        return 'source_supported' if action == expected else 'source_conflict'
    if page == 11:
        if action in ('bump', 'tone', 'paint'):
            toggle(w['route'], action); w['robot'] = 0
            return 'route_changed'
        if action != 'test':
            fail()
        w['robot'] = 5 if {'bump', 'tone'} <= set(w['route']) else 2 if {'bump', 'tone'} & set(w['route']) else 0
        return 'arrived' if w['robot'] == 5 else 'stopped'
    if action in ('eye', 'ear', 'hand', 'tongue') and w['phase'] < 2:
        if action == 'tongue':
            return 'unsafe_blocked'
        add(w['clues'], action)
        if len(w['clues']) == 3:
            w['phase'] = 2
        return 'new_object_clue'
    if action in ('ball', 'bell', 'stoneA') and w['phase'] == 2:
        w['guess'] = action; w['firstGuess'] = w['firstGuess'] or action
        return 'revised_after_reveal' if w['revealed'] else 'transfer_guess'
    if action != 'verify':
        fail()
    if len(w['clues']) < 3:
        return 'more_clues_required'
    if not w['guess']:
        return 'guess_required'
    if not w['revealed']:
        w['revealed'] = True
        return 'revealed_new_object'
    w['revised'] = w['guess'] != w['firstGuess']
    return 'verified_new_object' if w['guess'] == 'ball' else 'conflict_remains'


def outcome(page, w, action, previous):
    if not w['started']:
        return False
    if page == 2:
        return set(w['channels']) == {'eye', 'ear', 'hand'}
    if page == 3:
        return len(w['clues']) == 3
    if page == 4:
        return w['guess'] == 'chime'
    if page == 5:
        return w['revealed'] and w['guess'] == 'chime' and (action == 'revise' or previous)
    if page == 7:
        return len(w['clues']) == 4 and w['rotation'] > 0
    if page == 8:
        return w['phase'] == 1 and w['selected'] == 'stoneA' and (action == 'stoneA' or previous)
    if page == 9:
        return len(w['heard']) == 3 and w['guess'] == 'bird' and (action == 'bird' or previous)
    if page == 10:
        return w['links'] == dict(colour='source', texture='source', taste='infer')
    if page == 11:
        return w['robot'] == 5
    return w['revealed'] and w['guess'] == 'ball' and (action == 'verify' or previous)


def apply_page(validator, state, operation):
    page = page_number(validator)
    if (not isinstance(operation, dict) or set(operation) != {'name', 'action', 'work'}
            or operation['name'] != 'act' or not isinstance(operation['action'], str)
            or len(state['attempts']) >= 256):
        fail()
    work = deepcopy(state['lastWork']) if state['lastWork'] is not None else fresh_work()
    action = operation['action']; was_revealed = work['revealed']
    reason = transition(page, work, action)
    # Strict canonical equality also rejects Boolean/number coercion, additional
    # fields, changed first guesses and client-supplied completion assertions.
    try:
        if canonical(operation['work']) != canonical(work):
            fail()
    except (TypeError, ValueError):
        fail()
    completed = outcome(page, work, action, state['completed'])
    if page == 12 and action == 'verify' and not was_revealed:
        completed = False
    state['lastWork'] = work
    state['completed'] = completed
    state['phase'] = 'complete' if completed else 'playing' if work['started'] else 'ready'
    if action in ('help', 'replay'):
        state['helpCount'] += 1
    state['attempts'].append({'action': action, 'outcome': reason, 'completed': completed,
        'helpCount': state['helpCount'], 'firstGuess': work['firstGuess'], 'guess': work['guess']})
