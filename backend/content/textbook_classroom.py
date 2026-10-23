"""Bind a fixed lesson to the existing OpenMAIC classroom and agent protocol."""
from copy import deepcopy
import json
from pathlib import Path

from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_release import public_classroom
from content.textbook_pedagogy import LOW_READING_POLICY
from core.errors import ApiError

POLICY = json.loads(Path(__file__).with_name('textbook_classroom_policy.v1.json').read_text())
COMPANIONS = ['default-2', 'default-3', 'default-4', 'default-5', 'default-6']
INTERACTION_PATHS = frozenset({'/api/chat', '/api/chat/pi', '/api/generate/tts', '/api/transcription'})


def classroom_roster(frozen, release, *, private=False):
    teacher = get_formal_runtime_teacher_contract(frozen['subject'])['runtime']
    config = {
        'id': 'mira-textbook-' + frozen['subject'], 'name': teacher['name'], 'role': 'teacher',
        'avatar': teacher['avatar'], 'color': '#826642', 'priority': 10,
        'persona': '', 'voiceConfig': teacher['voiceConfig'],
    }
    if private:
        config['persona'] = POLICY['teacherInstruction'].format(
            teacherName=teacher['name'], gradeCode=frozen['gradeCode'], subject=frozen['subject'],
            knowledgeBrief=json.dumps(frozen['knowledgeBrief'], ensure_ascii=False))
        config['allowedActions'] = POLICY['teacherActions'][:]
        if frozen['gradeCode'] in LOW_READING_POLICY['grades']:
            config['persona'] += '\n' + '\n'.join(LOW_READING_POLICY['rules'])
    # Older previews used the built-in six-person classroom. Replace only the
    # generic teacher, retaining its built-in assistant/classmate identities.
    # Workbench lessons name their own classmates, for whom the student runtime
    # has no voices or personas; they sit with the built-in classmates instead.
    peers = [agent for agent in release['classroom']['stage'].get('agentIds', COMPANIONS)
             if agent in COMPANIONS] or COMPANIONS
    return [config['id'], *dict.fromkeys(peers)], [config]


def discussion_request(frozen, release, body):
    """Keep OpenMAIC's dialogue protocol; bind content/roster to this release."""
    state, config = body.get('storeState'), body.get('config')
    messages = body.get('messages')
    if (not isinstance(state, dict) or not isinstance(config, dict)
            or not isinstance(messages, list)
            or any(not isinstance(m, dict) or m.get('role') not in {'user', 'assistant'} for m in messages)):
        raise ApiError('textbook_discussion_invalid', '课堂讨论请求无效', 400)
    classroom = public_classroom(release)
    if (not isinstance(state.get('stage'), dict) or state['stage'].get('id') != classroom['id']
            or state.get('currentSceneId') not in {s['id'] for s in classroom['scenes']}):
        raise ApiError('textbook_discussion_scene_invalid', '请从当前课件发起讨论', 409)
    ids, agents = classroom_roster(frozen, release, private=True)
    if config.get('triggerAgentId') is not None and config['triggerAgentId'] not in ids:
        raise ApiError('textbook_discussion_agent_invalid', '讨论同学不属于本节课', 400)
    classroom['stage'].update(agentIds=ids, generatedAgentConfigs=agents)
    result = deepcopy(body)
    # Native peers keep their original server-side personas/actions/voices.
    # Browser-provided teacher prompts and replacement slides aren't authority.
    result['config'] = {**config, 'agentIds': ids, 'agentConfigs': agents}
    result['storeState'] = {
        'stage': classroom['stage'], 'scenes': classroom['scenes'],
        'currentSceneId': state['currentSceneId'], 'mode': 'playback',
        'whiteboardOpen': state.get('whiteboardOpen') is True,
        'whiteboardManualVisibilityRevision': state.get('whiteboardManualVisibilityRevision', 0),
    }
    return result
