"""Bounded UI continuity snapshots; never assessment or completion evidence."""
from copy import deepcopy
import hashlib
import json
import math
import re

from content.textbook_catalog import canonical
from content import textbook_journey
from core.errors import ApiError


SCHEMA = 'mira.textbook.activity-state.v1'
MAX_BODY_BYTES = 384 * 1024
MAX_STATE_BYTES = 256 * 1024
MAX_MUTATIONS = 128
MAX_STORED_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RELEASE_SCOPES = 64
_IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')
_FORBIDDEN_KEYS = frozenset({'__proto__', 'prototype', 'constructor'})
POST_FIELDS = frozenset({'schemaVersion', 'sceneId', 'sceneIndex', 'releaseSha256',
                         'contentSha256', 'learningSessionId', 'expectedRevision', 'mutationId', 'state'})


def invalid(message='小游戏进度格式无效', *, code='textbook_activity_state_invalid', status=400):
    raise ApiError(code, message, status)


def validate_json_state(value):
    """Reject executable/prototype-shaped and unbounded payloads before JSON I/O."""
    if type(value) is not dict:
        invalid()
    nodes = 0
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 4096 or depth > 16:
            invalid('小游戏进度过于复杂')
        if type(item) is dict:
            for key, child in item.items():
                if (type(key) is not str or not key or len(key) > 128
                        or key in _FORBIDDEN_KEYS):
                    invalid()
                stack.append((child, depth + 1))
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            if len(item) > 16384:
                invalid('小游戏进度内容过长')
        elif item is None or type(item) is bool:
            pass
        elif type(item) in (int, float):
            if abs(item) > 9007199254740991 or not math.isfinite(item):
                invalid()
        else:
            invalid()
    try:
        if len(canonical(value).encode('utf-8')) > MAX_STATE_BYTES:
            invalid('小游戏进度内容过大', status=413)
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        invalid()


def parse_post(data):
    if type(data) is not dict or set(data) != POST_FIELDS or data.get('schemaVersion') != SCHEMA:
        invalid()
    if (type(data['sceneId']) is not str or not _IDENTIFIER.fullmatch(data['sceneId'])
            or type(data['learningSessionId']) is not str
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,254}', data['learningSessionId']) is None
            or type(data['sceneIndex']) is not int or not 0 <= data['sceneIndex'] < 60
            or type(data['expectedRevision']) is not int or not 0 <= data['expectedRevision'] < 9007199254740991
            or type(data['mutationId']) is not str or not _IDENTIFIER.fullmatch(data['mutationId'])
            or any(type(data[key]) is not str or re.fullmatch(r'[a-f0-9]{64}', data[key]) is None
                   for key in ('releaseSha256', 'contentSha256'))):
        invalid()
    validate_json_state(data['state'])
    return data


def descriptors(release):
    """Hash original frozen HTML, before public projection/media/shim changes."""
    native = set()
    if textbook_journey.supported(release):
        native = set(textbook_journey.definition(release=release).plan['sceneIds'].values())
    return [dict(sceneId=scene['id'], sceneIndex=index,
                 contentSha256=hashlib.sha256(scene['content']['html'].encode('utf-8')).hexdigest())
            for index, scene in enumerate(textbook_journey.ordered_scenes(release))
            if scene.get('type') == 'interactive' and scene.get('content', {}).get('type') == 'interactive'
            and type(scene['content'].get('html')) is str and scene['content']['html'].strip()
            and scene['id'] not in native]


def scope(progress, *, session_id, release, create=False):
    """A different release gets a fresh scope; historical scopes stay intact."""
    container = progress.get('activitySnapshots')
    if container is None:
        container = {'schemaVersion': SCHEMA, 'releases': {}}
        if create:
            progress['activitySnapshots'] = container
    if (type(container) is not dict or set(container) != {'schemaVersion', 'releases'}
            or container['schemaVersion'] != SCHEMA or type(container['releases']) is not dict
            or len(container['releases']) > MAX_RELEASE_SCOPES):
        invalid('保存的小游戏进度不可用', code='textbook_activity_state_unavailable', status=503)
    current = container['releases'].get(release['sha256'])
    if current is None:
        if create and len(container['releases']) >= MAX_RELEASE_SCOPES:
            invalid('小游戏进度已达到容量上限', code='textbook_activity_state_capacity', status=413)
        current = {'classroomId': release['classroomId'], 'learningSessionId': session_id, 'scenes': {}}
        if create:
            container['releases'][release['sha256']] = current
    if (type(current) is not dict or set(current) != {'classroomId', 'learningSessionId', 'scenes'}
            or current['classroomId'] != release['classroomId'] or current['learningSessionId'] != session_id
            or type(current['scenes']) is not dict):
        invalid('保存的小游戏进度身份不匹配', code='textbook_activity_state_unavailable', status=503)
    return current


def activity(descriptor, stored):
    result = {**descriptor, 'revision': 0, 'mutationId': None, 'state': None}
    if stored is None:
        return result
    try:
        if (type(stored) is not dict or set(stored) != {'sceneIndex', 'contentSha256', 'revision', 'mutationId', 'state', 'mutations'}
                or stored['sceneIndex'] != descriptor['sceneIndex'] or type(stored['sceneIndex']) is not int
                or stored['contentSha256'] != descriptor['contentSha256']
                or type(stored['revision']) is not int or not 1 <= stored['revision'] <= 9007199254740991
                or type(stored['mutationId']) is not str or not _IDENTIFIER.fullmatch(stored['mutationId'])
                or type(stored['mutations']) is not dict or not 1 <= len(stored['mutations']) <= MAX_MUTATIONS
                or stored['mutationId'] not in stored['mutations']):
            raise ValueError('invalid persisted snapshot')
        for key, value in stored['mutations'].items():
            if (type(key) is not str or not _IDENTIFIER.fullmatch(key)
                    or type(value) is not str or re.fullmatch(r'[a-f0-9]{64}', value) is None):
                raise ValueError('invalid mutation receipt')
        validate_json_state(stored['state'])
    except (ApiError, ValueError, TypeError, KeyError):
        invalid('保存的小游戏进度不可用', code='textbook_activity_state_unavailable', status=503)
    return {**result, **{key: deepcopy(stored[key]) for key in ('revision', 'mutationId', 'state')}}


def request_sha(data):
    return hashlib.sha256(canonical(data).encode('utf-8')).hexdigest()


def validate_storage_budget(progress):
    """Reject only this new snapshot write; never trim unrelated progress."""
    if len(canonical(progress['activitySnapshots']).encode('utf-8')) > MAX_STORED_BYTES:
        invalid('小游戏进度已达到容量上限', code='textbook_activity_state_capacity', status=413)


def response_within_budget(value):
    # Flask may escape Unicode in its JSON provider. Budget that larger wire
    # representation too, not only the smaller UTF-8 database representation.
    if len(json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')) > MAX_RESPONSE_BYTES:
        invalid('保存的小游戏进度过大', code='textbook_activity_state_unavailable', status=503)
    return value


def exchange(progress, *, session_id, release, definitions, data=None):
    """Shared, pure snapshot CAS; callers own authentication, row locks and SQL.

    Both fixed textbook and formal runtime classrooms use the same bounded
    namespace. No event, answer, score or completion field is inspected or
    changed here. ``changed`` distinguishes a new write from an idempotent read.
    """
    identity = {'ok': True, 'schemaVersion': SCHEMA,
        'classroomId': release['classroomId'], 'learningSessionId': session_id,
        'releaseSha256': release['sha256']}
    saved_scope = scope(progress, session_id=session_id, release=release)
    if data is None:
        return response_within_budget({**identity, 'activities': [activity(item,
            saved_scope['scenes'].get(item['sceneId'])) for item in definitions]}), False
    definition = next((item for item in definitions if item['sceneId'] == data['sceneId']), None)
    if (data['learningSessionId'] != session_id or definition is None
            or data['sceneIndex'] != definition['sceneIndex']
            or data['releaseSha256'] != release['sha256']
            or data['contentSha256'] != definition['contentSha256']):
        invalid('小游戏版本已变化，请重新进入', code='textbook_activity_state_identity', status=409)
    stored = saved_scope['scenes'].get(definition['sceneId'])
    current = activity(definition, stored)
    request_digest = request_sha(data)
    mutations = dict((stored or {}).get('mutations', {}))
    if data['mutationId'] in mutations:
        if mutations[data['mutationId']] != request_digest:
            invalid('小游戏保存标识已用于另一份进度', code='textbook_activity_mutation_conflict', status=409)
        return {**identity, 'activity': current}, False
    if data['expectedRevision'] != current['revision']:
        invalid('小游戏已在其他页面更新，请重新进入', code='textbook_activity_revision_conflict', status=409)
    mutations[data['mutationId']] = request_digest
    updated = {key: deepcopy(data[key]) for key in ('sceneIndex', 'contentSha256', 'mutationId', 'state')}
    updated.update(revision=current['revision'] + 1, mutations=dict(list(mutations.items())[-MAX_MUTATIONS:]))
    scope(progress, session_id=session_id, release=release, create=True)['scenes'][definition['sceneId']] = updated
    validate_storage_budget(progress)
    return {**identity, 'activity': activity(definition, updated)}, True


def load_post_bytes(raw):
    """Internal HTTP boundary also rejects duplicate JSON members and NaN."""
    if len(raw) > MAX_BODY_BYTES:
        invalid('小游戏进度内容过大', status=413)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                invalid()
            result[key] = value
        return result
    try:
        return parse_post(json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: invalid()))
    except (ValueError, UnicodeError, RecursionError):
        invalid()
