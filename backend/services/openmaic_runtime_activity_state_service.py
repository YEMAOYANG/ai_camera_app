"""Formal classroom UI continuity, separate from assessed runtime events."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import re
from threading import Lock

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services import textbook_activity_state as snapshots


_SHA = re.compile(r'[a-f0-9]{64}\Z')
_DEFINITIONS = OrderedDict()
_LOCK = Lock()


class OpenMaicRuntimeActivityStateService:
    """Reuse the event writer's complete authority and lock ordering.

    Source HTML is read through the existing registry-backed Native reader and
    compared with the published audio/feature seal. Only small immutable scene
    descriptors are cached; learning state always comes from the locked row.
    """

    def __init__(self, event_service, *, classroom_reader):
        self.events = event_service
        self.repository = event_service.repository
        self.classroom_reader = classroom_reader

    def _authority(self, conn, *, runtime_session_id, learning_session_id, upstream_classroom_id):
        authority = self.events._lock_current_formal_authority(conn,
            runtime_session_id=runtime_session_id, learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id)
        scenes = self.events._validate_authority(authority, runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id, upstream_classroom_id=upstream_classroom_id,
            now=self.events.clock())
        publication = self.repository.get_activity_publication(conn, authority=authority)
        manifest = authority.get('feature_manifest_json')
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except (TypeError, ValueError):
                manifest = None
        if (not isinstance(manifest, dict) or publication is None
                or not _SHA.fullmatch(str(publication.get('publication_receipt_hash') or ''))
                or not _SHA.fullmatch(str(manifest.get('classroomContentSha256') or ''))
                or publication.get('classroom_content_sha256') != manifest['classroomContentSha256']):
            raise ApiError('runtime_activity_authority_invalid', '正式课堂进度合同不可用', 409)
        identity = {'classroomId': upstream_classroom_id,
            'sha256': publication['publication_receipt_hash'],
            'contentSha256': manifest['classroomContentSha256'],
            'runtimeClassroomId': authority['runtime_classroom_id'],
            'releaseId': authority['candidate_release_id'],
            'targetFingerprint': authority['candidate_target_fingerprint'],
            'buildItemId': authority['candidate_build_item_id'],
            'familyId': authority['family_id'], 'childId': authority['child_id'],
            'learningSessionId': learning_session_id,
            'scenes': scenes}
        return authority, identity

    def _definitions(self, identity):
        key = digest(identity)
        with _LOCK:
            if key in _DEFINITIONS:
                _DEFINITIONS.move_to_end(key)
                return deepcopy(_DEFINITIONS[key])
        try:
            room = self.classroom_reader(identity['classroomId'])
            if (not isinstance(room, dict) or room.get('id') != identity['classroomId']
                    or room.get('stage', {}).get('id') != identity['classroomId']
                    or digest({'stage': room.get('stage'), 'scenes': room.get('scenes')}) != identity['contentSha256']):
                raise ValueError('classroom source differs')
            scenes = room['scenes']
            if (not isinstance(scenes, list) or len(scenes) != len(identity['scenes'])
                    or any(not isinstance(scene, dict) for scene in scenes)):
                raise ValueError('classroom scenes differ')
            by_id = {scene['id']: scene for scene in scenes}
            if len(by_id) != len(scenes) or set(by_id) != {item['sceneId'] for item in identity['scenes']}:
                raise ValueError('classroom scene identities differ')
            definitions = []
            for item in identity['scenes']:
                scene = by_id[item['sceneId']]
                content = scene.get('content', {})
                if (scene.get('type') == 'interactive' and content.get('type') == 'interactive'
                        and type(content.get('html')) is str and content['html'].strip()):
                    definitions.append({'sceneId': scene['id'], 'sceneIndex': item['sceneIndex'],
                        'contentSha256': hashlib.sha256(content['html'].encode('utf-8')).hexdigest()})
        except Exception:
            # Reader exceptions can include private URLs or source. The public
            # boundary exposes only this stable, retryable code.
            raise ApiError('runtime_activity_source_unavailable', '小游戏内容暂时无法校验，请稍后重试', 503) from None
        with _LOCK:
            _DEFINITIONS[key] = deepcopy(definitions)
            while len(_DEFINITIONS) > 128:
                _DEFINITIONS.popitem(last=False)
        return definitions

    def state(self, *, runtime_session_id, learning_session_id, upstream_classroom_id, data=None, manifest_only=False):
        trusted = {
            'runtime_session_id': self.events._identifier(runtime_session_id, 'runtimeSessionId', maximum=128),
            'learning_session_id': self.events._identifier(learning_session_id, 'learningSessionId', maximum=255),
            'upstream_classroom_id': self.events._identifier(upstream_classroom_id, 'classroomId', maximum=255)}
        if data is not None:
            data = snapshots.parse_post(data)
            if data['learningSessionId'] != trusted['learning_session_id']:
                snapshots.invalid('课堂进度身份已变化，请重新进入', code='textbook_activity_state_identity', status=409)
        with self.repository.transaction() as conn:
            _, initial = self._authority(conn, **trusted)
        # Do not hold the child/session/publication locks during a remote read.
        definitions = self._definitions(initial)
        with self.repository.transaction() as conn:
            authority, current = self._authority(conn, **trusted)
            if current != initial:
                raise ApiError('runtime_activity_authority_changed', '课堂刚刚更新，请重新进入', 409)
            if manifest_only:
                return {'ok': True, 'schemaVersion': snapshots.SCHEMA,
                    'classroomId': initial['classroomId'], 'learningSessionId': learning_session_id,
                    'releaseSha256': initial['sha256'], 'activities': definitions}
            session = self.repository.get_learning_session_for_update(conn,
                family_id=authority['family_id'], learning_session_id=learning_session_id)
            if (session is None or session.get('id') != learning_session_id
                    or session.get('child_id') != authority['child_id']
                    or session.get('course_id') != authority['session_course_id']
                    or session.get('course_version') != authority['session_course_version']):
                snapshots.invalid('课堂进度身份已变化，请重新进入', code='textbook_activity_state_identity', status=409)
            try:
                raw = session.get('runtime_state_json')
                progress = json.loads(raw) if isinstance(raw, str) and raw else deepcopy(raw) if raw else {}
                if type(progress) is not dict:
                    raise ValueError('invalid stored progress')
            except (TypeError, ValueError):
                snapshots.invalid('保存的课堂进度不可用', code='textbook_activity_state_unavailable', status=503)
            result, changed = snapshots.exchange(progress, session_id=learning_session_id,
                release=initial, definitions=definitions, data=data)
            if changed:
                self.repository.save_activity_state(conn, authority=authority,
                    runtime_state_json=canonical(progress), now=self.events.clock())
            return result
