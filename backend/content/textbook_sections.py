"""Section presentation and completion policy for exact published releases."""
import json
from pathlib import Path

from content.textbook_journey import ordered_scenes
from core.errors import ApiError


CHECK_ENTRY = 'shared-check'
_REGISTRY = json.loads(Path(__file__).with_name('textbook_sections.v1.json').read_text(encoding='utf-8'))


def plan_for(content_key, release_sha):
    plan = _REGISTRY.get(content_key)
    if plan is not None and plan['releaseSha256'] != release_sha:
        raise ApiError('textbook_sections_unavailable', '课件分段版本已变化，请返回教材目录', 409)
    return plan


def resolve_entry(plan, entry):
    if plan is None:
        if entry is None:
            return None
    elif entry is None:
        return plan['sections'][0]['nodeId']
    elif entry == CHECK_ENTRY or any(entry == item['nodeId'] for item in plan['sections']):
        return entry
    raise ApiError('textbook_entry_invalid', '这个课堂入口无效，请返回教材目录', 400)


def scene_groups(release, plan):
    scenes = ordered_scenes(release)
    groups = {}
    for item in plan['sections']:
        section = scenes[item['firstPage'] - 1:item['lastPage']]
        if (len(section) != item['lastPage'] - item['firstPage'] + 1
                or section[0]['id'] != item['firstSceneId'] or section[-1]['id'] != item['lastSceneId']
                or any(scene['type'] == 'quiz' or not speech_actions(scene) for scene in section)):
            raise ApiError('textbook_sections_unavailable', '课件分段与发布版本不一致', 409)
        groups[item['nodeId']] = section
    check = scenes[plan['sections'][-1]['lastPage']:]
    if ([scene['id'] for scene in check] != plan['checkSceneIds'] or not check or check[0]['type'] != 'quiz'
            or any(scene['type'] != 'quiz' and not speech_actions(scene) for scene in check)):
        raise ApiError('textbook_sections_unavailable', '共用小检查与发布版本不一致', 409)
    groups[CHECK_ENTRY] = check
    return groups


def speech_actions(scene):
    return {action['id'] for action in scene.get('actions', ()) if action.get('type') == 'speech'}


def completed_pages(state, scenes):
    visited = set(state['visited'])
    heard = state.get('sectionSpeech', {})
    return [scene['id'] for scene in scenes if scene['id'] in visited
            and (bool(state['quiz']) if scene['type'] == 'quiz'
                 else speech_actions(scene).issubset(heard.get(scene['id'], ())))]


def progress(state, plan, groups):
    sections = [
        {**item, 'listened': len(completed_pages(state, groups[item['nodeId']])) == len(groups[item['nodeId']])}
        for item in plan['sections']
    ]
    return {'sections': sections, 'checkReady': all(item['listened'] for item in sections)}


def require_check(state, plan, groups):
    if not progress(state, plan, groups)['checkReady']:
        raise ApiError('textbook_check_locked', '听完两部分的讲解后再做小检查', 409)
