"""Classify paid classroom requests using authenticated, frozen course state."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_formal_interaction import validate_classroom_interaction
from integrations.openmaic_formal_quality import quality_snapshot
from services.learning_paid_authority import teaching_budget_bindings, teaching_budget_scope, scope_digest, upgraded_manifest
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService

_POLICY = json.loads((Path(__file__).resolve().parents[1] / 'content/required_teaching_policy.v1.json').read_text())
_PAID_PATHS = frozenset({'/api/chat', '/api/chat/pi', '/api/generate/tts', '/api/transcription', '/api/quiz-grade',
                         '/api/pbl/v2/evaluate', '/api/pbl/v2/instructor', '/api/pbl/v2/open-task', '/api/pbl/v2/simulator'})


def canonical_scripted_guidance(manifest: Mapping, classroom: Mapping, marker: object) -> dict:
    """No browser prompt, agent persona, history, model or answer key is trusted."""
    if not isinstance(marker, Mapping) or set(marker) != {'sceneId', 'actionId'}:
        raise ValueError('invalid scripted guidance identity')
    validate_classroom_interaction(manifest['professionalCreation'], manifest['generationContract'], classroom)
    snapshot = quality_snapshot(classroom)
    scene = next((s for s in snapshot['scenes'] if s['id'] == marker['sceneId']), None)
    action = next((a for a in (scene or {}).get('actions', [])
                   if a.get('id') == marker['actionId'] and a.get('type') == 'discussion'), None)
    if action is None or not isinstance(action.get('topic'), str):
        raise ValueError('scripted discussion is absent from the frozen classroom')
    teacher = manifest['formalEvidence']['teacher']
    contract = manifest['generationContract']['teacher']
    runtime_teacher = contract['runtime']
    # Generated peer personas are not snapshot-bound; use the verified subject teacher.
    agent = {'id': teacher['agentId'], 'name': runtime_teacher['name'], 'role': 'teacher',
             'avatar': runtime_teacher['avatar'], 'color': '#425CBA', 'priority': 100,
             'persona': _POLICY['instruction'].format(gradeBoundary=json.dumps(manifest['generationContract']['gradeBoundary'], ensure_ascii=False)),
             'voiceConfig': runtime_teacher['voiceConfig']}
    teaching_scenes = [copy.deepcopy(s) for s in snapshot['scenes']
                       if s['order'] <= scene['order'] and s['type'] != 'quiz']
    return {'messages': [], 'miraScriptedAction': dict(marker),
            'config': {'agentIds': [agent['id']], 'agentConfigs': [agent], 'sessionType': 'discussion',
                       'triggerAgentId': agent['id'], 'discussionTopic': action['topic'],
                       'discussionPrompt': str(action.get('prompt') or '')},
            'storeState': {'stage': {**snapshot['stage'], 'agentIds': [agent['id']],
                                     'generatedAgentConfigs': [agent]},
                           'scenes': teaching_scenes, 'currentSceneId': scene['id'],
                           'mode': 'playback', 'whiteboardOpen': False}}


def teaching_conversation_id(*, authorization_id, learning_session_id, classroom_id, scene_id, action_id):
    payload = [authorization_id, learning_session_id, classroom_id, scene_id, action_id]
    return 'mtc_' + hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def trusted_teaching_context(conversation, binding, *, learning_session_id, classroom_id):
    if (not isinstance(conversation, Mapping) or conversation.get('authorizationId') != binding['authorizationId']
            or conversation.get('learningSessionId') != learning_session_id or conversation.get('classroomId') != classroom_id
            or type(conversation.get('revision')) is not int or conversation['revision'] < 0
            or conversation.get('id') != teaching_conversation_id(authorization_id=binding['authorizationId'],
                learning_session_id=learning_session_id, classroom_id=classroom_id,
                scene_id=conversation.get('sceneId'), action_id=conversation.get('actionId'))):
        raise ApiError('learning_teaching_context_invalid', '课堂指导记录身份不一致', 409)
    return {'conversationId': conversation['id'], 'authorizationId': binding['authorizationId'],
            'learningSessionId': learning_session_id, 'classroomId': classroom_id,
            'sceneId': conversation['sceneId'], 'actionId': conversation['actionId'],
            'expectedRevision': conversation['revision']}


def required_reply_request(conversation, reply, binding, *, learning_session_id, classroom_id):
    context = trusted_teaching_context(conversation, binding, learning_session_id=learning_session_id, classroom_id=classroom_id)
    if isinstance(reply, Mapping) and set(reply) == {'conversationId'} and reply['conversationId'] == conversation['id']:
        canonical = copy.deepcopy(conversation['canonicalRequest'])
        canonical['miraTeachingContext'] = context
        return canonical
    if (not isinstance(reply, Mapping) or set(reply) != {'conversationId', 'replyId', 'userText'}
            or reply.get('conversationId') != conversation['id']
            or not isinstance(reply.get('replyId'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', reply['replyId'])
            or not isinstance(reply.get('userText'), str) or not reply['userText'].strip() or len(reply['userText']) > 2000):
        raise ApiError('learning_teaching_reply_invalid', '请发送两千字以内的本次回答', 400)
    duplicate = reply['replyId'] in conversation.get('replyIds', [])
    if conversation.get('state') != 'awaiting_user' and not (duplicate and conversation.get('state') in {'completed', 'awaiting_user'}):
        raise ApiError('learning_teaching_reply_not_ready', '老师的指导尚未结束，请稍后继续', 409)
    canonical = copy.deepcopy(conversation['canonicalRequest'])
    canonical.pop('miraScriptedAction', None)
    canonical['messages'] = copy.deepcopy(conversation['messages']) + [
        {'id': reply['replyId'], 'role': 'user', 'parts': [{'type': 'text', 'text': reply['userText']}]}]
    canonical['directorState'] = copy.deepcopy(conversation.get('directorState'))
    canonical['miraTeachingContext'] = {**context, 'replyId': reply['replyId'],
        'replyTextSha256': hashlib.sha256(reply['userText'].encode()).hexdigest()}
    return canonical


def required_speech_request(conversation, body, binding, manifest, *, learning_session_id, classroom_id):
    context = trusted_teaching_context(conversation, binding, learning_session_id=learning_session_id, classroom_id=classroom_id)
    text = body.get('text')
    if (conversation.get('state') not in {'running', 'awaiting_user', 'completed'} or not isinstance(text, str)
            or not any(isinstance(item, Mapping) and item.get('text') == text for item in conversation.get('utterances', []))):
        raise ApiError('learning_teaching_speech_unverified', '这段语音没有对应的老师指导记录', 409)
    voice = manifest['generationContract']['teacher']['runtime']['voiceConfig']
    audio_id = 'mtu_' + hashlib.sha256(json.dumps([conversation['id'], text, voice], ensure_ascii=False,
                                                  sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'text': text, 'audioId': audio_id, 'ttsProviderId': voice['providerId'], 'ttsModelId': voice['modelId'],
            'ttsVoice': voice['voiceId'], 'ttsSpeed': 1, 'miraTeachingContext': context}


class OpenMaicPaidCallService:
    def __init__(self, *, repository, runtime_service, budget_service):
        self.repository = repository
        self.runtime_service = runtime_service
        self.budget_service = budget_service

    def admit(self, *, runtime_session_id, learning_session_id, upstream_classroom_id, data):
        if not isinstance(data, Mapping) or set(data) != {'path', 'request'} or data['path'] not in _PAID_PATHS or not isinstance(data['request'], Mapping):
            raise ApiError('learning_paid_request_invalid', '互动请求无效', 400)
        with self.repository.transaction() as conn:
            row = self.repository.get_runtime_authority(conn, runtime_session_id=runtime_session_id,
                learning_session_id=learning_session_id, upstream_classroom_id=upstream_classroom_id, for_update=False)
            if row is None:
                raise ApiError('runtime_event_session_not_found', '课堂会话不存在或身份不匹配', 404)
            OpenMaicRuntimeEventService._validate_authority(row, runtime_session_id=runtime_session_id,
                learning_session_id=learning_session_id, upstream_classroom_id=upstream_classroom_id, now=now_ms())
            recovery_request = data['path'] in {'/api/chat', '/api/chat/pi'} and isinstance(data['request'].get('miraRequiredConversation'), Mapping) and set(data['request']['miraRequiredConversation']) == {'conversationId'}
            if row['session_status'] == 'completed' and not (recovery_request or data['path'] == '/api/generate/tts'):
                raise ApiError('learning_session_completed', '这节课已完成，请从课程列表继续学习', 409)
            manifest = row['feature_manifest_json']
            if isinstance(manifest, str): manifest = json.loads(manifest)
        if not upgraded_manifest(manifest):
            raise ApiError('learning_paid_context_not_supported', '课堂费用合同不匹配', 409)
        binding_row = {**row, 'course_id': row['session_course_id'], 'course_version': row['session_course_version']}
        bindings = teaching_budget_bindings(self.budget_service, binding_row, manifest, admit=False)
        body = data['request']
        marker = body.get('miraScriptedAction')
        required_conversation = body.get('miraRequiredConversation')
        purpose, canonical = 'optional_interaction', None
        active_required_binding = (bindings or {}).get('required_teaching')
        # Identity for cached replay is derived from the stored session, never minted.
        saved_binding = {'schemaVersion': 'mira.learning.paid-budget-binding.v1', 'required': True,
                         'authorizationId': scope_digest(teaching_budget_scope(binding_row, manifest, 'required_teaching'))}
        required_binding = active_required_binding or saved_binding
        chat = data['path'] in {'/api/chat', '/api/chat/pi'}
        if marker is not None and required_conversation is not None:
            raise ApiError('learning_scripted_guidance_invalid', '课堂指导请求冲突', 400)
        if chat and required_conversation is not None:
            if required_binding is None or not isinstance(required_conversation, Mapping):
                raise ApiError('learning_budget_unavailable', '课堂指导暂不可用，学习进度已保留。', 503)
            conversation = self.runtime_service.client.read_teaching_conversation(
                conversation_id=required_conversation.get('conversationId'), learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
            if not active_required_binding and required_conversation.get('replyId') not in (conversation or {}).get('replyIds', []) and set(required_conversation) != {'conversationId'}:
                raise ApiError('learning_budget_unavailable', '新的课堂指导暂不可用，已保存内容可以继续查看。', 503)
            canonical = required_reply_request(conversation, required_conversation, required_binding,
                learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
            purpose = 'required_teaching'
        elif chat and marker is not None:
            # A scripted start is distinct from an arbitrary user message or forged transcript.
            if body.get('messages') != []:
                raise ApiError('learning_scripted_guidance_invalid', '课堂指导身份不匹配', 400)
            try:
                classroom = self.runtime_service.client.get_classroom(upstream_classroom_id)
                canonical = canonical_scripted_guidance(manifest, classroom, marker)
            except (ValueError, KeyError, TypeError) as exc:
                raise ApiError('learning_scripted_guidance_invalid', '课堂指导与已发布课程不一致', 409) from exc
            purpose = 'required_teaching'
            scene_index = next(scene['order'] for scene in quality_snapshot(classroom)['scenes'] if scene['id'] == marker['sceneId'])
            with self.repository.transaction() as conn:
                entered = self.repository.get_scene_identity(conn, runtime_session_id=runtime_session_id, scene_index=scene_index)
            if entered is None or entered['scene_id'] != marker['sceneId']:
                raise ApiError('learning_teaching_scene_not_entered', '请从当前课堂页面开始老师指导', 409)
            if required_binding is not None:
                identity = teaching_conversation_id(authorization_id=required_binding['authorizationId'], learning_session_id=learning_session_id,
                    classroom_id=upstream_classroom_id, scene_id=marker['sceneId'], action_id=marker['actionId'])
                conversation = self.runtime_service.client.read_teaching_conversation(conversation_id=identity,
                    learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
                if conversation is None:
                    if not active_required_binding:
                        raise ApiError('learning_budget_unavailable', '课堂指导暂不可用，学习进度已保留。', 503)
                    conversation = {'id': identity, 'authorizationId': required_binding['authorizationId'],
                        'learningSessionId': learning_session_id, 'classroomId': upstream_classroom_id,
                        'sceneId': marker['sceneId'], 'actionId': marker['actionId'], 'revision': 0}
                else:
                    canonical = copy.deepcopy(conversation['canonicalRequest'])
                canonical['miraTeachingContext'] = trusted_teaching_context(conversation, required_binding,
                    learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
        elif data['path'] == '/api/generate/tts' and required_binding is not None:
            if required_conversation is not None and (not isinstance(required_conversation, Mapping)
                    or set(required_conversation) != {'conversationId'}):
                raise ApiError('learning_teaching_context_invalid', '课堂语音身份不一致', 400)
            conversation = self.runtime_service.client.read_teaching_conversation(
                conversation_id=(required_conversation or {}).get('conversationId'),
                learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
            if conversation is not None and any(isinstance(item, Mapping) and item.get('text') == body.get('text') for item in conversation.get('utterances', [])):
                canonical = required_speech_request(conversation, body, required_binding, manifest,
                    learning_session_id=learning_session_id, classroom_id=upstream_classroom_id)
                purpose = 'required_teaching'
            elif required_conversation is not None:
                raise ApiError('learning_teaching_speech_unverified', '这段语音没有对应的老师指导记录', 409)
        binding = (bindings or {}).get(purpose)
        if purpose == 'required_teaching' and canonical is not None:
            binding = required_binding
        if binding is None:
            raise ApiError('learning_budget_unavailable', '互动暂时不可用，学习进度已保留。', 503)
        result = {'ok': True, 'paidBudget': binding, 'purpose': purpose}
        if canonical is not None:
            # Stable full body makes repeat submissions the same budget dispatch identity.
            result.update(request=canonical)
            if chat: result['upstreamPath'] = '/api/chat/pi'
        return result
