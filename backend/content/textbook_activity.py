"""Versioned native OpenMAIC activity. All judgments remain on the server.

The plan extends one exact immutable release at delivery time. It reuses that
release's reviewed illustration/audio, and stores evidence in learning_sessions.
Practice retries never replace the first independent assessment.
"""
from copy import deepcopy
from pathlib import Path

from content.textbook_release import grade_answers, questions
from core.errors import ApiError
from content.textbook_journey_registry import course_json

ROOT = Path(__file__).parent / 'textbooks/activities'


def _plan():
    return course_json(ROOT / 'tiandiren.v1.json', source_root=ROOT)


def __getattr__(name):
    if name == 'PLAN':
        return _plan()
    raise AttributeError(name)


ZONES = ['sky', 'earth', 'coral', 'teal', 'yellow']


def supported(release):
    PLAN = _plan()
    return release.get('sha256') == PLAN['releaseSha256']


def attach(classroom, release):
    PLAN = _plan()
    if supported(release):
        for scene in classroom['scenes']:
            for section, scene_id in PLAN['sceneIds'].items():
                if scene['id'] == scene_id:
                    scene['miraActivity'] = {'id': PLAN['id'], 'section': section}
                    # The native scene plays the current task's reviewed cues.
                    # Running the old linear script would read future quiz
                    # questions or role instructions over a different activity.
                    scene['actions'] = []
                    if section == 'games':
                        scene['content'].pop('html', None)
                        scene['content'].pop('url', None)


def initial(progress, release):
    PLAN = _plan()
    stored = progress.get('textbookPlay')
    if stored:
        if stored.get('id') != PLAN['id']:
            raise ApiError('textbook_play_version', '互动版本发生变化，请重新进入课堂', 409)
        return deepcopy(stored)
    state = {'id': PLAN['id'], 'version': 0, 'games': {'phase': 'hunt', 'index': 0, 'records': []},
             'challenge': {'phase': 'quiz', 'index': 0, 'records': []}}
    # Previously submitted published-course scores are immutable, too.
    if progress.get('quiz'):
        section = state['challenge']
        for i, result in enumerate(progress['quiz']['results']):
            section['records'].append({'phase': 'quiz', 'index': i, 'skill': PLAN['quizSkills'][i],
                'choice': result['response'], 'correct': result['correct'], 'hintUsed': result.get('hintUsed', False),
                'adultHelp': result.get('adultHelp', False), 'attempts': 1, 'solved': result['correct']})
        section.update(phase='repair', index=0)
        if not repair_skills(section):
            section['phase'] = 'transfer'
    return state


def repair_skills(section):
    return [r['skill'] for r in section['records'] if r['phase'] == 'quiz'
            and (not r['correct'] or r['hintUsed'] or r['adultHelp'])]


def item(section, release):
    PLAN = _plan()
    phase, index = section['phase'], section['index']
    if phase == 'done':
        return None
    if phase == 'quiz':
        q = questions(release['classroom'])[index]
        return {'skill': PLAN['quizSkills'][index], 'speaker': PLAN['quizSpeakers'][index],
                'question': q, 'targets': [q['answer'][0]], 'total': 6}
    if phase == 'hunt':
        value = {'skill': ['sky', 'earth', 'person'][index], 'total': 3}
    elif phase == 'roles':
        value = {**PLAN['roles'][index], 'total': len(PLAN['roles'])}
    elif phase == 'repair':
        skills = repair_skills(section)
        value = {'skill': skills[index], 'speaker': 'coral', 'total': len(skills)}
    else:
        value = {**PLAN['transfer'][index], 'total': len(PLAN['transfer'])}
    skill, speaker = value['skill'], value.get('speaker', 'teal')
    value['targets'] = PLAN['skills'][skill].get('zones') or [
        speaker if skill == 'me' else ('teal' if speaker == 'coral' else 'coral') if skill == 'you' else 'yellow']
    return value


def record_for(section):
    return next((r for r in section['records'] if r['phase'] == section['phase']
                 and r['index'] == section['index']), None)


def advance(state, section_name, data, release):
    if (not isinstance(data, dict) or set(data) - {'section', 'version', 'action', 'choice'}
            or section_name not in ('games', 'challenge') or type(data.get('version')) is not int):
        raise ApiError('textbook_play_invalid', '互动操作无效', 400)
    if data['version'] != state['version']:
        raise ApiError('textbook_play_conflict', '进度已更新，正在恢复已保存的位置', 409)
    section = state[section_name]
    phase, action = section['phase'], data.get('action')
    if action == 'replay' and section_name == 'games' and phase == 'done':
        state['games'] = {'phase': 'hunt', 'index': 0, 'records': [], 'replaying': True,
                          'firstRun': section.get('firstRun', section['records'])}
    else:
        current = item(section, release)
        if current is None:
            raise ApiError('textbook_play_finished', '这一关已完成', 409)
        record = record_for(section)
        if action in ('hint', 'adult'):
            if section.get('feedback') and section['feedback']['canNext']:
                raise ApiError('textbook_play_answered', '回答已保存，请继续下一题', 409)
            section['hintUsed' if action == 'hint' else 'adultHelp'] = True
            # An aid after an incorrect attempt is practice help; first evidence stays unchanged.
        elif action == 'answer':
            choices = [o['value'] for o in current['question']['options']] if phase == 'quiz' else ZONES
            choice = data.get('choice')
            if not isinstance(choice, str) or choice not in choices:
                raise ApiError('textbook_play_choice', '请点选图中位置或题目选项', 400)
            if section.get('feedback', {}).get('canNext'):
                raise ApiError('textbook_play_answered', '回答已保存，请继续下一题', 409)
            correct = choice in current['targets']
            if record is None:
                record = {'phase': phase, 'index': section['index'], 'skill': current['skill'],
                    'choice': choice, 'correct': correct, 'hintUsed': bool(section.get('hintUsed')),
                    'adultHelp': bool(section.get('adultHelp')), 'attempts': 0, 'solved': False}
                section['records'].append(record)
            record['attempts'] += 1
            record['solved'] = correct
            section['feedback'] = {'correct': correct, 'canNext': correct or phase in ('quiz', 'transfer')}
        elif action == 'next':
            if not section.get('feedback', {}).get('canNext'):
                raise ApiError('textbook_play_unfinished', '先试一试眼前的小任务', 409)
            section['index'] += 1
            for key in ('feedback', 'hintUsed', 'adultHelp'):
                section.pop(key, None)
            if section['index'] >= current['total']:
                section['index'] = 0
                section['phase'] = {'hunt': 'roles', 'roles': 'done', 'quiz': 'repair',
                                    'repair': 'transfer', 'transfer': 'done'}[phase]
                if section['phase'] == 'repair' and not repair_skills(section):
                    section['phase'] = 'transfer'
        else:
            raise ApiError('textbook_play_invalid', '互动操作无效', 400)
    state['version'] += 1
    return state


def quiz_result(state, release):
    records = [r for r in state['challenge']['records'] if r['phase'] == 'quiz']
    if len(records) != 6:
        return None
    result = grade_answers(release, {q['id']: r['choice'] for q, r in zip(questions(release['classroom']), records)})
    for graded, record in zip(result['results'], records):
        graded.update(hintUsed=record['hintUsed'], adultHelp=record['adultHelp'])
    result['independentCorrectCount'] = sum(r['correct'] and not r['hintUsed'] and not r['adultHelp'] for r in records)
    result['hintCount'] = sum(r['hintUsed'] for r in records)
    result['adultHelpCount'] = sum(r['adultHelp'] for r in records)
    return result


def complete(progress):
    state = progress.get('textbookPlay', {})
    games = state.get('games', {})
    return bool((games.get('phase') == 'done' or games.get('replaying'))
                and state.get('challenge', {}).get('phase') == 'done')


def public_view(state, release):
    PLAN = _plan()
    allowed = {m['path'] for m in release['media']}
    audio = {a['id']: a.get('audioUrl') for s in release['classroom']['scenes']
             for a in s.get('actions', []) if a.get('audioUrl') in allowed}
    image = next(m['path'] for m in release['media'] if m['mimeType'].startswith('image/'))
    views = {}
    for section_name in ('games', 'challenge'):
        section = state[section_name]
        current = item(section, release)
        view = {'phase': section['phase'], 'index': section['index'], 'done': current is None,
                'replaying': section.get('replaying', False), 'hintUsed': bool(section.get('hintUsed')),
                'adultHelp': bool(section.get('adultHelp'))}
        if current:
            skill = PLAN['skills'][current['skill']]
            role = current['skill'] in ('me', 'you', 'he')
            q = current.get('question')
            hint_ids = ([PLAN['roleSwitchAudio']]
                        if current.get('speaker') == 'coral' and current['skill'] in ('me', 'you')
                        else skill['learnAudio'])
            cues = ([q['questionAudioUrl']] if q else
                    [audio.get('review_speaker-' + current.get('speaker', 'teal')),
                     audio.get('review_cue-' + current['skill'])] if role else
                    [audio.get(skill['learnAudio'][-1])])
            view.update(total=current['total'],
                prompt=q['question'] if q else f'把「{skill["word"]}」送到图里' if not role else f'谁是「{skill["word"]}」？',
                speaker=current.get('speaker') if role and not q else None,
                options=q['options'] if q else None, audio=[a for a in cues if a in allowed],
                hintAudio=[audio[a] for a in hint_ids if a in audio]
                    if section.get('hintUsed') or section.get('feedback') else [])
            if not q:
                view['word'] = skill['word']
            if section.get('hintUsed'):
                view['hint'] = skill['hints'][-1]
            if section.get('feedback'):
                view['feedback'] = {**section['feedback'], 'explanation': q['analysis'] if q else skill['explanation']}
        views[section_name] = view
    first = [r for r in state['challenge']['records'] if r['phase'] == 'quiz']
    transfer = [r for r in state['challenge']['records'] if r['phase'] == 'transfer']
    def independent(records):
        return sum(bool(r['correct'] and not r['hintUsed'] and not r['adultHelp']) for r in records)
    return {'ok': True, 'activityId': PLAN['id'], 'version': state['version'], 'image': image, **views,
            'evidence': {'answered': len(first), 'independent': independent(first),
                'hints': sum(r['hintUsed'] for r in first), 'adultHelp': sum(r['adultHelp'] for r in first),
                'transferAnswered': len(transfer), 'transferIndependent': independent(transfer),
                'practiceSkills': [PLAN['skills'][s]['word'] for s in repair_skills(state['challenge'])]}}
