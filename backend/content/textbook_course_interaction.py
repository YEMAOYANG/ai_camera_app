"""Server-computed, bounded interaction evidence for fixed textbook releases.

Events are client-reported inputs, not proof of the child's identity, unaided
reading, spoken accuracy or mastery. UI checkpoint snapshots are deliberately
not consumed here. Each release must freeze every interactive scene's validator
and exact HTML hash; unsupported or partially bound courses fail closed.
"""
from copy import deepcopy
import hashlib
import re

from content.textbook_catalog import canonical, digest
from content import textbook_autumn_p4_p7, textbook_autumn_p8_p12, textbook_math_interaction, textbook_english_interaction
from content import textbook_math_split_add
from content import textbook_math_subtract_zero
from content import textbook_math_tidy_review
from content import textbook_science_sensory, textbook_science_fruit
from core.errors import ApiError

SCHEMA = 'mira.textbook.interaction-completion.v1'
STATE_SCHEMA = 'mira.textbook.interaction-completion-state.v1'
OP_SCHEMA = 'mira.textbook.interaction-operation.v1'
_SHA = re.compile(r'[a-f0-9]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z')
_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3', 'u5-l1')
_VALIDATORS = {'scene-p2': 'autumn-evidence-slots.v1', 'scene-p3': 'autumn-falling-leaves.v1',
               **textbook_autumn_p4_p7.VALIDATORS, **textbook_autumn_p8_p12.VALIDATORS}
_EVIDENCE = {'weather', 'leaves', 'animals', 'wrong_warm', 'wrong_green'}
_VALID = {'weather', 'leaves', 'animals'}
_MAX_ATTEMPTS = 128
_MAX_OPERATIONS = 2048


def fail(message='互动记录无效，请重新进入课堂'):
    raise ApiError('textbook_interaction_operation_invalid', message, 409)


def html_templates(classroom, binding, source_asset_sha256):
    """Digest literal HTML and ordered asset identities separately.

    Media URLs are rewritten for delivery. Typed tokens avoid conflating an
    actual URL with text that merely resembles a placeholder. Callers supply
    a verified lookup: source bytes before publishing, or frozen delivery
    provenance when reading a release.
    """
    from content.textbook_release import MEDIA
    contract = build_contract(classroom, binding)
    scenes = []
    for item in contract['scenes']:
        html = classroom['scenes'][item['sceneIndex']]['content']['html']
        tokens, end = [], 0
        for match in MEDIA.finditer(html):
            sha = source_asset_sha256(match)
            if not isinstance(sha, str) or not _SHA.fullmatch(sha):
                fail('互动页面素材来源无效')
            tokens.extend([{'text': html[end:match.start()]}, {'assetSha256': sha}])
            end = match.end()
        tokens.append({'text': html[end:]})
        scenes.append({'sceneId': item['sceneId'], 'sceneIndex': item['sceneIndex'],
                       'templateSha256': digest(tokens)})
    return scenes


def validate_delivery_templates(frozen, release):
    """Prove delivery URL substitution retained the reviewed page content."""
    templates = frozen.get('interactionCompletionTemplates')
    if (not isinstance(templates, dict) or set(templates) != {'schemaVersion', 'scenes', 'assets'}
            or templates.get('schemaVersion') != 'mira.textbook.interaction-delivery-templates.v1'
            or not isinstance(templates.get('scenes'), list) or not isinstance(templates.get('assets'), list)):
        fail('互动页面缺少审核源与交付转换的冻结绑定')
    allowed = set()
    for item in templates['assets']:
        if (not isinstance(item, dict) or set(item) != {'sourceSha256', 'deliverySha256', 'mimeType', 'byteSize'}
                or any(not isinstance(item.get(k), str) or not _SHA.fullmatch(item[k])
                       for k in ('sourceSha256', 'deliverySha256'))
                or not isinstance(item.get('mimeType'), str)
                or not item['mimeType'].startswith(('image/', 'audio/'))
                or type(item.get('byteSize')) is not int or item['byteSize'] <= 0):
            fail('互动页面冻结素材身份无效')
        key = canonical(item)
        if key in allowed:
            fail('互动页面冻结素材身份重复')
        allowed.add(key)
    media = release.get('media')
    if not isinstance(media, list) or any(not isinstance(item, dict) or not isinstance(item.get('path'), str) for item in media):
        fail('互动页面交付素材清单无效')
    by_path = {item['path']: item for item in media}
    if len(by_path) != len(media):
        fail('互动页面交付素材身份重复')
    used = set()

    def source_sha(match):
        item = by_path.get(match.group(0))
        if item is None:
            fail('互动页面引用了未审核的交付素材')
        identity = {'sourceSha256': item.get('sourceSha256', item.get('sha256')),
                    'deliverySha256': item.get('sha256'), 'mimeType': item.get('mimeType'),
                    'byteSize': item.get('byteSize')}
        key = canonical(identity)
        if key not in allowed:
            fail('互动页面素材与审核源不一致')
        used.add(key)
        return identity['sourceSha256']

    actual = html_templates(release['classroom'], release.get('textbookBinding'), source_sha)
    if actual != templates['scenes'] or used != allowed:
        fail('互动页面内容或素材转换与审核源不一致')
    return True


def _validators(binding):
    if binding == {'editionId': _BINDING[0], 'revisionId': _BINDING[1], 'nodeId': _BINDING[2]}:
        return _VALIDATORS
    if isinstance(binding, dict) and set(binding) == {'editionId', 'revisionId', 'nodeId'}:
        selected = textbook_math_subtract_zero.validators(binding)
        if selected:
            return selected
        selected = textbook_math_tidy_review.validators(binding)
        if selected:
            return selected
        selected = textbook_science_fruit.validators(binding)
        if selected:
            return selected
        selected = textbook_science_sensory.validators(binding)
        if selected:
            return selected
        selected = textbook_math_split_add.validators(binding)
        if selected:
            return selected
        selected = textbook_math_interaction.validators(binding)
        if selected:
            return selected
        selected = textbook_english_interaction.validators(binding)
        if selected:
            return selected
    fail('本课尚未绑定互动验证器')


def build_contract(classroom, binding):
    """Bind the supported lesson to the actual delivered HTML bytes.

    Publication rewrites media URLs, so this must run on the delivery copy,
    not the authored preview.  The caller must separately establish that the
    student host and its full-page evidence have passed acceptance.
    """
    if not isinstance(classroom, dict) or not isinstance(classroom.get('scenes'), list):
        fail('课堂页面身份无效')
    scenes = []
    for index, scene in enumerate(classroom['scenes']):
        if not isinstance(scene, dict):
            fail('课堂页面身份无效')
        if scene.get('type') != 'interactive':
            continue
        html = scene.get('content', {}).get('html')
        validator = _validators(binding).get(scene.get('id'))
        if not isinstance(html, str) or not html or validator is None:
            fail('本课存在尚未绑定验证器的互动页面')
        scenes.append({'sceneId': scene['id'], 'sceneIndex': index,
                       'contentSha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
                       'validator': validator})
    body = {'schemaVersion': SCHEMA, 'binding': deepcopy(binding), 'scenes': scenes}
    contract = {**body, 'sha256': digest(body)}
    validate_contract({'classroom': classroom, 'textbookBinding': binding,
                       'interactionCompletionContract': contract})
    return contract


def validate_contract(release):
    """Require an exact, fully bound release; never accept a partial plan."""
    contract = release.get('interactionCompletionContract')
    if not isinstance(contract, dict) or set(contract) != {'schemaVersion', 'binding', 'scenes', 'sha256'}:
        fail('本课没有可验证的完整互动合同')
    if (contract.get('schemaVersion') != SCHEMA
            or not _SHA.fullmatch(str(contract.get('sha256')))
            or contract['sha256'] != digest({k: v for k, v in contract.items() if k != 'sha256'})
            or not isinstance(contract.get('binding'), dict)):
        fail('互动合同身份不一致')
    if release.get('textbookBinding') != contract['binding']:
        fail('互动合同与发布教材不一致')
    room = release.get('classroom')
    if not isinstance(room, dict) or not isinstance(room.get('scenes'), list):
        fail('课堂页面身份无效')
    orders = [s.get('order') for s in room['scenes'] if isinstance(s, dict)]
    if (len(orders) != len(room['scenes']) or any(type(v) is not int for v in orders)
            or len(set(orders)) != len(orders) or orders != sorted(orders)):
        fail('课堂页面顺序无效')
    selected_validators = _validators(contract['binding'])
    expected = []
    for index, scene in enumerate(room['scenes']):
        if scene.get('type') != 'interactive':
            continue
        html = scene.get('content', {}).get('html')
        validator = selected_validators.get(scene.get('id'))
        if not isinstance(html, str) or not html or validator is None:
            fail('本课存在尚未绑定验证器的互动页面')
        expected.append({'sceneId': scene['id'], 'sceneIndex': index,
                         'contentSha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
                         'validator': validator})
    # This contract is for this exact already-authored course. An attacker (or
    # a broken build) must not make missing pages disappear from completion.
    subtract_zero = textbook_math_subtract_zero.validators(contract['binding'])
    tidy = textbook_math_tidy_review.validators(contract['binding'])
    if ([s['sceneId'] for s in expected] != list(selected_validators)
            or [s['sceneIndex'] for s in expected] !=
                (list(range(len(subtract_zero))) if subtract_zero else
                 list(range(len(tidy))) if tidy else
                 [p - 1 for p in textbook_science_sensory.PAGES] if selected_validators is textbook_science_sensory.VALIDATORS
                 else list(range(1, len(selected_validators) + 1)))
            or len(room['scenes']) != (len(subtract_zero) if subtract_zero else
                len(tidy) if tidy else
                12 if selected_validators is _VALIDATORS or selected_validators is textbook_science_fruit.VALIDATORS else
                12 if textbook_math_split_add.validators(contract['binding']) else
                10 if selected_validators is textbook_english_interaction.VALIDATORS else
                13 if selected_validators is textbook_science_sensory.VALIDATORS else 9)
            or contract.get('scenes') != expected):
        fail('互动页面、顺序或内容摘要已变化')
    return contract


def initial(contract):
    scenes = {}
    for spec in contract['scenes']:
        if spec['validator'] == 'autumn-evidence-slots.v1':
            scenes[spec['sceneId']] = {'phase': 'ready', 'selected': None, 'slots': [None, None, None],
                'completed': False, 'attempts': [], 'helpCount': 0}
        elif spec['validator'] == 'autumn-falling-leaves.v1':
            scenes[spec['sceneId']] = {'phase': 'ready', 'leafCount': 0, 'wind': 'left',
                'completed': False, 'attempts': [], 'helpCount': 0}
        elif spec['validator'] in textbook_autumn_p4_p7.VALIDATORS.values():
            scenes[spec['sceneId']] = textbook_autumn_p4_p7.initial_page(spec['validator'])
        elif spec['validator'] in textbook_autumn_p8_p12.VALIDATORS.values():
            scenes[spec['sceneId']] = textbook_autumn_p8_p12.initial_page(spec['validator'])
        elif spec['validator'].startswith(('math-subtract-', 'math-zero-')):
            scenes[spec['sceneId']] = textbook_math_subtract_zero.initial_page(spec['validator'])
        elif spec['validator'].startswith('math-tidy-'):
            scenes[spec['sceneId']] = textbook_math_tidy_review.initial_page(spec['validator'])
        elif spec['validator'].startswith(('math-split-', 'math-add-')):
            scenes[spec['sceneId']] = textbook_math_split_add.initial_page(spec['validator'])
        elif spec['validator'].startswith('math-'):
            scenes[spec['sceneId']] = textbook_math_interaction.initial_page(spec['validator'])
        elif spec['validator'].startswith('english-classroom-'):
            scenes[spec['sceneId']] = textbook_english_interaction.initial_page(spec['validator'])
        elif spec['validator'].startswith('science-fruit-'):
            scenes[spec['sceneId']] = textbook_science_fruit.initial_page(spec['validator'])
        elif spec['validator'].startswith('science-sensory-'):
            scenes[spec['sceneId']] = textbook_science_sensory.initial_page(spec['validator'])
        else:
            fail('互动验证器不可用')
    return {'schemaVersion': STATE_SCHEMA, 'contractSha256': contract['sha256'], 'scenes': scenes, 'operations': {}}


def _op(operation, names):
    if not isinstance(operation, dict) or set(operation) not in names:
        fail()
    name = operation.get('name')
    if not isinstance(name, str):
        fail()
    return name


def _attempt(state, value):
    if len(state['attempts']) >= _MAX_ATTEMPTS:
        fail('本页练习次数已达到上限')
    state['attempts'].append(value)


def _evidence(state, operation):
    name = _op(operation, ({'name'}, {'name', 'value'}, {'name', 'slot'}))
    if name == 'start' and set(operation) == {'name'} and state['phase'] == 'ready':
        state['phase'] = 'playing'
        return
    if state['phase'] == 'ready' or state['completed']:
        fail('请先开始当前练习')
    if name == 'select' and set(operation) == {'name', 'value'} and isinstance(operation['value'], str) and operation['value'] in _EVIDENCE:
        state['selected'] = None if state['selected'] == operation['value'] else operation['value']
    elif name == 'place' and set(operation) == {'name', 'slot'} and type(operation['slot']) is int \
            and 0 <= operation['slot'] < 3 and state['selected'] is not None and state['slots'][operation['slot']] is None:
        state['slots'][operation['slot']] = state['selected']
        state['selected'] = None
    elif name == 'retract' and set(operation) == {'name', 'slot'} and type(operation['slot']) is int \
            and 0 <= operation['slot'] < 3 and state['slots'][operation['slot']] is not None:
        state['slots'][operation['slot']] = None
    elif name == 'reset' and set(operation) == {'name'}:
        state['selected'], state['slots'] = None, [None, None, None]
        state['phase'] = 'playing'
    elif name == 'hint' and set(operation) == {'name'} and state['helpCount'] < _MAX_ATTEMPTS:
        state['helpCount'] += 1
    elif name == 'submit' and set(operation) == {'name'}:
        slots = list(state['slots'])
        passed = len(slots) == 3 and set(slots) == _VALID
        _attempt(state, {'slots': slots, 'passed': passed, 'helpCount': state['helpCount']})
        state['completed'] = passed
        state['phase'] = 'complete' if passed else 'feedback'
    else:
        fail()


def _leaves(state, operation):
    name = _op(operation, ({'name'},))
    if name == 'start' and state['phase'] == 'ready':
        state['phase'] = 'playing'
        return
    if state['phase'] == 'ready':
        fail('请先开始当前练习')
    if name == 'add' and state['leafCount'] < 9:
        state['leafCount'] += 1
        state['completed'] = False
        state['phase'] = 'playing'
    elif name == 'remove' and state['leafCount'] > 0:
        state['leafCount'] -= 1
        state['completed'] = False
        state['phase'] = 'playing'
    elif name == 'toggleWind':
        state['wind'] = 'right' if state['wind'] == 'left' else 'left'
        state['completed'] = False
        state['phase'] = 'playing'
    elif name == 'reset':
        state.update(leafCount=0, wind='left', completed=False, phase='playing')
    elif name == 'hint' and state['helpCount'] < _MAX_ATTEMPTS:
        state['helpCount'] += 1
    elif name == 'submit':
        passed = state['leafCount'] >= 2
        _attempt(state, {'leafCount': state['leafCount'], 'wind': state['wind'],
                         'passed': passed, 'helpCount': state['helpCount']})
        state['completed'] = passed
        state['phase'] = 'complete' if passed else 'feedback'
    else:
        fail()


def _project_zero_p11_trials(contract, scenes):
    """Correct the exact zero lesson's p11 summary from accepted trial history.

    Call only with a copied scene mapping: reads must not mutate saved records.
    """
    binding = contract['binding']
    if (textbook_math_subtract_zero.validators(binding)
            and textbook_math_subtract_zero.NODES.get(binding['nodeId']) == 'zero'):
        textbook_math_subtract_zero.reconcile_zero_p11_trials(scenes.get('scene-p11'))


def apply_operation(progress, *, release, scene_index, scene_id, contract_sha256, operation_id, operation):
    """Validate one reported child operation and recompute the scene outcome."""
    contract = validate_contract(release)
    if (type(scene_index) is not int or not isinstance(scene_id, str) or not _ID.fullmatch(scene_id)
            or not isinstance(operation_id, str) or not _ID.fullmatch(operation_id)
            or contract_sha256 != contract['sha256']):
        fail('互动版本已变化，请重新进入课堂')
    spec = next((s for s in contract['scenes'] if s['sceneIndex'] == scene_index and s['sceneId'] == scene_id), None)
    if spec is None:
        fail('互动页面身份不匹配')
    stored = progress.get('courseInteraction')
    state = initial(contract) if stored is None else deepcopy(stored)
    if (not isinstance(state, dict) or set(state) != {'schemaVersion', 'contractSha256', 'scenes', 'operations'}
            or state.get('schemaVersion') != STATE_SCHEMA or state.get('contractSha256') != contract['sha256']
            or not isinstance(state.get('scenes'), dict) or set(state['scenes']) != {s['sceneId'] for s in contract['scenes']}
            or not isinstance(state.get('operations'), dict) or len(state['operations']) > _MAX_OPERATIONS):
        fail('保存的互动记录与课程不一致')
    _project_zero_p11_trials(contract, state['scenes'])
    request_sha = digest({'sceneId': scene_id, 'sceneIndex': scene_index, 'operation': operation})
    previous = state['operations'].get(operation_id)
    if previous is not None:
        if previous != request_sha:
            fail('互动操作标识已用于其他动作')
        page = state['scenes'][scene_id]
        return {'sceneId': scene_id, 'completed': page['completed'], 'phase': page['phase'],
                'allActivitiesCompleted': all(s['completed'] is True for s in state['scenes'].values()),
                'evidenceBoundary': 'client_reported_operations_not_mastery'}
    if len(state['operations']) >= _MAX_OPERATIONS:
        fail('课堂互动记录已达到容量上限')
    page = state['scenes'][scene_id]
    if spec['validator'] == 'autumn-evidence-slots.v1':
        _evidence(page, operation)
    elif spec['validator'] == 'autumn-falling-leaves.v1':
        _leaves(page, operation)
    elif spec['validator'] in textbook_autumn_p4_p7.VALIDATORS.values():
        textbook_autumn_p4_p7.apply_page(spec['validator'], page, operation)
    elif spec['validator'] in textbook_autumn_p8_p12.VALIDATORS.values():
        textbook_autumn_p8_p12.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith(('math-subtract-', 'math-zero-')):
        previous = state['scenes'].get('scene-p' + str(scene_index))
        textbook_math_subtract_zero.apply_page(spec['validator'], page, operation, previous=previous)
        textbook_math_subtract_zero.invalidate_changed_story(state['scenes'], spec['validator'])
    elif spec['validator'].startswith('math-tidy-'):
        textbook_math_tidy_review.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith(('math-split-', 'math-add-')):
        textbook_math_split_add.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith('math-'):
        textbook_math_interaction.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith('english-classroom-'):
        textbook_english_interaction.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith('science-fruit-'):
        textbook_science_fruit.apply_page(spec['validator'], page, operation)
    elif spec['validator'].startswith('science-sensory-'):
        textbook_science_sensory.apply_page(spec['validator'], page, operation)
    else:
        fail()
    state['operations'][operation_id] = request_sha
    progress['courseInteraction'] = state
    return {'sceneId': scene_id, 'completed': page['completed'], 'phase': page['phase'],
            'allActivitiesCompleted': all(s['completed'] is True for s in state['scenes'].values()),
            'evidenceBoundary': 'client_reported_operations_not_mastery'}


def completion_ready(progress, release):
    contract = validate_contract(release)
    state = progress.get('courseInteraction')
    if (not isinstance(state, dict) or state.get('schemaVersion') != STATE_SCHEMA
            or state.get('contractSha256') != contract['sha256'] or not isinstance(state.get('scenes'), dict)
            or set(state['scenes']) != {s['sceneId'] for s in contract['scenes']}
            or any(not isinstance(v, dict) for v in state['scenes'].values())):
        return False
    scenes = dict(state['scenes'])
    if textbook_math_subtract_zero.validators(contract['binding']) and textbook_math_subtract_zero.NODES.get(contract['binding']['nodeId']) == 'zero':
        scenes['scene-p11'] = deepcopy(scenes['scene-p11'])
        try:
            _project_zero_p11_trials(contract, scenes)
        except ApiError:
            return False
    return all(v.get('completed') is True for v in scenes.values())


def recovery_state(progress, release):
    """Only authenticated, server-computed page state is returned for recovery.

    The iframe checkpoint is never accepted as a source for this state.
    """
    contract = validate_contract(release)
    stored = progress.get('courseInteraction')
    state = initial(contract) if stored is None else stored
    if (not isinstance(state, dict) or state.get('schemaVersion') != STATE_SCHEMA
            or state.get('contractSha256') != contract['sha256']
            or not isinstance(state.get('scenes'), dict)
            or set(state['scenes']) != {s['sceneId'] for s in contract['scenes']}):
        fail('保存的互动记录与课程不一致')
    recovered = {'contractSha256': contract['sha256'], 'scenes': deepcopy(state['scenes'])}
    _project_zero_p11_trials(contract, recovered['scenes'])
    if textbook_math_subtract_zero.validators(contract['binding']):
        kind = textbook_math_subtract_zero.NODES[contract['binding']['nodeId']]
        recovered['sourceContexts'] = textbook_math_subtract_zero.story_source_context(state['scenes'], kind)
    return recovered
