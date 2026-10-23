"""Only fill missing selected-option feedback speech on an audited preview.

Existing feedback is immutable. Explicitly reviewed new feedback may only use
the corresponding original option image. Questions, answers, choices, scores,
existing actions and audio are retained byte-for-byte in the revision archive.
"""
from copy import deepcopy
import re

from content.textbook_catalog import digest
from content.textbook_release import MEDIA
from core.errors import ApiError

SCHEMA = 'mira.textbook.preview-feedback-addition.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')


def fail(message):
    raise ApiError('textbook_preview_feedback_addition_conflict', message, 409)


def validate_patch(patch):
    if (not isinstance(patch, dict) or set(patch) != {
            'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
            or patch['schemaVersion'] != SCHEMA
            or not SHA.fullmatch(str(patch['expectedSourceSha256']))
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 60):
        fail('补充反馈须绑定当前课堂摘要、审查者和具体依据')
    identities, actions = set(), set()
    for c in patch['changes']:
        if (not isinstance(c, dict) or set(c) != {'sceneId', 'questionId', 'optionValue', 'actionId',
                'beforeQuestionSha256', 'feedback'}
                or any(not isinstance(c[k], str) or not c[k].strip()
                       for k in ('sceneId', 'questionId', 'optionValue', 'actionId'))
                or not SHA.fullmatch(str(c['beforeQuestionSha256']))
                or not isinstance(c['feedback'], dict) or set(c['feedback']) != {'text', 'visual'}
                or not isinstance(c['feedback']['text'], str)
                or not 1 <= len(c['feedback']['text']) <= 1000
                or c['feedback']['text'] != c['feedback']['text'].strip()
                or (c['sceneId'], c['questionId'], c['optionValue']) in identities
                or c['actionId'] in actions):
            fail('反馈条目须精确指定唯一原题、选项、新旁白编号和原题摘要')
        identities.add((c['sceneId'], c['questionId'], c['optionValue']))
        actions.add(c['actionId'])


def text_candidate(source, patch):
    validate_patch(patch)
    if digest(source) != patch['expectedSourceSha256']:
        fail('课堂摘要变化，不能补充')
    target = deepcopy(source)
    originals = {(s['id'], q['id']): (s, q) for s in source['scenes'] if s.get('type') == 'quiz'
                 for q in s.get('content', {}).get('questions', [])}
    targets = {(s['id'], q['id']): (s, q) for s in target['scenes'] if s.get('type') == 'quiz'
               for q in s.get('content', {}).get('questions', [])}
    existing_ids = {a['id'] for s in source['scenes'] for a in s.get('actions', [])}
    for c in patch['changes']:
        identity = (c['sceneId'], c['questionId'])
        if identity not in originals or c['actionId'] in existing_ids:
            fail('原题不存在或新旁白编号已被使用')
        old_scene, old = originals[identity]
        scene, question = targets[identity]
        value, feedback = c['optionValue'], c['feedback']
        if digest(old) != c['beforeQuestionSha256'] or sum(o.get('value') == value for o in old.get('options', [])) != 1:
            fail('完整原题摘要或选项不符')
        stems = [a for a in old_scene.get('actions', [])
                 if a.get('type') == 'speech' and a.get('text') == old.get('question')]
        if len(stems) != 1 or not stems[0].get('audioId') or not stems[0].get('audioUrl'):
            fail('原题须有已配音的唯一逐字题干')
        present = old.get('optionFeedback', {}).get(value)
        if present is not None:
            if present != feedback:
                fail('已有反馈内容或录音不能被补句修订改写')
        else:
            visual = feedback['visual']
            option_visual = old.get('optionVisuals', {}).get(value)
            if (not isinstance(visual, dict) or set(visual) != {'kind', 'src', 'alt'}
                    or visual.get('kind') != 'image' or visual != option_visual
                    or not isinstance(visual.get('src'), str) or not MEDIA.fullmatch(visual['src'])
                    or not isinstance(visual.get('alt'), str) or not visual['alt'].strip()):
                fail('新增反馈只能引用这个选项已有的同一图片和替代说明')
            question.setdefault('optionFeedback', {})[value] = deepcopy(feedback)
        text = feedback['text']
        if (any(a.get('type') == 'speech' and a.get('text') == text for a in scene['actions'])
                or sum(f.get('text') == text for q in scene['content']['questions']
                       for f in q.get('optionFeedback', {}).values()) != 1):
            fail('反馈已有旁白或不能唯一匹配选项，不能新增重复录音')
        action = {'id': c['actionId'], 'type': 'speech', 'text': text}
        if 'audioMetadata' in stems[0]:
            action['audioMetadata'] = deepcopy(stems[0]['audioMetadata'])
        scene['actions'].append(action)
    for identity in {(c['sceneId'], c['questionId']) for c in patch['changes']}:
        _, q = targets[identity]
        if set(q['optionFeedback']) != {o['value'] for o in q['options']}:
            fail('新增反馈必须一次覆盖该题全部缺失选项')
    return target


def bind_added_feedback(target, source, patch):
    from services.textbook_preview_audio import bind_question_audio
    expected = text_candidate(source, patch)
    added = {(c['sceneId'], c['actionId']) for c in patch['changes']}
    stripped = deepcopy(target)
    for s in stripped['scenes']:
        for a in s.get('actions', []):
            if (s['id'], a['id']) in added:
                a.pop('audioId', None); a.pop('audioUrl', None)
    if stripped != expected:
        fail('补句前除指定新录音外的课堂字段发生变化')
    result = []
    # Bind on a copy, then copy back only the explicitly added feedback.
    # This must not opportunistically rewrite an old question binding.
    bound = deepcopy(target)
    selected = {(c['sceneId'], c['questionId']) for c in patch['changes']}
    for scene in bound['scenes']:
        for question in scene.get('content', {}).get('questions', []):
            if (scene['id'], question['id']) in selected:
                # A prior verbatim-stem revision may have retained older
                # metadata while correctly replacing questionAudioUrl. Derive
                # the stem identity in this throwaway copy: bind_question_audio
                # still checks the existing URL against the unique actual
                # speech. The stored metadata is preserved exactly and can
                # only be corrected by the separate explicit binding repair.
                question.pop('questionAudioBinding', None)
    bind_question_audio(bound)
    for c in patch['changes']:
        scene = next(s for s in target['scenes'] if s['id'] == c['sceneId'])
        question = next(q for q in scene['content']['questions'] if q['id'] == c['questionId'])
        ready_scene = next(s for s in bound['scenes'] if s['id'] == c['sceneId'])
        ready = next(q for q in ready_scene['content']['questions'] if q['id'] == c['questionId'])['optionFeedback'][c['optionValue']]
        if not ready.get('audioUrl') or not ready.get('audioBinding'):
            fail('新增反馈没有绑定正式录音')
        question['optionFeedback'][c['optionValue']] = ready
        result.append({**c, 'ttsRequestId': ready['audioBinding']['ttsRequestId'],
                       'deliveredFeedbackSha256': digest(ready)})
    return result
