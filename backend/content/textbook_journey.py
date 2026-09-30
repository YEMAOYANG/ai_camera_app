"""Server-owned adaptive lesson, verified repair and spaced retrieval.

Authored rules and question banks live beside the immutable release. No scores
are inferred from scene visits. A completed sitting is not durable mastery.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from content import textbook_activity as legacy
from content.textbook_picture_questions import presentation
from content.textbook_journey_registry import definition, definitions, skills_for, supported
from core.errors import ApiError
from core.security import now_ms

PLAN = legacy.PLAN
ROOT = Path(__file__).parent / 'textbooks/activities'
FLOW = json.loads((ROOT / 'tiandiren.journey.v2.json').read_text())
SUPPORT = json.loads((ROOT.parent.parent / 'learning_parent_support.v1.json').read_text())
NAVIGATION = json.loads((ROOT.parent.parent / 'learning_navigation.v1.json').read_text())['cues']
SKILLS = FLOW['skills']
DAY = 86400000


def attach(classroom, release):
    if not supported(release):
        return
    PLAN = definition(release=release).plan
    for scene in classroom['scenes']:
        for section, scene_id in PLAN['sceneIds'].items():
            if scene['id'] == scene_id:
                scene['miraActivity'] = {'id': PLAN['id'], 'section': section}
                scene['actions'] = []
                if section == 'games':
                    scene['content'].pop('html', None)
                    scene['content'].pop('url', None)
    # Start with a short check. Original narrated pages stay available as a
    # reference; only the adaptive activities determine this lesson's route.
    scenes = sorted(classroom['scenes'], key=lambda s: s['order'])
    games = next(s for s in scenes if s['id'] == PLAN['sceneIds']['games'])
    scenes.remove(games)
    scenes.insert(0, games)
    for i, scene in enumerate(scenes):
        scene['order'] = i
    classroom['scenes'] = scenes


def _section(phase, queue=None):
    return {'phase': phase, 'index': 0, 'queue': queue or [], 'records': [], 'round': 0}


def initial(progress, release):
    spec = definition(release=release)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    previous = progress.get('textbookPlay')
    if previous and previous.get('flowVersion') == 2:
        definition(state=previous, release=release)
        return deepcopy(previous)
    state = {'id': PLAN['id'], 'flowVersion': 2, 'version': (previous or {}).get('version', 0),
             'games': _section('diagnostic', SKILLS[:]), 'challenge': _section('locked'),
             'baseline': [], 'verified': [], 'diagnoses': {}, 'reviewHistory': [],
             'reviewLevel': 0, 'reviewDueAt': None, 'reviewTaskId': None,
             'parentNeeded': False, 'status': 'learning', 'run': 0, 'variant': 0, 'usedItems': {}}
    # Preserve legacy evidence verbatim, then require the NEW context check.
    if previous:
        state['legacyEvidence'] = deepcopy(previous)
    old_quiz = progress.get('quiz')
    if old_quiz:
        state['legacyQuiz'] = deepcopy(old_quiz)
        for skill, r in zip(PLAN['quizSkills'], old_quiz['results']):
            state['baseline'].append({'skill': skill, 'choice': r['response'], 'correct': r['correct'],
                'hintUsed': r.get('hintUsed', False), 'adultHelp': r.get('adultHelp', False)})
        _route_learning(state)
    return state


def independent(record):
    return bool(record.get('correct') and not record.get('hintUsed') and not record.get('adultHelp'))


def repair_skills(section):
    return list(dict.fromkeys(r['skill'] for r in section['records'] if not independent(r)))


def _route_learning(state):
    spec = definition(state=state)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    missing = [r['skill'] for r in state['baseline'] if not independent(r)]
    # Do not equate one precheck answer with mastery; everyone gets a new context.
    games = state['games']
    games.update(phase='hunt' if missing else 'done', index=0,
                 queue=[skill for skill in missing for _ in range(PLAN['skills'][skill].get('practiceRepeats', 2 if skill in ('me', 'you', 'he') else 1))])
    games.pop('feedback', None)
    state['skippedSkills'] = [s for s in SKILLS if s not in missing]
    if not missing:
        _start_check(state)


def _start_check(state):
    spec = definition(state=state)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    state['challenge'] = _section('transfer', SKILLS[:])
    state['verified'] = []
    state['status'] = 'reviewing' if state.get('reviewActive') else 'checking'


def item(section, release, state=None):
    spec = definition(state=state, release=release)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    phase = section['phase']
    if phase in ('done', 'locked', 'break'):
        return None
    skill = section['queue'][section['index']]
    if phase == 'diagnostic':
        q = legacy.questions(release['classroom'])[PLAN['quizSkills'].index(skill)]
        return {'skill': skill, 'id': q['id'], 'prompt': q['question'], 'options': q['options'],
                'targets': q['answer'], 'audio': [q['questionAudioUrl']], 'explanation': PLAN['skills'][skill]['explanation'],
                'hints': PLAN['skills'][skill]['hints'] + [q['analysis']], 'total': len(section['queue']),
                **(FLOW.get('diagnosticPictures', {}).get(skill, {}))}
    if phase == 'probe':
        return {**FLOW['probes'][skill], 'skill': skill, 'total': len(section['queue'])}
    if phase == 'transfer':
        bank = FLOW['bank'][skill]
        variant = ((state or {}).get('variant', 0) + section['round']) % len(bank)
        previous = record_for(section)
        if previous:
            question = next(q for q in bank if q['id'] == previous['questionId'])
        else:
            candidates = bank[variant:] + bank[:variant]
            question = next(q for q in candidates if q['id'] not in (state or {}).get('usedItems', {}))
        return {**question, 'skill': skill, 'total': len(section['queue'])}
    if spec.renderer == 'picture_choices':
        return {**FLOW['practice'][skill], 'skill': skill, 'total': len(section['queue'])}
    speaker = section.get('speaker') or ('coral' if (section['round'] + section['index']) % 2 else 'teal')
    value = PLAN['skills'][skill]
    target = value.get('zones') or [speaker if skill == 'me' else
              ('teal' if speaker == 'coral' else 'coral') if skill == 'you' else 'yellow']
    return {'skill': skill, 'id': f'{phase}-{skill}-{speaker}', 'word': value['word'],
            'speaker': speaker if skill in ('me', 'you', 'he') else None,
            'prompt': f'把“{value["word"]}”送到图里。', 'targets': target,
            'hints': value['hints'] + [value['explanation']], 'explanation': value['explanation'],
            'total': len(section['queue'])}


def record_for(section):
    return next((r for r in reversed(section['records']) if r['phase'] == section['phase']
                 and r['index'] == section['index'] and r['round'] == section['round']), None)


def _clear_feedback(section):
    for key in ('feedback', 'hintLevel', 'adultHelp', 'speaker'):
        section.pop(key, None)


def _finish_round(state, timestamp):
    spec = definition(state=state)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    section = state['challenge']
    missing = [s for s in SKILLS if s not in state['verified']]
    if not missing:
        section.update(phase='done', index=0)
        state['parentNeeded'] = False
        state['status'] = 'retained' if state.get('reviewActive') and state['reviewLevel'] == len(FLOW['reviewIntervalsDays']) - 1 else 'session_passed'
        if state.get('reviewActive'):
            state['reviewHistory'].append({'level': state['reviewLevel'], 'completedAt': timestamp,
                'independentSkills': state['verified'][:], 'records': deepcopy(section['records'])})
            state['reviewLevel'] += 1
        else:
            state.setdefault('firstVerifiedAt', timestamp)
        state['reviewActive'] = False
        level = state['reviewLevel']
        state['reviewDueAt'] = timestamp + FLOW['reviewIntervalsDays'][level] * DAY if level < len(FLOW['reviewIntervalsDays']) else None
        state['lastVerifiedAt'] = timestamp
        return
    if (section['round'] >= FLOW['maxRepairRounds']
            or any(all(q['id'] in state.get('usedItems', {}) for q in FLOW['bank'][skill]) for skill in missing)):
        section.update(phase='break', index=0, queue=missing)
        state.update(status='needs_support', parentNeeded=True)
        return
    section.update(phase='probe', index=0, queue=missing, round=section['round'] + 1)


def advance(state, section_name, data, release, *, timestamp=None):
    spec = definition(state=state, release=release)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    timestamp = now_ms() if timestamp is None else timestamp
    if (not isinstance(data, dict) or set(data) - {'section', 'version', 'action', 'choice'}
            or section_name not in ('games', 'challenge') or type(data.get('version')) is not int):
        raise ApiError('textbook_play_invalid', '互动操作无效', 400)
    if state['version'] != data['version']:
        raise ApiError('textbook_play_conflict', '进度已更新，请继续保存的位置', 409)
    action = data.get('action')
    section = state[section_name]
    phase = section['phase']
    if action == 'review' and section_name == 'challenge':
        if (phase != 'done' or state['reviewDueAt'] is None or timestamp < state['reviewDueAt']):
            raise ApiError('textbook_review_not_due', '到时间再来复习，今天可以休息啦', 409)
        state['previousCheck'] = deepcopy(section)
        state.update(reviewActive=True, run=state['run'] + 1, variant=(state['reviewLevel'] + 1) * 3, usedItems={})
        _start_check(state)
    elif action == 'resume' and section_name == 'challenge' and phase == 'break':
        seen = {key: at for key, at in state.get('usedItems', {}).items() if timestamp - at < DAY}
        if any(all(q['id'] in seen for q in FLOW['bank'][skill]) for skill in section['queue']):
            raise ApiError('textbook_rest_needed', '今天已经练习很多了。先休息，明天再来试一试。', 409)
        state['usedItems'] = seen
        state['supportHistory'] = state.get('supportHistory', []) + [deepcopy(section)]
        section.update(phase='probe', index=0, round=0)
        section['records'] = []
        _clear_feedback(section)
        state['status'] = 'reviewing' if state.get('reviewActive') else 'checking'
        # Clear the intervention only after an independent new check succeeds.
    elif action == 'replay' and section_name == 'games' and phase == 'done':
        state['games'] = _section('hunt', SKILLS[:])
        state['games']['replaying'] = True
    else:
        current = item(section, release, state)
        if current is None:
            raise ApiError('textbook_play_finished', '请先完成前面的任务', 409)
        if section.get('feedback', {}).get('canNext') and action != 'next':
            raise ApiError('textbook_play_answered', '回答已保存，请继续', 409)
        if action == 'speaker' and phase in ('hunt', 'repair') and current.get('speaker'):
            if data.get('choice') not in ('coral', 'teal'):
                raise ApiError('textbook_play_invalid', '请选择说话的小朋友', 400)
            section['speaker'] = data['choice']
        elif action == 'hint':
            section['hintLevel'] = min(section.get('hintLevel', 0) + 1, 3)
        elif action == 'adult':
            section['adultHelp'] = True
        elif action == 'answer':
            choices = [o['value'] for o in current['options']] if current.get('options') else legacy.ZONES
            choice = data.get('choice')
            if not isinstance(choice, str) or choice not in choices:
                raise ApiError('textbook_play_choice', '请选一个答案', 400)
            correct = choice in current['targets']
            record = record_for(section)
            if record is None:
                record = {'phase': phase, 'index': section['index'], 'round': section['round'],
                    'skill': current['skill'], 'questionId': current['id'], 'choice': choice,
                    'correct': correct, 'hintUsed': section.get('hintLevel', 0) > 0,
                    'hintLevel': section.get('hintLevel', 0), 'adultHelp': bool(section.get('adultHelp')),
                    'attempts': 0, 'solved': False}
                section['records'].append(record)
                if phase == 'diagnostic':
                    state['baseline'].append(deepcopy(record))
                elif phase == 'transfer':
                    state.setdefault('usedItems', {})[current['id']] = timestamp
                    if independent(record) and current['skill'] not in state['verified']:
                        state['verified'].append(current['skill'])
                elif phase == 'probe':
                    state['diagnoses'][current['skill']] = {
                        'basis': '独立追问' if independent(record) else '追问仍需帮助',
                        'observation': ('能理解情境，字词对应还需巩固' if independent(record) else
                                        '空间位置还需辨认' if current['skill'] in ('sky', 'earth') else
                                        '人物和物品还需区分' if current['skill'] == 'person' else PLAN['skills'][current['skill']].get('observation', '说话、听话和谈到的人还需区分'))}
            record['attempts'] += 1
            record['solved'] = correct
            # Guided play never produces independent assessment credit.
            can_next = correct or phase in ('diagnostic', 'transfer', 'probe') or record['attempts'] >= 3
            section['feedback'] = {'correct': correct, 'canNext': can_next}
            if record['attempts'] >= 3 and not correct:
                section['hintLevel'] = 3
        elif action == 'next':
            if not section.get('feedback', {}).get('canNext'):
                raise ApiError('textbook_play_unfinished', '先试一试眼前的小任务', 409)
            section['index'] += 1
            _clear_feedback(section)
            if section['index'] >= current['total']:
                section['index'] = 0
                if phase == 'diagnostic':
                    _route_learning(state)
                elif phase == 'hunt':
                    section['phase'] = 'done'
                    if not section.get('replaying'):
                        _start_check(state)
                elif phase == 'probe':
                    section['phase'] = 'repair'
                elif phase == 'repair':
                    section['phase'] = 'transfer'
                else:
                    _finish_round(state, timestamp)
        else:
            raise ApiError('textbook_play_invalid', '互动操作无效', 400)
    state['version'] += 1
    state['updatedAt'] = timestamp
    return state


def quiz_result(state, release):
    spec = definition(state=state, release=release)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    if state.get('legacyQuiz'):
        return deepcopy(state['legacyQuiz'])
    if len(state['baseline']) != len(SKILLS):
        return None
    records = {r['skill']: r for r in state['baseline']}
    answers = {q['id']: records[skill]['choice'] for q, skill in zip(legacy.questions(release['classroom']), PLAN['quizSkills'])}
    result = legacy.grade_answers(release, answers)
    for row, skill in zip(result['results'], PLAN['quizSkills']):
        row.update(hintUsed=records[skill]['hintUsed'], adultHelp=records[skill]['adultHelp'])
    result.update(independentCorrectCount=sum(independent(r) for r in state['baseline']),
                  hintCount=sum(r['hintUsed'] for r in state['baseline']),
                  adultHelpCount=sum(r['adultHelp'] for r in state['baseline']))
    return result


def complete(progress):
    state = progress.get('textbookPlay') or {}
    if state.get('flowVersion') != 2:
        return legacy.complete(progress)
    return state['challenge']['phase'] == 'done' and len(state['verified']) == len(skills_for(state))


def audio_id(text):
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def audio_url(text):
    return '/mira/textbook-audio/' + audio_id(text) + '.wav'


def summary(state, *, timestamp=None):
    spec = definition(state=state)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    timestamp = now_ms() if timestamp is None else timestamp
    due = state.get('reviewDueAt')
    missing = [PLAN['skills'][s]['word'] for s in SKILLS if s not in state['verified']]
    status = state['status']
    support = parent_support(state)
    next_action = (support['action'] if support else
        '打开课堂，完成今天的短复习。' if due is not None and due <= timestamp else
        '两轮间隔复习已通过，可以继续学校当前课程。' if status == 'retained' else
        '已安排下次短复习，暂时不需要家长辅导。' if due else '回到课堂，继续尚未完成的小任务。')
    return {'status': status, 'parentNeeded': state['parentNeeded'], 'nextStep': next_action,
        'independentBefore': sum(independent(r) for r in state['baseline']), 'verifiedCount': len(state['verified']),
        'remainingSkills': missing, 'reviewDueAt': due, 'reviewDue': due is not None and due <= timestamp,
        'reviewLevel': state['reviewLevel'], 'diagnoses': [f'{PLAN["skills"][s]["word"]}：{v["observation"]}' for s, v in state['diagnoses'].items()],
        'updatedAt': state.get('updatedAt'), 'skippedCount': len(state.get('skippedSkills', [])),
        'parentSupport': support, 'skillCount': len(SKILLS)}


def parent_support(state):
    spec = definition(state=state)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    if not state.get('parentNeeded'):
        return None
    missing = next((s for s in SKILLS if s not in state.get('verified', [])), None)
    advice = PLAN.get('parentSupport', {}).get(missing) or SUPPORT.get(state['id'], {}).get(missing)
    return ({**advice, 'handBack': SUPPORT['handBack'], 'expectedSeconds': SUPPORT['expectedSeconds']}
            if advice else None)


def public_view(state, release):
    spec = definition(state=state, release=release)
    PLAN, FLOW, SKILLS = spec.plan, spec.flow, spec.skills
    allowed = {m['path'] for m in release['media']}
    image = next(m['path'] for m in release['media'] if m['mimeType'].startswith('image/'))
    views = {}
    for name in ('games', 'challenge'):
        section = state[name]
        current = item(section, release, state)
        level = section.get('hintLevel', 0)
        view = {'phase': section['phase'], 'index': section['index'], 'done': section['phase'] == 'done',
                'replaying': section.get('replaying', False), 'hintUsed': level > 0, 'hintLevel': level,
                'adultHelp': bool(section.get('adultHelp'))}
        if current:
            prompt = current['prompt']
            if current.get('speaker'):
                prompt = ('蓝衣男孩在说话，红衣女孩在听。' if current['speaker'] == 'teal' else
                          '红衣女孩在说话，蓝衣男孩在听。') + prompt
            options = current.get('options')
            narration = prompt + (''.join(o['value'] + '，' + o['label'] + '。' for o in options) if options else '')
            view.update(prompt=prompt, total=current['total'], options=options,
                context=current.get('context'), speaker=current.get('speaker'),
                audio=current.get('audio') or [audio_url(narration)], hintAudio=[])
            if spec.renderer == 'tiandiren':
                view.update(presentation(current, section['phase']))
            else:
                # A new lesson cannot load a picture outside its reviewed release.
                arts = [current['visual']['art']] + [o['picture'] for o in current['options']]
                if any(not isinstance(a, dict) or a.get('src') not in allowed for a in arts):
                    raise ApiError('textbook_picture_unavailable', '本课图片还未准备完整', 409)
                view.update(visual=current['visual'], options=current['options'])
            if current.get('word'):
                view['word'] = current['word']
            if level:
                hint = current['hints'][min(level, len(current['hints'])) - 1]
                view.update(hint=hint, hintAudio=[audio_url(hint)])
                if level == 3:
                    view['demonstration'] = current['targets']
            if section.get('feedback'):
                explanation = current['explanation']
                saved = record_for(section)
                view['selectedChoice'] = saved['choice'] if saved else None
                view['feedback'] = {**section['feedback'], 'explanation': explanation,
                                    'audio': [audio_url(explanation)]}
        else:
            cue = ('gardenDone' if name == 'games' and section['phase'] == 'done' else
                   'reviewReady' if section['phase'] == 'done' and state.get('reviewDueAt') and state['reviewDueAt'] <= now_ms() else
                   'lessonDone' if section['phase'] == 'done' else
                   'restBreak' if section['phase'] == 'break' else 'locked')
            view['audio'] = [audio_url(NAVIGATION[cue])]
        views[name] = view
    evidence = {'total': len(SKILLS), 'answered': len(state['baseline']), 'independent': sum(independent(r) for r in state['baseline']),
        'hints': sum(r['hintUsed'] for r in state['baseline']), 'adultHelp': sum(r['adultHelp'] for r in state['baseline']),
        'transferAnswered': len(state['challenge']['records']), 'transferIndependent': len(state['verified']),
        'practiceSkills': [PLAN['skills'][r['skill']]['word'] for r in state['baseline'] if not independent(r)]}
    return {'ok': True, 'activityId': PLAN['id'], 'flowVersion': 2, 'version': state['version'], 'image': image,
            **views, 'evidence': evidence, 'journey': summary(state)}


def ordered_scenes(release):
    scenes = sorted(release['classroom']['scenes'], key=lambda s: s['order'])
    if supported(release):
        PLAN = definition(release=release).plan
        games = next(s for s in scenes if s['id'] == PLAN['sceneIds']['games'])
        scenes = [games] + [s for s in scenes if s['id'] != games['id']]
    return scenes


def audio_file(asset):
    entry = None
    for pack in dict.fromkeys([d.audio_pack for d in definitions()] + ['navigation-audio-v1']):
        folder = ROOT / pack
        manifest = json.loads((folder / 'manifest.json').read_text())
        entry = manifest.get(asset)
        if entry:
            break
    if not entry:
        raise ApiError('textbook_audio_missing', '没有找到这段声音', 404)
    path = (folder / entry.get('file', asset)).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ApiError('textbook_audio_invalid', '声音暂时不可用，请稍后再试', 503)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ApiError('textbook_audio_invalid', '声音暂时不可用，请稍后再试', 503)
    return path
