"""Deterministic lesson sample. No business DB, AI calls, or mastery claims.

The HTTP adapter persists this JSON in its isolated review store. Keeping the
engine independent makes the evidence rules reusable by the textbook runtime.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path


LESSON_PATH = Path(__file__).resolve().parents[1] / 'content/textbooks/samples/tiandiren-v2/lesson.json'
LESSON = json.loads(LESSON_PATH.read_text())
LESSON_HASH = sha256(LESSON_PATH.read_bytes()).hexdigest()
SKILLS = LESSON['skills']
QUESTIONS = {q['id']: q for q in LESSON['questions']}
NATURE = ['sky', 'earth', 'person']
ROLES = [('me', 'teal'), ('me', 'coral'), ('you', 'teal'), ('you', 'coral'), ('he', 'teal'), ('he', 'coral')]
PEOPLE = ['coral', 'teal', 'yellow']
PHASES = ['welcome', 'explore', 'hunt', 'role-demo', 'roles', 'check', 'repair', 'transfer', 'complete', 'review', 'review-preview', 'review-complete']
QUIZZES = {'check', 'transfer', 'review', 'review-preview'}
GAMES = {'hunt', 'roles', 'repair'}


class SampleError(ValueError):
    pass


def new_state(now):
    return {'lessonHash': LESSON_HASH, 'revision': 0, 'phase': 'welcome', 'index': 0,
            'createdAt': now, 'explored': [], 'demoSpeaker': 'teal', 'demoRole': 'me',
            'practice': [], 'check': [], 'transfer': [], 'review': [], 'review-preview': [],
            'repairSkills': [], 'current': {}, 'completedAt': None, 'reviewDueAt': None,
            'returnPhase': 'complete'}


def enter(state, phase, index=0):
    state.update(phase=phase, index=index, current={})


def role_person(skill, speaker):
    return speaker if skill == 'me' else ('coral' if speaker == 'teal' else 'teal') if skill == 'you' else 'yellow'


def activity(state):
    phase, index = state['phase'], state['index']
    if phase in QUIZZES:
        # Preview repeats already encountered transfer stories; keep the actual
        # delayed-review bank unseen until it is due.
        group = 'transfer' if phase == 'review-preview' else phase
        return QUESTIONS[f'{group}-{index + 1}']
    if phase == 'hunt':
        skill, speaker = NATURE[index], None
    elif phase == 'roles':
        skill, speaker = ROLES[index]
    elif phase == 'repair':
        skill, speaker = state['repairSkills'][index], 'coral'
        if skill in NATURE:
            speaker = None
    else:
        return None
    return {'id': f'{phase}-{index}', 'skill': skill, 'speaker': speaker,
            'answerZones': SKILLS[skill].get('zones', [role_person(skill, speaker)])}


def phase_total(state):
    return len(state['repairSkills']) if state['phase'] == 'repair' else 3 if state['phase'] == 'hunt' else 6


def hints_for(skill, speaker):
    hints = list(SKILLS[skill]['hints'])
    if speaker and skill == 'you':
        hints[1] = ('红衣女孩' if speaker == 'teal' else '蓝衣男孩') + '正在听对方说话。'
    return hints


def view(state, now):
    """Allowlist only. Neither future questions nor their answers leave Python."""
    current = state['current']
    value = {'phase': state['phase'], 'index': state['index'], 'revision': state['revision'],
             'lessonId': LESSON['id'], 'title': LESSON['title'], 'explored': state['explored'],
             'total': phase_total(state), 'feedback': current.get('feedback'),
             'feedbackAudio': current.get('feedbackAudio', []), 'hintLevel': current.get('hintLevel', 0),
             'adultHelp': current.get('adultHelp', False), 'answered': bool(current.get('answered')),
             'correct': current.get('correct'), 'selected': current.get('selected'),
             'wrongChoices': current.get('wrongChoices', []), 'solved': current.get('solved', False),
             'canContinue': current.get('solved', False) or current.get('answered', False),
             'reviewDueAt': state['reviewDueAt'],
             'reviewAvailable': bool(state['reviewDueAt'] and now >= state['reviewDueAt'] and not state['review']),
             'hasStarted': state['phase'] != 'welcome', 'replaying': state.get('replaying', False), 'demoSpeaker': state['demoSpeaker'],
             'demoRole': state['demoRole'], 'sampleOnly': True}
    phase = state['phase']
    if phase == 'explore':
        value.update(canContinue=len(state['explored']) == 3, highlight=current.get('highlight'),
                     word=SKILLS[current['skill']]['word'] if current.get('skill') else None)
    if phase == 'role-demo':
        role, speaker = state['demoRole'], state['demoSpeaker']
        value.update(canContinue=True, speaker=speaker, word=SKILLS[role]['word'],
                     highlight=[role_person(role, speaker)])
    item = activity(state)
    if item:
        skill = item['skill']
        value['activityId'] = item['id']
        if phase in QUIZZES:
            value['question'] = {key: item[key] for key in ('id', 'prompt', 'options', 'audio')}
            value['question']['prompt'] = item.get('displayPrompt', item['prompt'])
            # Show a figure only when the question names the illustrated people.
            value['speaker'] = item.get('speaker')
        else:
            value.update(word=SKILLS[skill]['word'], speaker=item['speaker'],
                         cueAudio=[f'{skill}-cue'] if skill in NATURE else [f'review_speaker-{item["speaker"]}', f'review_cue-{skill}'])
            if current.get('hintLevel', 0) >= 2 or current.get('solved'):
                value['highlight'] = item['answerZones']
        if phase in QUIZZES and current.get('answered'):
            value['answer'] = item['answer']  # only the submitted item
    return deepcopy(value)


def apply(state, data, now):
    if state['lessonHash'] != LESSON_HASH:
        raise SampleError('样板已更新，请在家长视图中开始一次新体验。')
    if not isinstance(data, dict) or set(data) - {'action', 'choice'} or not isinstance(data.get('action'), str):
        raise SampleError('操作格式无效。')
    state = deepcopy(state)
    action, choice, phase = data['action'], data.get('choice'), state['phase']
    current, item = state['current'], activity(state)
    if action == 'start' and phase == 'welcome' and choice in ('play', 'check'):
        enter(state, 'explore' if choice == 'play' else 'check')
    elif action == 'explore' and phase == 'explore' and choice in ['sky', 'earth', *PEOPLE]:
        skill = choice if choice in NATURE else 'person'
        if skill not in state['explored']:
            state['explored'].append(skill)
        current.update(skill=skill, highlight=[choice], feedback=SKILLS[skill]['explanation'],
                       feedbackAudio=SKILLS[skill]['learnAudio'])
    elif action == 'demo' and phase == 'role-demo' and choice in ['teal', 'coral', 'me', 'you', 'he']:
        state['demoSpeaker' if choice in PEOPLE else 'demoRole'] = choice
        speaker, role = state['demoSpeaker'], state['demoRole']
        current.update(feedback=SKILLS[role]['explanation'],
                       feedbackAudio=[f'review_speaker-{speaker}', f'explain-{role}'])
    elif action in ('hint', 'adult') and item and not current.get('answered') and not current.get('solved'):
        if action == 'hint':
            level = min(current.get('hintLevel', 0) + 1, 2)
            # Quiz stories can name different speakers than the garden game.
            # A generic semantic cue must not refer to the game's gold mic.
            quiz_hint = phase in QUIZZES
            current.update(hintLevel=level,
                           feedback=SKILLS[item['skill']]['explanation'] if quiz_hint else hints_for(item['skill'], item.get('speaker'))[level - 1],
                           feedbackAudio=[f'explain-{item["skill"]}' if quiz_hint else f'hint-{item["skill"]}-{level}'])
        else:
            current.update(adultHelp=True, feedback='一起完成也没关系，再自己试一试。', feedbackAudio=['adult'])
    elif action == 'choose' and item and not current.get('answered') and not current.get('solved'):
        if phase in QUIZZES:
            if choice not in [o['value'] for o in item['options']]:
                raise SampleError('请选题目里的一个字。')
            correct = choice == item['answer']
            result = {'id': item['id'], 'skill': item['skill'], 'response': choice, 'correct': correct,
                      'hintLevel': current.get('hintLevel', 0), 'adultHelp': current.get('adultHelp', False),
                      'independent': correct and not current.get('hintLevel') and not current.get('adultHelp'), 'at': now}
            state[phase].append(result)
            current.update(answered=True, correct=correct, selected=choice,
                           feedback=('找到了！' if correct else '这次还没选对。') + item['explanation'],
                           feedbackAudio=[f'explain-{item["skill"]}'])
        else:
            choices = ['sky', 'earth', *PEOPLE] if item['skill'] in NATURE else PEOPLE
            if choice not in choices:
                raise SampleError('请点图里可以选择的地方。')
            correct = choice in item['answerZones']
            current['attempts'] = current.get('attempts', 0) + 1
            current.update(correct=correct, selected=choice, solved=correct)
            if correct:
                state.setdefault('replayPractice' if state.get('replaying') else 'practice', []).append({'id': item['id'], 'skill': item['skill'], 'attempts': current['attempts'],
                    'hintLevel': current.get('hintLevel', 0), 'adultHelp': current.get('adultHelp', False)})
                current.update(feedback='找到了！' + SKILLS[item['skill']]['explanation'],
                               feedbackAudio=[f'explain-{item["skill"]}'])
            else:
                current.setdefault('wrongChoices', []).append(choice)
                current.update(feedback='再看看，试试另一处。也可以点小灯泡听提示。', feedbackAudio=['wrong'])
    elif action == 'next':
        if phase == 'explore' and len(state['explored']) == 3:
            enter(state, 'hunt')
        elif phase == 'role-demo':
            enter(state, 'roles')
        elif item and (current.get('answered') or current.get('solved')):
            if state['index'] + 1 < phase_total(state):
                enter(state, phase, state['index'] + 1)
            elif phase == 'hunt':
                enter(state, 'role-demo')
            elif phase == 'roles':
                if state.get('replaying'):
                    state['replaying'] = False
                    enter(state, state['returnPhase'])
                else:
                    enter(state, 'check')
            elif phase == 'check':
                state['repairSkills'] = [r['skill'] for r in state['check'] if not r['independent']]
                enter(state, 'repair' if state['repairSkills'] else 'transfer')
            elif phase == 'repair':
                enter(state, 'transfer')
            elif phase == 'transfer':
                state.update(completedAt=now, reviewDueAt=now + LESSON['reviewDelaySeconds'])
                enter(state, 'complete')
            elif phase == 'review-preview':
                enter(state, state['returnPhase'])
            elif phase == 'review':
                enter(state, 'review-complete')
        else:
            raise SampleError('先完成眼前的小任务，再往下走。')
    elif action == 'replay' and phase in ('complete', 'review-complete'):
        state.update(returnPhase=phase, replaying=True, explored=[])
        enter(state, 'explore')
    elif action == 'review' and phase in ('complete', 'review-complete') and choice in ('due', 'preview'):
        if choice == 'due':
            if not state['reviewDueAt'] or now < state['reviewDueAt'] or state['review']:
                raise SampleError('真正的复习还没到时间，或已经完成。可以先体验复习玩法。')
            enter(state, 'review')
        else:
            state['returnPhase'] = phase
            state['review-preview'] = []
            enter(state, 'review-preview')
    else:
        raise SampleError('这个操作不适用于当前环节，请刷新后继续。')
    state['revision'] += 1
    return state


def report(state, now):
    def summary(key):
        rows = state[key]
        return {'answered': len(rows), 'correct': sum(r['correct'] for r in rows),
                'independent': sum(r['independent'] for r in rows),
                'helped': sum(bool(r['hintLevel'] or r['adultHelp']) for r in rows)}
    transfer = summary('transfer')
    weak = [SKILLS[r['skill']]['word'] for r in state['transfer'] if not r['independent']]
    practice_adult = sum(bool(r['adultHelp']) for r in state['practice'])
    adult = practice_adult + sum(r['adultHelp'] for k in ('check', 'transfer', 'review') for r in state[k])
    # A sample completion is not a mastery decision or a learning-time claim.
    intervention = bool(state['completedAt'] and (transfer['independent'] < 3 or adult >= 3))
    return {'sampleOnly': True, 'completed': state['completedAt'] is not None,
            'check': summary('check'), 'transfer': transfer, 'review': summary('review'),
            'practiceRounds': len(state['practice']), 'practiceRetries': sum(r['attempts'] - 1 for r in state['practice']),
            'hintedRounds': sum(bool(r['hintLevel']) for r in state['practice']) + sum(bool(r['hintLevel']) for k in ('check', 'transfer', 'review') for r in state[k]),
            'adultHelpRounds': adult, 'repairWords': [SKILLS[k]['word'] for k in state['repairSkills']],
            'reviewDueAt': state['reviewDueAt'], 'reviewAvailable': view(state, now)['reviewAvailable'],
            'interventionSuggested': intervention,
            'nextStep': ('建议陪孩子指图说一小会儿，观察是否听懂操作和角色变化。' if intervention else
                         ('明天先复习：' + '、'.join(weak) + '。系统读题，家长无需逐题讲解。' if weak else
                          '本轮无需额外陪练；明天由课件带孩子简短复习。')) if state['completedAt'] else '体验还在进行，完成后再判断是否需要陪练。',
            'notAssessed': LESSON['notAssessed'],
            'objectives': [{'word': skill['word'], **{phase: next(({'correct': r['correct'], 'independent': r['independent']} for r in state[phase] if r['skill'] == key), None) for phase in ('check', 'transfer', 'review')}} for key, skill in SKILLS.items()]}
