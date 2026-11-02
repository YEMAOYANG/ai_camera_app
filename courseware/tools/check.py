"""Static courseware release checks; browser and editorial audits use receipts."""
import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path
from urllib.parse import unquote


MEDIA_URL = re.compile(r'/api/classroom-media/[^/\s"\'<>]+/media/[^\s"\'<>+]+')
HASH = re.compile(r'([0-9a-fA-F]{64})(?:\.[^./]+)?$')
EMOJI = re.compile('[\U0001f000-\U0001faff\u2600-\u27bf\ufe0f\u20e3]')
OPERATIONS = {'widget_highlight', 'widget_setState', 'widget_annotation', 'widget_reveal'}


def body_hash(body):
    data = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def text_box(element):
    content = element.get('content', '')
    sizes = [float(x) for x in re.findall(r'font-size\s*:\s*([\d.]+)px', content, re.I)]
    size = max(sizes, default=16)
    paragraphs = re.split(r'</p\s*>|<br\s*/?>', content, flags=re.I)
    lines = 0
    width = max(float(element.get('width', 0)) - 20, 1)
    for part in paragraphs:
        text = html.unescape(re.sub(r'<[^>]*>', '', part))
        if text.strip():
            units = sum(1 if ord(ch) > 127 else 0.55 for ch in text)
            lines += max(1, math.ceil(units * size / width))
    height = 20 + max(lines, 1) * size * 1.5 + max(0, lines - 1) * 5
    left, top = float(element.get('left', 0)), float(element.get('top', 0))
    return left, top, left + float(element.get('width', 0)), top + height


def check_classroom(body, media_dir=None, *, notes=None, roster=None, receipt=None, verification=None, grade=None):
    issues = []

    def add(gate, code, scene, detail, severity='error'):
        issues.append(dict(gate=gate, code=code, scene=scene, detail=detail, severity=severity))

    if notes is not None:
        resources = notes.get('resources', {})
        for name in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise'):
            item = resources.get(name, {})
            if not isinstance(item.get('findings'), list) or not item['findings'] or not isinstance(item.get('pageRefs'), list) or not item['pageRefs']:
                add('G0', 'notes_incomplete', None, name + ' requires findings and pageRefs')

    scenes = body.get('scenes', [])
    speech_count = question_count = 0
    referenced = set()
    for index, scene in enumerate(scenes, 1):
        actions = scene.get('actions', [])
        speeches = [a for a in actions if a.get('type') == 'speech']
        speech_count += len(speeches)
        for action in speeches:
            if not action.get('audioUrl'):
                add('G1', 'speech_audio_missing', index, str(action.get('id', 'speech')))
            text = action.get('text', '')
            if len(text) > 25:
                add('G3', 'speech_too_long', index, str(action.get('id', 'speech')) + ': %d characters' % len(text), 'error' if len(text) > 40 else 'warn')
            if any(phrase in text for phrase in ('自己读题', '请你读')):
                add('G4', 'self_read_instruction', index, str(action.get('id', 'speech')))

        if scene.get('type') == 'slide':
            elements = scene.get('content', {}).get('canvas', {}).get('elements', [])
            boxes = [(e.get('id', ''), text_box(e)) for e in elements if e.get('type') == 'text']
            for name, box in boxes:
                if box[0] < -1 or box[1] < -1 or box[2] > 1001 or box[3] > 563.5:
                    add('G2', 'slide_text_outside', index, str(name))
            for i, (name, a) in enumerate(boxes):
                for other, b in boxes[i + 1:]:
                    if min(a[2] - 10, b[2] - 10) - max(a[0] + 10, b[0] + 10) > 1 and min(a[3] - 10, b[3] - 10) - max(a[1] + 10, b[1] + 10) > 1:
                        add('G2', 'slide_text_overlap', index, '%s / %s' % (name, other))

        if scene.get('type') == 'interactive':
            page = scene.get('content', {}).get('html', '')
            if len([a for a in actions if a.get('type') in OPERATIONS]) < 3:
                add('G3', 'interactive_operations_missing', index, 'At least three page operations required')
            if len(speeches) < 3:
                add('G3', 'interactive_speech_missing', index, 'At least three speech actions required')
            if not re.search(r'#cv\s*\{[^}]*\bwidth\s*:\s*1280px\s*;[^}]*\bheight\s*:\s*720px\s*[;}]', page, re.I):
                add('G3', 'interactive_stage_missing', index, 'Fixed 1280 x 720 #cv stage required')
            for action in actions:
                kind = action.get('type')
                if kind in {'widget_highlight', 'widget_annotation', 'widget_reveal'}:
                    target = action.get('target', '')
                    ident = target[1:] if target.startswith('#') else ''
                    literal = bool(ident and re.search(r'(["\'])' + re.escape(ident) + r'\1', page))
                    dynamic = re.fullmatch(r'(.+?)-\d+(?:-\d+)*', ident)
                    if not literal and not (dynamic and dynamic.group(1) + '-' in page):
                        add('G3', 'interactive_target_missing', index, str(target))
                if kind == 'widget_setState':
                    keys = action.get('state', {})
                    missing = [key for key in keys if not re.search(r'(?<![\w$])' + re.escape(key) + r'(?![\w$])', page)]
                    if not keys:
                        add('G3', 'interactive_state_missing', index, 'No state keys')
                    for key in missing:
                        add('G3', 'interactive_state_missing', index, key, 'error' if len(missing) == len(keys) else 'warn')

        if scene.get('type') == 'quiz':
            for question in scene.get('content', {}).get('questions', []):
                question_count += 1
                name = str(question.get('id', question_count))
                options = question.get('options', [])
                values = [o.get('value') for o in options]
                if not 2 <= len(values) <= 6 or any(v is None for v in values) or len(set(map(str, values))) != len(values):
                    add('G4', 'quiz_options_invalid', index, name)
                answer = question.get('answer')
                if not isinstance(answer, list) or len(answer) != 1 or answer[0] not in values:
                    add('G4', 'quiz_answer_invalid', index, name)
                for field in ('analysis', 'skill', 'questionAudioUrl'):
                    if not isinstance(question.get(field), str) or not question[field].strip():
                        add('G4', 'quiz_' + field + '_missing', index, name)
                text = question.get('question', '')
                if any(phrase in text for phrase in ('自己读题', '请你读')):
                    add('G4', 'self_read_instruction', index, name)
                if grade in (1, 2):
                    visuals = question.get('optionVisuals')
                    if not isinstance(visuals, dict) or set(visuals) != set(map(str, values)) or any(not isinstance(v, dict) or v.get('kind') not in ('image', 'quantity', 'people') for v in visuals.values()):
                        add('G4', 'quiz_visuals_invalid', index, name)
                    if EMOJI.search(text) or any(EMOJI.search(str(o.get('label', ''))) for o in options):
                        add('G4', 'quiz_emoji', index, name)

    if media_dir is not None:
        directory = Path(media_dir)
        for value in strings(body):
            for match in MEDIA_URL.finditer(value):
                filename = unquote(match.group().split('/media/', 1)[1].split('?', 1)[0].split('#', 1)[0])
                if not filename or '/' in filename or filename in ('.', '..'):
                    continue
                referenced.add(filename)
        for filename in sorted(referenced):
            path = directory / filename
            if not path.is_file():
                add('G1', 'media_missing', None, filename)
            else:
                match = HASH.search(filename)
                if match and hashlib.sha256(path.read_bytes()).hexdigest() != match.group(1).lower():
                    add('G1', 'media_hash_mismatch', None, filename)
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.is_file() and path.name not in referenced:
                    add('G1', 'media_unreferenced', None, path.name, 'warn')
        else:
            add('G1', 'media_directory_missing', None, str(directory))

    # This checks configuration only, not the recorded audio.
    voices = json.loads(Path(__file__).with_name('voices.json').read_text(encoding='utf-8'))
    for agent in body.get('stage', {}).get('generatedAgentConfigs', []):
        name = agent.get('name', '')
        voice = agent.get('voiceConfig', {}).get('voiceId')
        if not voice:
            add('G5', 'voice_missing', None, name)
        if roster is not None:
            if name not in roster:
                add('G5', 'roster_agent_missing', None, name)
            elif voice and voice not in voices.get(roster[name], []):
                add('G5', 'voice_gender_mismatch', None, name + ': ' + str(voice))

    digest = body_hash(body)
    if receipt is not None:
        if receipt.get('bodySha256') != digest or receipt.get('ok') is not True:
            add('G6', 'audit_receipt_stale', None, 'Body hash or audit result does not match')
        viewports = receipt.get('viewports', [])
        if not all(v in viewports for v in ('1280x720', '1000x563', '640x360')):
            add('G6', 'audit_receipt_missing_viewport', None, 'Required viewports: 1280x720, 1000x563, 640x360')
    if verification is not None:
        if verification.get('bodySha256') != digest:
            add('G7', 'verification_receipt_stale', None, 'Body hash does not match')
        if verification.get('disagreements') != []:
            add('G7', 'verification_disagreements', None, 'Disagreements must be empty')
        if not isinstance(verification.get('speechChecked'), int) or verification['speechChecked'] < speech_count or not isinstance(verification.get('questionsChecked'), int) or verification['questionsChecked'] < question_count:
            add('G7', 'verification_incomplete', None, 'Counts must cover all speech and questions')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body', required=True)
    parser.add_argument('--media-dir')
    for name in ('notes', 'roster', 'receipt', 'verification'):
        parser.add_argument('--' + name)
    parser.add_argument('--grade', type=int)
    parser.add_argument('--require-all', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    def load(path):
        return json.loads(Path(path).read_text(encoding='utf-8')) if path else None

    try:
        issues = check_classroom(load(args.body), args.media_dir, notes=load(args.notes), roster=load(args.roster), receipt=load(args.receipt), verification=load(args.verification), grade=args.grade)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.require_all:
        for gate, name in (('G0', 'notes'), ('G6', 'receipt'), ('G7', 'verification')):
            if getattr(args, name) is None:
                issues.append(dict(gate=gate, code=name + '_missing', scene=None, detail=name + ' is required', severity='error'))
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print('{gate} {severity} {code} scene={scene}: {detail}'.format(**issue))
    return int(any(issue['severity'] == 'error' for issue in issues))


if __name__ == '__main__':
    raise SystemExit(main())
