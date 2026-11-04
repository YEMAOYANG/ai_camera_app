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


# The spoken explanation a page must carry when a lesson is checked as a teaching lesson. The pilot lesson 整理和复习 averages
# 162 characters on a slide and 131 on an interactive page; its thinnest slide has 6 lines and 100 characters.
NARRATION_MINIMUM = {'slide': (6, 100), 'interactive': (5, 90)}
# The speech voice cannot be trusted with pinyin letters: a spoken line names the character and its tone instead.
TONE_MARKED = re.compile('[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]')
# The numbered texts of a slide template (points, items, steps): the teacher lights each one while speaking about it.
NUMBERED_TEXT = re.compile(r'text_(?:point|item|step)-\d+$')
TRADITIONAL = frozenset(Path(__file__).with_name('traditional.txt').read_text(encoding='utf-8').strip())


def traditional(text):
    """Characters of text that exist only in Traditional Chinese; lessons are written in Simplified Chinese."""
    return ''.join(sorted({ch for ch in text if ch in TRADITIONAL}))


def body_hash(body):
    data = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def teaching_goal_count(notes):
    """The goals covered by verify.py: objectives plus the key and difficult points."""
    if not isinstance(notes, dict):
        return 0
    count = sum(isinstance(goal, str) and bool(goal.strip()) for goal in notes.get('objectives') or [])
    return count + sum(isinstance(notes.get(key), str) and bool(notes[key].strip()) for key in ('keyPoint', 'difficultPoint'))


def play_issues(receipt):
    """Turn a current random-play receipt into blocking G6 issues."""
    if not isinstance(receipt, dict) or receipt.get('schemaVersion') != 'mira.courseware.autoplay-receipt.v1' \
            or not isinstance(receipt.get('pages'), list):
        return [dict(gate='G6', code='play_receipt_invalid', scene=None,
                     detail='the random-play receipt has an invalid shape', severity='error')]
    found = []
    for page in receipt['pages']:
        if not isinstance(page, dict) or type(page.get('scene')) is not int:
            found.append(dict(gate='G6', code='play_receipt_invalid', scene=None,
                              detail='a random-play page result has an invalid shape', severity='error'))
            continue
        scene, stuck = page['scene'], page.get('stuck')
        errors = page.get('errors') if isinstance(page.get('errors'), list) else []
        if errors:
            found.append(dict(gate='G6', code='page_error_in_play', scene=scene,
                              detail='; '.join(map(str, errors))[:300], severity='error'))
        if stuck and str(stuck).startswith(('no play-again', 'finish still showing')):
            found.append(dict(gate='G6', code='play_again_broken', scene=scene,
                              detail=str(stuck), severity='error'))
        elif stuck or page.get('finished') is not True:
            found.append(dict(gate='G6', code='play_unfinished', scene=scene,
                              detail=str(stuck or 'never finished'), severity='error'))
    if receipt.get('ok') is not True and not found:
        found.append(dict(gate='G6', code='play_receipt_failed', scene=None,
                          detail='the random-play receipt is not successful', severity='error'))
    return found


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


def check_classroom(body, media_dir=None, *, notes=None, roster=None, receipt=None, play_receipt=None,
                    verification=None, grade=None, teaching=False, require_play=False):
    """All gates over a built classroom; teaching=True also requires enough spoken explanation on every slide and page,
    no pinyin letters in a spoken line and every numbered text of a slide lit in turn."""
    issues = []

    def add(gate, code, scene, detail, severity='error'):
        issues.append(dict(gate=gate, code=code, scene=scene, detail=detail, severity=severity))

    if notes is not None:
        resources = notes.get('resources', {})
        for name in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise'):
            item = resources.get(name, {})
            if item.get('status') == 'not_provided':
                # The official listing of this class hour has no such resource; the evidence names the saved listing.
                if not isinstance(item.get('evidence'), str) or not item['evidence'].strip():
                    add('G0', 'notes_incomplete', None, name + ' not_provided requires evidence')
            elif not isinstance(item.get('findings'), list) or not item['findings'] or not isinstance(item.get('pageRefs'), list) or not item['pageRefs']:
                add('G0', 'notes_incomplete', None, name + ' requires findings and pageRefs')
        bad = traditional(json.dumps(notes, ensure_ascii=False))
        if bad:
            add('G0', 'traditional_chinese', None, 'official notes: ' + bad)
        facts = notes.get('factChecks', [])
        if not isinstance(facts, list):
            add('G0', 'fact_check_incomplete', None, 'factChecks must be a list')
        else:
            for number, fact in enumerate(facts, 1):
                claims = fact.get('claims') if isinstance(fact, dict) else None
                sources = fact.get('sources') if isinstance(fact, dict) else None
                valid_sources = isinstance(sources, list) and len(sources) >= 2 and all(
                    isinstance(source, dict) and isinstance(source.get('resource'), str)
                    and source['resource'] in resources and isinstance(source.get('pageRefs'), list)
                    and bool(source['pageRefs']) and isinstance(source.get('finding'), str)
                    and bool(source['finding'].strip()) for source in sources or [])
                if not isinstance(claims, list) or not claims or not all(
                        isinstance(claim, str) and claim.strip() for claim in claims) or not valid_sources:
                    add('G0', 'fact_check_incomplete', None,
                        'factChecks[%d] needs claims and two cited official resources' % number)

    scenes = body.get('scenes', [])
    speech_count = question_count = 0
    answers = []
    referenced = set()
    for index, scene in enumerate(scenes, 1):
        actions = scene.get('actions', [])
        speeches = [a for a in actions if a.get('type') == 'speech']
        speech_count += len(speeches)
        if teaching and scene.get('type') in NARRATION_MINIMUM:
            lines, characters = NARRATION_MINIMUM[scene['type']]
            spoken = sum(len(a.get('text', '')) for a in speeches)
            if len(speeches) < lines or spoken < characters:
                add('G3', 'narration_thin', index, '%d lines and %d characters of speech; a %s needs at least %d lines and %d characters that explain the knowledge' % (
                    len(speeches), spoken, scene['type'], lines, characters))
        if teaching:
            for action in speeches:
                if TONE_MARKED.search(action.get('text', '')):
                    add('G3', 'speech_pinyin', index, str(action.get('id', 'speech')) + ': say the character and its tone name, not pinyin letters')
            if scene.get('type') == 'slide':
                numbered = [e['id'] for e in scene.get('content', {}).get('canvas', {}).get('elements', []) if NUMBERED_TEXT.match(str(e.get('id', '')))]
                lit = list(dict.fromkeys(a.get('elementId') for a in actions if a.get('type') in ('spotlight', 'laser') and a.get('elementId') in numbered))
                if lit != [name for name in numbered if name in lit] or len(lit) < len(numbered):
                    add('G3', 'spotlight_gap', index, 'lit in the order %s; the teacher must light every one of %s in that order' % (lit, numbered))
        for action in speeches:
            if not action.get('audioUrl'):
                add('G1', 'speech_audio_missing', index, str(action.get('id', 'speech')))
            text = action.get('text', '')
            if len(text) > 25:
                add('G3', 'speech_too_long', index, str(action.get('id', 'speech')) + ': %d characters' % len(text), 'error' if len(text) > 40 else 'warn')
            if any(phrase in text for phrase in ('自己读题', '请你读')):
                add('G4', 'self_read_instruction', index, str(action.get('id', 'speech')))

        for action in actions:
            if action.get('type') == 'discussion':
                # A live discussion calls a paid model (paid classroom interactions are off) and the student runtime
                # seats only its own roster. Write the question as a pre-recorded teacher line instead.
                add('G3', 'discussion_not_allowed', index, str(action.get('id', 'discussion')) + ': write it as a teacher line such as 小满问：…')

        texts = [(str(a.get('id', 'speech')), a.get('text', '')) for a in speeches]
        if scene.get('type') == 'slide':
            texts += [(str(e.get('id', '')), re.sub(r'<[^>]*>', '', e.get('content', ''))) for e in scene.get('content', {}).get('canvas', {}).get('elements', []) if e.get('type') == 'text']
        if scene.get('type') == 'quiz':
            for q in scene.get('content', {}).get('questions', []):
                texts.append((str(q.get('id', '')), ' '.join([q.get('question', ''), q.get('analysis', '')] + [str(o.get('label', '')) for o in q.get('options', [])])))
        for name, text in texts:
            bad = traditional(text)
            if bad:
                add('G3', 'traditional_chinese', index, name + ': ' + bad)

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
                else:
                    answers.append(answer[0])
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

    if len(answers) >= 2:
        # A child who always taps the same place must not pass by luck.
        value, count = max(((v, answers.count(v)) for v in set(answers)), key=lambda pair: (pair[1], str(pair[0])))
        if count * 2 > len(answers):
            add('G4', 'answer_position_skewed', None, '%s is the answer to %d of %d questions' % (value, count, len(answers)))

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
    if play_receipt is None:
        if require_play:
            add('G6', 'play_receipt_missing', None, 'the random-play check has not run')
    elif not isinstance(play_receipt, dict):
        issues += play_issues(play_receipt)
    elif play_receipt.get('bodySha256') != digest:
        add('G6', 'play_receipt_stale', None, 'the random-play receipt belongs to another build')
    else:
        expected = [index for index, scene in enumerate(scenes, 1) if scene.get('type') == 'interactive']
        actual = [page.get('scene') for page in play_receipt.get('pages', []) if isinstance(page, dict)]
        if actual != expected:
            add('G6', 'play_receipt_incomplete', None, 'played scenes %s; expected %s' % (actual, expected))
        issues += play_issues(play_receipt)
    if verification is not None:
        if verification.get('bodySha256') != digest:
            add('G7', 'verification_receipt_stale', None, 'Body hash does not match')
        if verification.get('disagreements') != []:
            add('G7', 'verification_disagreements', None, 'Disagreements must be empty')
        if not isinstance(verification.get('speechChecked'), int) or verification['speechChecked'] < speech_count or not isinstance(verification.get('questionsChecked'), int) or verification['questionsChecked'] < question_count:
            add('G7', 'verification_incomplete', None, 'Counts must cover all speech and questions')
        if notes is not None and verification.get('notesSha256') != body_hash(notes):
            add('G7', 'verification_notes_stale', None, 'Official-notes hash does not match')
        goals = teaching_goal_count(notes)
        if goals and (type(verification.get('goalsChecked')) is not int or verification['goalsChecked'] < goals):
            add('G7', 'verification_teaching_incomplete', None, 'Checked %s of %s teaching goals' % (
                verification.get('goalsChecked'), goals))
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body', required=True)
    parser.add_argument('--media-dir')
    for name in ('notes', 'roster', 'receipt', 'verification'):
        parser.add_argument('--' + name)
    parser.add_argument('--play-receipt')
    parser.add_argument('--grade', type=int)
    parser.add_argument('--require-all', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    def load(path):
        return json.loads(Path(path).read_text(encoding='utf-8')) if path else None

    try:
        issues = check_classroom(load(args.body), args.media_dir, notes=load(args.notes), roster=load(args.roster),
                                 receipt=load(args.receipt), play_receipt=load(args.play_receipt),
                                 verification=load(args.verification), grade=args.grade,
                                 require_play=args.require_all)
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
