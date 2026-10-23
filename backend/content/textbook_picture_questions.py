"""Answer-blind picture presentation for the existing six-skill lesson."""
from copy import deepcopy
from pathlib import Path
from content.textbook_journey_registry import course_json

ROOT = Path(__file__).parent / 'textbooks/activities'


def __getattr__(name):
    if name == 'VISUALS':
        return course_json(ROOT / 'tiandiren.visuals.v1.json', source_root=ROOT)
    raise AttributeError(name)


def presentation(current, phase):
    if not current.get('options'):
        return {}
    VISUALS = __getattr__('VISUALS')
    key = f'{phase}-{current["skill"]}' if phase in ('diagnostic', 'probe') else current['id']
    scene = deepcopy(VISUALS['scenes'][key])
    pictures = {'天': 'sky', '地': 'earth', '人': 'people', '头顶': 'above', '脚下': 'below',
        '小朋友': 'teal', '石头': 'rock', **VISUALS['portraits'],
        '我': scene.get('speaker', 'teal'), '你': scene.get('listener', 'coral'), '他': 'yellow'}
    options = []
    for option in current['options']:
        # Never derive a picture from the private correct-answer key.
        if option['label'] not in pictures:
            raise ValueError('Missing authored picture for low-grade answer choice')
        options.append({**option, 'picture': pictures[option['label']]})
    if len({o['picture'] for o in options}) != len(options):
        raise ValueError('Low-grade answer pictures must be visually distinguishable')
    return {'visual': scene, 'options': options, 'responseMode': 'picture_choice'}
