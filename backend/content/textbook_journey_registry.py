"""Immutable, per-release teaching definitions for the shared adaptive engine.

Adding a catalog title never enables an activity. Every definition names an
exact published release and content hashes; picture/audio release checks still
run through the existing publication pipeline.
"""
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re

from core.errors import ApiError

ROOT = Path(__file__).parent / 'textbooks/activities'


def course_json(path, *, expected_sha256=None, source_root=None):
    """Load lazily, after the backend-owned environment, without starting an app.

    Imports of teaching modules must not read a local shadow before dotenv is
    loaded. Registered originals are always read and hashed by CourseFileStore.
    """
    from core import config as _backend_environment  # noqa: F401; existing dotenv owner
    from services.course_file_store import CourseFileStore, course_bytes
    if source_root is not None and CourseFileStore().resolve(path, expected_sha256=expected_sha256) is None:
        if not Path(path).resolve().is_relative_to(Path(source_root).resolve()):
            raise ValueError('Teaching definition escaped its registry')
    return json.loads(course_bytes(path, expected_sha256=expected_sha256, max_bytes=4 * 1024 * 1024))


@dataclass(frozen=True)
class JourneyDefinition:
    plan: dict
    flow: dict
    renderer: str
    audio_pack: str

    @property
    def skills(self):
        return self.flow['skills']


def validate_definition(plan, flow, *, renderer, audio_pack):
    skills = flow.get('skills', [])
    if (not 1 <= len(skills) <= 12 or len(set(skills)) != len(skills)
            or set(skills) != set(plan.get('skills', {})) or set(plan.get('quizSkills', [])) != set(skills) or len(plan.get('quizSkills', [])) != len(skills)
            or not re.fullmatch(r'[a-f0-9]{64}', plan.get('releaseSha256', ''))
            or set(plan.get('sceneIds', {})) != {'games', 'challenge'}
            or len(set(plan['sceneIds'].values())) != 2
            or renderer not in ('tiandiren', 'picture_choices')
            or not re.fullmatch(r'[a-z0-9-]+', audio_pack)
            or flow.get('reviewIntervalsDays') != [1, 7]
            or flow.get('maxRepairRounds') != 2):
        raise ValueError('Invalid adaptive lesson definition')
    identities = set()
    for skill in skills:
        bank = flow.get('bank', {}).get(skill, [])
        if len(bank) < 9 or skill not in flow.get('probes', {}):
            raise ValueError('Each objective needs independent transfer variants and a diagnostic probe')
        items = bank + [flow['probes'][skill]]
        if renderer == 'picture_choices':
            if skill not in flow.get('practice', {}) or skill not in flow.get('diagnosticPictures', {}):
                raise ValueError('Missing guided practice or baseline pictures')
            diagnostic = flow['diagnosticPictures'][skill]
            if set(diagnostic) != {'visual', 'options'} or not diagnostic['visual'].get('art'):
                raise ValueError('Baseline illustration cannot replace the canonical release answer')
            items += [flow['practice'][skill]]
        for question in items:
            options = question.get('options', [])
            values = [o.get('value') for o in options]
            if (question.get('id') in identities or not question.get('id') or not question.get('prompt')
                    or not 2 <= len(values) <= 4 or len(set(values)) != len(values)
                    or len(question.get('targets', [])) != 1 or question['targets'][0] not in values
                    or len(question.get('hints', [])) != 3 or not question.get('explanation')):
                raise ValueError('Invalid or duplicated practice question')
            identities.add(question['id'])
            if renderer == 'picture_choices' and (not question.get('visual', {}).get('art')
                    or any(not o.get('picture') for o in options)):
                raise ValueError('Low-reading questions require meaningful scene and choice pictures')
    return JourneyDefinition(plan, flow, renderer, audio_pack)


@lru_cache(maxsize=1)
def definitions():
    registry = course_json(ROOT / 'registry.v1.json', source_root=ROOT)
    result = []
    for row in registry['definitions']:
        docs = []
        for field in ('plan', 'flow'):
            relative = row[field]['file']
            if (not isinstance(relative, str) or '\\' in relative or relative.startswith('/')
                    or any(p in {'', '.', '..'} for p in relative.split('/'))):
                raise ValueError('Teaching definition escaped its registry')
            path = ROOT / relative
            docs.append(course_json(path, expected_sha256=row[field]['sha256'], source_root=ROOT))
        result.append(validate_definition(*docs, renderer=row['renderer'], audio_pack=row['audioPack']))
    if len({d.plan['id'] for d in result}) != len(result) or len({d.plan['releaseSha256'] for d in result}) != len(result):
        raise ValueError('Ambiguous activity or release identity')
    return tuple(result)


def definition(*, state=None, release=None):
    candidates = definitions()
    if release is not None:
        candidates = [d for d in candidates if d.plan['releaseSha256'] == release.get('sha256')]
    if state:
        candidates = [d for d in candidates if d.plan['id'] == state.get('id')]
    if len(candidates) != 1:
        raise ApiError('textbook_play_version', '这份课堂的互动配置未就绪，请重新进入课堂', 409)
    selected = candidates[0]
    if release is not None:
        from content.textbook_release import questions
        scenes = {s['id'] for s in release['classroom']['scenes']}
        quiz = questions(release['classroom'])
        if not set(selected.plan['sceneIds'].values()) <= scenes or len(quiz) != len(selected.skills):
            raise ApiError('textbook_play_version', '课堂场景和教学目标数量不一致', 409)
        if selected.renderer == 'picture_choices':
            for question, skill in zip(quiz, selected.plan['quizSkills']):
                pictures = selected.flow['diagnosticPictures'][skill]['options']
                if ({o['value'] for o in question['options']} != {o.get('value') for o in pictures}
                        or len(pictures) != len(question['options'])
                        or any(not o.get('picture') for o in pictures)):
                    raise ApiError('textbook_play_version', '题目图片与已发布的选项不对应', 409)
    return selected


def supported(release):
    return any(d.plan['releaseSha256'] == release.get('sha256') for d in definitions())


def skills_for(state):
    return definition(state=state).skills
