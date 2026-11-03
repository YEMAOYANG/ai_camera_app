"""Build a lesson folder into a classroom and its media.

The source has lesson.json, pages/<id>.html and pages/<id>.js, an optional
pages/<id>.css, and PNG images under assets/. Page HTML is the #play body;
its script uses the shared kit's K object. Voices are supplied separately.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

from courseware.kit import page, slides
from courseware.tools import glyph_picture, quiz_upgrade


class BuildError(Exception):
    pass


def _fail(code, detail):
    raise BuildError(code, str(detail))


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def _read(path, code, detail):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise BuildError(code, f'{detail}: {exc}') from exc


def _resolve_assets(value, urls, where):
    """Replace {'kind': 'asset', 'image': key, 'alt': ...} by the image visual of that lesson picture."""
    if isinstance(value, dict):
        if value.get('kind') == 'asset':
            if value.get('image') not in urls:
                _fail('image_missing', f"{where} {value.get('image')}")
            return {'kind': 'image', 'src': urls[value['image']], 'alt': value.get('alt')}
        return {k: _resolve_assets(v, urls, where) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_assets(v, urls, where) for v in value]
    return value


def prepare(lesson_dir, out_dir, *, stage_id, now_ms=None):
    source, out = Path(lesson_dir), Path(out_dir)
    lesson = _read(source / 'lesson.json', 'lesson_invalid', 'lesson.json')
    if not isinstance(lesson, dict) or lesson.get('schemaVersion') != 'mira.courseware.lesson.v1':
        _fail('lesson_invalid', 'schemaVersion')
    if set(lesson) - {'schemaVersion', 'title', 'description', 'grade', 'roster', 'images', 'scenes'}:
        _fail('lesson_invalid', 'unknown lesson fields')
    if not all(_string(lesson.get(k)) for k in ('title', 'description')) or type(lesson.get('grade')) is not int or lesson['grade'] not in range(1, 7):
        _fail('lesson_invalid', 'title, description or grade')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', stage_id or ''):
        _fail('lesson_invalid', 'stage_id')
    roster = lesson.get('roster')
    voices = _read(Path(__file__).with_name('voices.json'), 'roster_invalid', 'voices')
    if not isinstance(roster, dict) or not roster:
        _fail('roster_invalid', 'roster')
    teachers = []
    configs = []
    genders = {}
    for key, agent in roster.items():
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9-]+', key) or not isinstance(agent, dict):
            _fail('roster_invalid', key)
        role, gender = agent.get('role'), agent.get('gender')
        if role not in ('teacher', 'assistant', 'student') or gender not in voices or agent.get('voice') not in voices[gender] or not all(_string(agent.get(k)) for k in ('name', 'avatar', 'color', 'persona')):
            _fail('roster_invalid', key)
        if agent['name'] in genders:
            _fail('roster_invalid', key + ' name')
        genders[agent['name']] = gender
        if role == 'teacher':
            teachers.append(agent)
        configs.append({'id': 'gen-' + key, 'name': agent['name'], 'role': role, 'color': agent['color'], 'avatar': agent['avatar'], 'persona': agent['persona'], 'priority': {'teacher': 10, 'assistant': 7, 'student': 5}[role], 'voiceConfig': {'providerId': 'qwen-tts', 'modelId': 'qwen3-tts-flash', 'voiceId': agent['voice']}})
    if len(teachers) != 1:
        _fail('roster_invalid', 'teacher')
    scenes = lesson.get('scenes')
    images = lesson.get('images')
    if not isinstance(scenes, list) or not scenes or not isinstance(images, dict):
        _fail('lesson_invalid', 'scenes or images')
    media = out / 'media'
    media.mkdir(parents=True, exist_ok=True)
    urls, aspects = {}, {}
    for key, spec in images.items():
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9-]+', key) or not isinstance(spec, dict):
            _fail('lesson_invalid', f'images {key}')
        try:
            if set(spec) == {'file'} and isinstance(spec['file'], str):
                path = (source / spec['file']).resolve()
                if not path.is_relative_to((source / 'assets').resolve()) or path.suffix.lower() != '.png':
                    raise ValueError('invalid asset path')
                png = path.read_bytes()
            elif set(spec) == {'glyph'}:
                png = glyph_picture.render_picture(spec['glyph'])
            else:
                raise ValueError('expected file or glyph')
            if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
                raise ValueError('invalid PNG')
            width, height = struct.unpack('>II', png[16:24])
            if not width or not height:
                raise ValueError('invalid PNG dimensions')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise BuildError('image_missing', f'{key}: {exc}') from exc
        name = 'pic-' + hashlib.sha256(png).hexdigest() + '.png'
        (media / name).write_bytes(png)
        urls[key] = f'/api/classroom-media/{stage_id}/media/{name}'
        aspects[key] = width / height
    now = int(time.time() * 1000) if now_ms is None else now_ms
    body = {'stage': {'id': stage_id, 'name': lesson['title'], 'agentIds': [c['id'] for c in configs], 'createdAt': now, 'updatedAt': now, 'description': lesson['description'], 'generatedAgentConfigs': configs}, 'scenes': []}
    quiz_specs = []
    seen = set()
    for index, item in enumerate(scenes, 1):
        if not isinstance(item, dict):
            _fail('lesson_invalid', f'scene {index}')
        key, kind = item.get('key'), item.get('type')
        if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9-]+', key) or key in seen or kind not in ('slide', 'interactive', 'quiz') or not _string(item.get('title')):
            _fail('lesson_invalid', f'scene {index} key, type or title')
        seen.add(key)
        fields = {'key', 'type', 'title', 'script'} | {'slide': {'template', 'data'}, 'interactive': {'page', 'widgetType', 'startImage'}, 'quiz': {'intro', 'questions'}}[kind]
        if set(item) - fields:
            _fail('lesson_invalid', f'{key} unknown fields')
        script = item.get('script', [] if kind == 'quiz' else None)
        if not isinstance(script, list):
            _fail('lesson_invalid', f'{key} script')
        names, ids = {}, set()
        if kind == 'slide':
            try:
                rendered = slides.render(item.get('template'), item.get('data'), image_urls=urls, aspects=aspects)
            except slides.LayoutError as exc:
                if exc.args and exc.args[0] == 'image_missing':
                    _fail('image_missing', f'{key} {exc.args[1]}')
                raise BuildError('template_failed', f'{key} {exc.args}') from exc
            names = rendered['names']
            ids = {element['id'] for element in rendered['elements']}
            content = {'type': 'slide', 'canvas': slides.canvas(rendered['elements'], rendered['background'])}
        elif kind == 'interactive':
            page_id, widget = item.get('page'), item.get('widgetType')
            if not isinstance(page_id, str) or not re.fullmatch(r'[a-z0-9-]+', page_id) or not _string(widget):
                _fail('lesson_invalid', f'{key} page or widgetType')
            try:
                html = (source / 'pages' / (page_id + '.html')).read_text(encoding='utf-8')
                js = (source / 'pages' / (page_id + '.js')).read_text(encoding='utf-8')
                css_path = source / 'pages' / (page_id + '.css')
                css = css_path.read_text(encoding='utf-8') if css_path.exists() else ''
            except OSError as exc:
                raise BuildError('page_missing', f'{key} {page_id}: {exc}') from exc
            clash = page.defined_ids(html + js) & page.reserved_ids()
            if clash:
                _fail('id_reserved', f"{key} {page_id}: {', '.join(sorted(clash))}")
            html = page.page(item['title'], html, css, js).replace('__STAGE__', stage_id)
            if 'startImage' in item:
                image_key = item['startImage']
                if not isinstance(image_key, str) or image_key not in urls:
                    _fail('image_missing', f'{key} {image_key}')
                if 'K.ready({' not in html:
                    _fail('start_overlay_missing', f'{key} {page_id}')
                html = html.replace('K.ready({', "K.ready({img:'" + urls[image_key] + "',", 1)
            def replace_image(match):
                image_key = match.group(1)
                if image_key not in urls:
                    _fail('image_missing', f'{key} {image_key}')
                return urls[image_key]
            html = re.sub(r'__IMG:([^_]+)__', replace_image, html)
            content = {'url': '', 'html': html, 'type': 'interactive', 'widgetType': widget, 'widgetConfig': {'type': widget, 'description': item['title']}}
        else:
            questions = item.get('questions')
            if not isinstance(questions, list) or not questions or not isinstance(item.get('intro'), list):
                _fail('quiz_invalid', f'{key} questions or intro')
            questions = _resolve_assets(questions, urls, key)
            try:
                content = {'type': 'quiz', 'questions': [{'id': q['id'], 'type': 'single', 'answer': q['answer'], 'points': 10, 'options': [{'label': v['label'], 'value': k} for k, v in q['options'].items()], 'analysis': q['analysis'], 'question': q['question'], 'hasAnswer': True} for q in questions]}
            except (KeyError, TypeError, AttributeError) as exc:
                raise BuildError('quiz_invalid', f'{key} questions: {exc}') from exc
            quiz_specs.append({'sceneIndex': index, 'intro': item['intro'], 'questions': questions})
        actions = []
        for number, beat in enumerate(script, 1):
            if not isinstance(beat, dict):
                _fail('lesson_invalid', f'{key} script {number}')
            ops = set(beat) & {'say', 'spotlight', 'laser', 'highlight', 'reveal', 'annotate', 'setState', 'discuss'}
            if len(ops) != 1:
                _fail('lesson_invalid', f'{key} script {number}')
            op = next(iter(ops)); value = beat[op]
            if set(beat) - ({op, 'content'} if op in ('highlight', 'reveal', 'annotate', 'setState') else {op}):
                _fail('lesson_invalid', f'{key} script {number}')
            action = {'id': f'{key}-{number}'}
            if op == 'say' and _string(value):
                action.update(type='speech', text=value)
            elif op in ('spotlight', 'laser') and kind == 'slide' and _string(value):
                target = names.get(value, value)
                if target not in ids:
                    _fail('target_missing', f'{key} {op} {value}')
                action.update(type=op, elementId=target)
            elif op in ('highlight', 'reveal', 'annotate', 'setState') and kind == 'interactive' and ((op == 'setState' and isinstance(value, dict) and bool(value)) or (op != 'setState' and _string(value))):
                if op == 'annotate' and not _string(beat.get('content')):
                    _fail('lesson_invalid', f'{key} annotate content')
                action['type'] = {'highlight': 'widget_highlight', 'reveal': 'widget_reveal', 'annotate': 'widget_annotation', 'setState': 'widget_setState'}[op]
                action['state' if op == 'setState' else 'target'] = value
                if 'content' in beat:
                    if not isinstance(beat['content'], str):
                        _fail('lesson_invalid', f'{key} content')
                    action['content'] = beat['content']
            elif op == 'discuss' and isinstance(value, dict) and _string(value.get('topic')) and _string(value.get('prompt')):
                by = value.get('by')
                if by not in roster or roster[by]['role'] != 'student':
                    _fail('roster_invalid', f'{key} discuss by')
                action.update(type='discussion', topic=value['topic'], prompt=value['prompt'], agentId='gen-' + by)
            else:
                _fail('lesson_invalid', f'{key} script {number} {op}')
            actions.append(action)
        body['scenes'].append({'id': 'scene-' + key, 'type': kind, 'order': index, 'title': item['title'], 'actions': actions, 'content': content, 'stageId': stage_id, 'createdAt': now, 'outlineId': key, 'updatedAt': now})
    quiz_actions = {scene['id']: scene['actions'] for scene in body['scenes'] if scene['type'] == 'quiz'}
    try:
        body, needed = quiz_upgrade.upgrade_quiz(body, {'scenes': quiz_specs}, stage_id=stage_id, media_dir=media)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BuildError('quiz_invalid', f'quiz: {exc}') from exc
    for scene in body['scenes']:
        if scene['type'] == 'quiz':
            generated = [action for action in scene['actions'] if action['type'] == 'speech']
            scene['actions'] = quiz_actions[scene['id']] + generated
    question_audio = {}
    for line in needed:
        if line['questionId'] is not None:
            if line['questionId'] in question_audio:
                _fail('quiz_invalid', 'duplicate question id ' + str(line['questionId']))
            question_audio[line['questionId']] = line['id']
    lines = [{'id': a['id'], 'text': a['text'], 'voice': teachers[0]['voice']} for scene in body['scenes'] for a in scene['actions'] if a['type'] == 'speech']
    draft = {'body': body, 'lines': lines, 'roster': genders, 'grade': lesson['grade'], 'questionAudio': question_audio}
    _write(out / 'draft.json', draft); _write(out / 'lines.json', lines); _write(out / 'roster.json', genders)
    return draft


def finish(draft, out_dir, files):
    out = Path(out_dir); media = out / 'media'
    body = deepcopy(draft['body'])
    stage_id = body['stage']['id']
    actions = [a for scene in body['scenes'] for a in scene['actions'] if a['type'] == 'speech']
    missing = [a['id'] for a in actions if not isinstance(files.get(a['id']), str) or Path(files[a['id']]).name != files[a['id']] or not (media / files[a['id']]).is_file()]
    if missing:
        _fail('audio_missing', ', '.join(missing))
    urls = {}
    for action in actions:
        url = f"/api/classroom-media/{stage_id}/media/{files[action['id']]}"
        action['audioId'] = action['audioUrl'] = url
        urls[action['id']] = url
    for scene in body['scenes']:
        if scene['type'] == 'quiz':
            for question in scene['content']['questions']:
                question['questionAudioUrl'] = urls[draft['questionAudio'][question['id']]]
    from courseware.tools.check import MEDIA_URL, strings
    referenced = {match.group().split('/media/', 1)[1] for value in strings(body) for match in MEDIA_URL.finditer(value)}
    for path in media.iterdir():
        if path.is_file() and (path.match('pic-*.png') or path.match('tts-*.wav')) and path.name not in referenced:
            path.unlink()
    _write(out / 'body.json', body)
    return body


def build_lesson(lesson_dir, out_dir, *, stage_id, voice, now_ms=None):
    draft = prepare(lesson_dir, out_dir, stage_id=stage_id, now_ms=now_ms)
    return finish(draft, out_dir, voice(draft['lines'])['files'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare'); prep.add_argument('--lesson', required=True); prep.add_argument('--out', required=True); prep.add_argument('--stage-id', required=True); prep.add_argument('--now-ms', type=int)
    end = sub.add_parser('finish'); end.add_argument('--out', required=True); end.add_argument('--audio', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            prepare(args.lesson, args.out, stage_id=args.stage_id, now_ms=args.now_ms)
        else:
            draft = _read(Path(args.out) / 'draft.json', 'lesson_invalid', 'draft.json')
            audio = _read(Path(args.audio), 'audio_missing', 'audio.json')
            if not isinstance(audio, dict) or not isinstance(audio.get('files'), dict):
                _fail('audio_missing', 'files')
            finish(draft, args.out, audio['files'])
    except BuildError as exc:
        print(f'{exc.args[0]}: {exc.args[1]}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
