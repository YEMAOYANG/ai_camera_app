"""Add picture choices and individual narration actions to quiz scenes."""

from copy import deepcopy
from pathlib import Path
import re

from courseware.tools.glyph_picture import png_name, render_picture


_EMOJI = re.compile('[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u200d\u20e3]')
_PREFIX = re.compile(r'^\s*(?:[①-⑳]+|\d+[.、．)）](?!\s*\d)|【[^】]*】|\[[^\]]*\])\s*')
_READING = re.compile(r'(?:自己|自行|独自|先|请|来).{0,8}(?:读题|读一读|阅读题|读一下题|读一遍题)|(?:读题|阅读题).{0,8}(?:自己|自行|独自)|read\s+(?:it|the question)\s+yourself', re.IGNORECASE)


def _question_text(text):
    text = _EMOJI.sub('', text).strip()
    while True:
        cleaned = _PREFIX.sub('', text).strip()
        if cleaned == text:
            return text
        text = cleaned


def _visual(value, stage_id, media_dir):
    if not isinstance(value, dict):
        raise ValueError('missing option visual')
    kind = value.get('kind')
    if kind == 'quantity':
        if type(value.get('count')) is not int or not 0 <= value['count'] <= 100:
            raise ValueError('invalid quantity visual')
        if 'alt' in value and (not isinstance(value['alt'], str) or not value['alt'].strip()):
            raise ValueError('visual alt must be non-empty')
        return deepcopy(value)
    if kind == 'image':
        src, alt = value.get('src'), value.get('alt')
        if not isinstance(src, str) or not src.startswith(f'/api/classroom-media/{stage_id}/media/') or not isinstance(alt, str) or not alt.strip():
            raise ValueError('image visual needs a lesson media src and a non-empty alt')
        return {'kind': 'image', 'src': src, 'alt': alt}
    if kind == 'picture':
        alt = value.get('alt')
        if not isinstance(alt, str) or not alt.strip():
            raise ValueError('picture alt must be non-empty')
        png = render_picture(value['picture'])
        name = png_name(png)
        Path(media_dir).mkdir(parents=True, exist_ok=True)
        (Path(media_dir) / name).write_bytes(png)
        return {'kind': 'image', 'src': f'/api/classroom-media/{stage_id}/media/{name}', 'alt': alt}
    raise ValueError('unsupported visual kind')


def upgrade_quiz(body, spec, *, stage_id, media_dir, audio_urls=None):
    """Return (copied body, new speech actions with id, text and questionId)."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', stage_id):
        raise ValueError('invalid stage_id')
    result = deepcopy(body)
    existing_ids = {a.get('id') for s in result['scenes'] for a in s.get('actions', [])}
    needed = []
    seen_scenes = set()
    for scene_spec in spec['scenes']:
        index = scene_spec['sceneIndex']
        if type(index) is not int or not 1 <= index <= len(result['scenes']) or index in seen_scenes:
            raise ValueError('invalid or duplicate sceneIndex')
        seen_scenes.add(index)
        scene = result['scenes'][index - 1]
        if scene.get('type') != 'quiz':
            raise ValueError('scene is not a quiz')
        questions = scene['content']['questions']
        by_id = {item['id']: item for item in scene_spec['questions']}
        if len(by_id) != len(scene_spec['questions']) or set(by_id) != {q['id'] for q in questions}:
            raise ValueError('spec must cover every question exactly once')
        actions = [a for a in scene.get('actions', []) if a.get('type') != 'speech']
        def add_speech(text, question_id):
            number = 1
            while f'quiz_speech_{number}' in existing_ids:
                number += 1
            action_id = f'quiz_speech_{number}'
            existing_ids.add(action_id)
            actions.append({'id': action_id, 'type': 'speech', 'text': text})
            needed.append({'id': action_id, 'text': text, 'questionId': question_id})

        intro = scene_spec.get('intro', [])
        if not isinstance(intro, list):
            raise ValueError('intro must be a list of teacher lines')
        for line in intro:
            if not isinstance(line, str) or not line.strip() or _READING.search(line):
                raise ValueError('intro line is empty or asks the child to read')
            add_speech(line, None)
        for question in questions:
            item = by_id[question['id']]
            text = _question_text(item['question'])
            if not text or _READING.search(text):
                raise ValueError('question text is empty or asks the child to read')
            if not isinstance(item.get('skill'), str) or not item['skill'].strip():
                raise ValueError('question skill must be non-empty')
            options = item['options']
            values = [o['value'] for o in question['options']]
            if len(set(values)) != len(values) or set(options) != set(values):
                raise ValueError('missing or extra option visual')
            question['question'] = text
            question['skill'] = item['skill']
            if 'answer' in item:
                if not (isinstance(item['answer'], list) and len(item['answer']) == 1 and item['answer'][0] in values):
                    raise ValueError('question answer must be one option value')
                question['answer'] = list(item['answer'])
            if 'analysis' in item:
                if not isinstance(item['analysis'], str) or not item['analysis'].strip():
                    raise ValueError('question analysis must be non-empty')
                question['analysis'] = item['analysis'].strip()
            if item.get('visual') is None:
                question.pop('visual', None)
            else:
                question['visual'] = _visual(item['visual'], stage_id, media_dir)
            question['optionVisuals'] = {}
            for option in question['options']:
                choice = options[option['value']]
                if not isinstance(choice, dict) or 'visual' not in choice:
                    raise ValueError('missing option visual')
                option['label'] = choice['label']
                question['optionVisuals'][option['value']] = _visual(choice['visual'], stage_id, media_dir)
            question.pop('questionAudioUrl', None)
            if audio_urls and question['id'] in audio_urls:
                question['questionAudioUrl'] = audio_urls[question['id']]
            add_speech(text, question['id'])
        scene['actions'] = actions
    return result, needed
