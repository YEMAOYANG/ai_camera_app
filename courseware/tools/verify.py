"""Independently verify lesson speech and questions against official notes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

from courseware.tools import game_audio
from courseware.tools.check import body_hash, valid_objectives


VERIFIER_MODEL = 'gpt-6.1-terra'
VERIFIER_EFFORT = 'low'
PROMPT = Path(__file__).parent / 'prompts' / 'verify.v1.md'
ANALYSIS_PROMPT = Path(__file__).parent / 'prompts' / 'verify_analysis.v1.md'
TEACHING_PROMPT = Path(__file__).parent / 'prompts' / 'verify_teaching.v1.md'
EVIDENCE_SCHEMA = 'mira.courseware.verification-evidence.v1'
SPEECH_VERDICT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'id': {'type': 'string'}, 'ok': {'type': 'boolean'},
                   'issue': {'type': ['string', 'null']}},
    'required': ['id', 'ok', 'issue'],
}
QUESTION_SOLVE_VERDICT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'id': {'type': 'string'}, 'solved': {'type': 'string'},
                   'skillMatchesObjectives': {'type': 'boolean'},
                   'picturesMatch': {'type': 'boolean'},
                   'issue': {'type': ['string', 'null']}},
    'required': ['id', 'solved', 'skillMatchesObjectives', 'picturesMatch', 'issue'],
}

TEACHING_VERDICT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'id': {'type': 'string'}, 'verdict': {'type': 'string'}, 'taughtAt': {'type': 'string'},
                   'issue': {'type': ['string', 'null']}},
    'required': ['id', 'verdict', 'taughtAt', 'issue'],
}

QUESTION_ANALYSIS_VERDICT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'id': {'type': 'string'}, 'analysisOk': {'type': 'boolean'},
                   'issue': {'type': ['string', 'null']}},
    'required': ['id', 'analysisOk', 'issue'],
}


def _items(body):
    speeches, solves, analyses = [], [], []
    for number, scene in enumerate(body.get('scenes', []), 1):
        for action in scene.get('actions', []):
            if action.get('type') == 'speech':
                speeches.append({'id': action['id'], 'text': action['text'], 'scene': number})
        if scene.get('type') == 'quiz':
            for question in scene.get('content', {}).get('questions', []):
                options = [{key: option[key] for key in ('label', 'value')}
                           for option in question['options']]
                answer = question['answer']
                if not isinstance(answer, list) or len(answer) != 1 or answer[0] not in [o['value'] for o in options]:
                    raise ValueError('Invalid stored answer: ' + question['id'])
                visuals = []
                if question.get('visual') is not None:
                    visuals.append(('question', question['visual']))
                for option in options:
                    visual = question.get('optionVisuals', {}).get(option['value'])
                    if visual is not None:
                        visuals.append(('option ' + option['value'], visual))
                solves.append({'id': question['id'], 'question': question['question'],
                               'options': options, 'skill': question['skill'], 'visuals': visuals})
                analyses.append({'id': question['id'], 'question': question['question'],
                                 'options': options, 'answer': answer[0], 'analysis': question['analysis'],
                                 'visuals': visuals})
    for items in (speeches, solves):
        ids = [item['id'] for item in items]
        if any(not isinstance(ident, str) or not ident for ident in ids) or len(ids) != len(set(ids)):
            raise ValueError('Item ids must be nonempty and unique within each kind')
    return speeches, solves, analyses


def _teaching_items(notes):
    """The learning goals the narration must teach: the notes' objectives, key point and difficult point."""
    objectives = notes.get('objectives') if isinstance(notes, dict) else None
    if not valid_objectives(objectives):
        raise ValueError('objectives_invalid (official notes must have a nonempty list of nonblank objectives)')
    items = [{'id': 'goal-%d' % number, 'goal': goal, 'kind': 'objective'}
             for number, goal in enumerate(objectives, 1)]
    for key, kind in (('keyPoint', 'key point'), ('difficultPoint', 'difficult point')):
        if isinstance(notes.get(key), str) and notes[key].strip():
            items.append({'id': key, 'goal': notes[key], 'kind': kind})
    return items


def _narration(body):
    return [{'scene': number, 'type': scene.get('type'), 'title': scene.get('title'),
             'lines': [a['text'] for a in scene.get('actions', []) if a.get('type') == 'speech']}
            for number, scene in enumerate(body.get('scenes', []), 1)]


def _picture_batch(items, media, *, check_files, strict_media=False):
    batch, images = [], []
    for item in items:
        pictures = []
        for purpose, visual in item['visuals']:
            if visual.get('kind') == 'image':
                src = visual.get('src', '')
                match = re.fullmatch(r'/api/classroom-media/[^/]+/media/([^/]+)', src)
                if not match or match.group(1) in ('.', '..'):
                    raise ValueError('Invalid picture source: ' + str(src))
                if media is None:
                    raise ValueError('Media directory required for picture: ' + match.group(1))
                local = Path(media) / match.group(1)
                if strict_media and (local.is_symlink() or local.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp')):
                    raise ValueError('Invalid local verifier picture: ' + local.name)
                path = local.resolve()
                if check_files and not path.is_file():
                    raise ValueError('Picture file missing: ' + str(path))
                images.append(str(path))
                pictures.append({'for': purpose, 'attachment': len(images)})
            elif visual.get('kind') == 'quantity':
                pictures.append({'for': purpose, 'count': visual['count']})
            else:
                raise ValueError('Unsupported picture kind: ' + str(visual.get('kind')))
        batch.append({key: value for key, value in item.items() if key != 'visuals'} | {'pictures': pictures})
    return batch, images


def _request(kind, batch, notes, *, images=(), narration=None):
    template = {
        'question_analysis': ANALYSIS_PROMPT, 'teaching': TEACHING_PROMPT,
    }.get(kind, PROMPT).read_text(encoding='utf-8')
    prompt = template.replace('$NOTES', json.dumps(notes, ensure_ascii=False, sort_keys=True))
    if kind == 'teaching':
        prompt = prompt.replace('$NARRATION', json.dumps(narration, ensure_ascii=False))
    prompt = prompt.replace('$KIND', kind).replace('$ITEMS', json.dumps(batch, ensure_ascii=False, sort_keys=True))
    return {'kind': kind, 'items': batch, 'prompt': prompt, 'images': list(images)}


def build_requests(body, notes, *, batch_size=40, media=None, teaching=False, check_files=True, strict_media=False):
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('batch_size must be a positive integer')
    teaching_items = _teaching_items(notes) if teaching else []
    requests = []
    for kind, items in zip(('speech', 'question_solve', 'question_analysis'), _items(body)):
        size = min(batch_size, 4) if kind != 'speech' else batch_size
        for start in range(0, len(items), size):
            batch = items[start:start + size]
            images = []
            if kind != 'speech':
                batch, images = _picture_batch(batch, media, check_files=check_files, strict_media=strict_media)
            requests.append(_request(kind, batch, notes, images=images))
    if teaching_items:
        requests.append(_request('teaching', teaching_items, notes, narration=_narration(body)))
    return requests


def _schema(kind):
    item_schema = {'speech': SPEECH_VERDICT_SCHEMA, 'question_solve': QUESTION_SOLVE_VERDICT_SCHEMA,
                   'question_analysis': QUESTION_ANALYSIS_VERDICT_SCHEMA, 'teaching': TEACHING_VERDICT_SCHEMA}[kind]
    return {'type': 'object', 'additionalProperties': False,
            'properties': {'verdicts': {'type': 'array', 'items': item_schema}},
            'required': ['verdicts']}


def _validate(request, result):
    if not isinstance(result, dict) or set(result) != {'verdicts'} or not isinstance(result['verdicts'], list):
        raise ValueError('Expected an object containing a verdicts array')
    items = {item['id']: item for item in request['items']}
    seen = set()
    schema = _schema(request['kind'])['properties']['verdicts']['items']
    for verdict in result['verdicts']:
        if not isinstance(verdict, dict) or set(verdict) != set(schema['required']):
            raise ValueError('Malformed verdict fields')
        for key, spec in schema['properties'].items():
            value, expected = verdict[key], spec['type']
            if expected == 'string' and not isinstance(value, str):
                raise ValueError('Invalid verdict field: ' + key)
            if expected == 'boolean' and type(value) is not bool:
                raise ValueError('Invalid verdict field: ' + key)
            if expected == ['string', 'null'] and value is not None and not isinstance(value, str):
                raise ValueError('Invalid verdict field: ' + key)
        ident = verdict['id']
        if ident not in items or ident in seen:
            raise ValueError('Extra or duplicate verdict id: ' + ident)
        if request['kind'] == 'question_solve':
            if verdict['solved'] not in [option['value'] for option in items[ident]['options']] + ['unknown']:
                raise ValueError('Solved answer is not an option: ' + ident)
            if (verdict['solved'] == 'unknown' or not verdict['picturesMatch']) and not (verdict['issue'] or '').strip():
                raise ValueError('An issue is required for an unsolved question or picture mismatch: ' + ident)
        if request['kind'] == 'teaching':
            if verdict['verdict'] not in ('taught', 'weak', 'missing'):
                raise ValueError('Teaching verdict must be taught, weak or missing: ' + ident)
            if verdict['verdict'] != 'taught' and not (verdict['issue'] or '').strip():
                raise ValueError('An issue is required when a goal is not fully taught: ' + ident)
        seen.add(ident)
    if seen != set(items):
        raise ValueError('Missing verdict ids: ' + ', '.join(sorted(set(items) - seen)))
    return result['verdicts']


def _check_review_disk_space(directory=None):
    setting = 'MIRA_COURSEWARE_MIN_FREE_BYTES'
    configured = os.environ.get(setting)
    if configured is None:
        return
    try:
        floor = int(configured)
    except ValueError:
        floor = None
    minimum = 2 * 1024**3
    if floor is None or floor < minimum:
        raise ValueError(f'{setting} must be an integer of at least {minimum} bytes')
    for path in (Path.cwd(), directory if directory is not None else tempfile.gettempdir()):
        available = shutil.disk_usage(path).free
        if available < floor:
            raise RuntimeError(f'Independent review disk space at {path} has {available} bytes available, '
                               f'requires at least {floor} bytes')


def default_runner(prompt, schema, model, effort, images=(), *, attempts=2):
    if attempts not in (1, 2):
        raise ValueError('Verification attempts must be 1 or 2')
    binary = os.environ.get('MIRA_CODEX_BIN', '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
    _check_review_disk_space()
    with tempfile.TemporaryDirectory() as directory:
        _check_review_disk_space(directory)
        schema_path = Path(directory) / 'schema.json'
        output_path = Path(directory) / 'output.json'
        schema_path.write_text(json.dumps(schema), encoding='utf-8')
        command = [binary, 'exec', '-m', model, '-c', 'model_reasoning_effort=' + effort,
                   '-s', 'read-only', '--skip-git-repo-check', '--ephemeral']
        for image in images:
            if not Path(image).is_file():
                raise ValueError('Picture file missing: ' + str(image))
            command.extend(['--image', str(Path(image).resolve())])
        command.extend(['--output-schema', str(schema_path), '-o', str(output_path), '-'])
        for attempt in range(attempts):
            _check_review_disk_space(directory)
            stderr = ''
            try:
                output_path.unlink(missing_ok=True)
                result = subprocess.run(command, input=prompt, text=True, cwd=directory, check=True, capture_output=True)
                stderr = result.stderr or ''
                return json.loads(output_path.read_text(encoding='utf-8'))
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                if attempt == attempts - 1:
                    stderr = getattr(exc, 'stderr', None) or stderr
                    detail = ': ' + stderr[-300:] if stderr else ''
                    count = 'two attempts' if attempts == 2 else 'one attempt'
                    raise RuntimeError(f'Codex verification failed after {count}: ' + str(exc) + detail) from exc


def run_requests(requests, runner=default_runner, *, model=VERIFIER_MODEL, effort=VERIFIER_EFFORT, jobs=1):
    if type(jobs) is not int or jobs not in (1, 2):
        raise ValueError('Verification jobs must be 1 or 2')

    def verify_one(request):
        result = runner(request['prompt'], _schema(request['kind']), model, effort, request.get('images', ()))
        return _validate(request, result)

    if jobs == 1:
        return [verdict for request in requests for verdict in verify_one(request)]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return [verdict for batch in pool.map(verify_one, requests) for verdict in batch]


def build_receipt(body, notes, requests, verdicts, stored_answers, *, model, effort, ran_at):
    speeches, questions, analyses = _items(body)
    goals = _teaching_items(notes) if any(request['kind'] == 'teaching' for request in requests) else []
    expected = {'speech': speeches, 'question_solve': questions, 'question_analysis': analyses, 'teaching': goals}
    offsets = dict.fromkeys(expected, 0)
    for request in requests:
        kind = request['kind']
        count = len(request['items'])
        if not count or (kind in ('question_solve', 'question_analysis') and count > 4):
            raise ValueError('Invalid request batch size')
        batch = expected[kind][offsets[kind]:offsets[kind] + count]
        images = request.get('images', [])
        if kind in ('question_solve', 'question_analysis'):
            media = Path(images[0]).parent if images else None
            batch, expected_images = _picture_batch(batch, media, check_files=False)
            if images != expected_images:
                raise ValueError('Request images do not match the body')
        elif images:
            raise ValueError('Unexpected images in request')
        if batch != request['items']:
            raise ValueError('Requests do not cover the body exactly')
        offsets[kind] += count
    if any(offsets[kind] != len(items) for kind, items in expected.items()):
        raise ValueError('Requests do not cover the body exactly')
    if len(verdicts) != len(speeches) + len(questions) + len(analyses) + len(goals):
        raise ValueError('Verdict count does not cover the body')
    body_answers = {q['id']: q['answer'] for scene in body.get('scenes', []) if scene.get('type') == 'quiz'
                    for q in scene.get('content', {}).get('questions', [])}
    if stored_answers != body_answers:
        raise ValueError('Stored answers do not match the body')
    disagreements = []
    offset = 0
    for request in requests:
        count = len(request['items'])
        batch = _validate(request, {'verdicts': verdicts[offset:offset + count]})
        offset += count
        for verdict in batch:
            ident, issue = verdict['id'], verdict['issue']
            if request['kind'] == 'speech':
                if not verdict['ok']:
                    disagreements.append({'kind': 'speech', 'id': ident, 'issue': issue})
            elif request['kind'] == 'question_solve':
                answer = stored_answers.get(ident)
                if not isinstance(answer, list) or len(answer) != 1:
                    raise ValueError('Missing or invalid stored answer: ' + ident)
                if verdict['solved'] == 'unknown':
                    disagreements.append({'kind': 'unsolved', 'id': ident, 'issue': issue})
                elif verdict['solved'] != answer[0]:
                    disagreements.append({'kind': 'answer', 'id': ident, 'issue': issue})
                if not verdict['picturesMatch']:
                    disagreements.append({'kind': 'picture', 'id': ident, 'issue': issue})
                if not verdict['skillMatchesObjectives']:
                    disagreements.append({'kind': 'skill', 'id': ident, 'issue': issue})
            elif request['kind'] == 'teaching':
                if verdict['verdict'] != 'taught':
                    disagreements.append({'kind': 'teaching', 'id': ident, 'issue': issue})
            elif not verdict['analysisOk']:
                disagreements.append({'kind': 'analysis', 'id': ident, 'issue': issue})
    return {'schemaVersion': 'mira.courseware.verification.v1', 'bodySha256': body_hash(body),
            'notesSha256': body_hash(notes), 'speechChecked': len(speeches),
            'questionsChecked': len(questions), 'goalsChecked': len(goals), 'disagreements': disagreements,
            'verifier': {'model': model, 'effort': effort, 'ranAt': ran_at}}


def _evidence_body(body):
    content = deepcopy(body)
    game_audio.verify_recordings(content, before_voice=True)
    for record in [content['stage'], *content['scenes']]:
        for key in ('createdAt', 'updatedAt'):
            record.pop(key, None)
    for scene in content['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') == 'speech':
                action.pop('audioId', None)
                action.pop('audioUrl', None)
        if scene.get('type') == 'quiz':
            for question in scene['content']['questions']:
                question.pop('questionAudioUrl', None)
    return content


def _evidence_input_hash(body, requests, picture_hashes):
    inputs = [{'kind': request['kind'], 'prompt': request['prompt'], 'schema': _schema(request['kind']),
               'pictures': [picture_hashes[filename] for filename in request['images']]} for request in requests]
    return body_hash({'content': _evidence_body(body), 'requests': inputs})


def evidence_input_hash(body, requests):
    """Identify the same built lesson before and after binding recorded audio."""
    picture_hashes = {filename: sha256(Path(filename).read_bytes()).hexdigest()
                      for filename in {image for request in requests for image in request['images']}}
    return _evidence_input_hash(body, requests, picture_hashes)


def verification_from_evidence(body, notes, requests, answers, evidence, *, model, effort):
    if (not isinstance(evidence, dict) or evidence.get('schemaVersion') != EVIDENCE_SCHEMA
            or evidence.get('notesSha256') != body_hash(notes)
            or evidence.get('inputSha256') != evidence_input_hash(body, requests)):
        raise ValueError('Lesson or verifier inputs differ from the recorded independent review')
    if (evidence['model'], evidence['effort']) != (model, effort):
        raise ValueError('Recorded review used a different model or reasoning effort')
    if not re.fullmatch(r'[a-f0-9]{64}', str(evidence.get('reviewedBodySha256', ''))):
        raise ValueError('Recorded review is missing the original body identity')
    if not isinstance(evidence.get('ranAt'), str) or datetime.fromisoformat(evidence['ranAt']).tzinfo is None:
        raise ValueError('Recorded review is missing the verifier timestamp')
    receipt = build_receipt(body, notes, requests, evidence['verdicts'], answers,
                            model=model, effort=effort, ran_at=evidence['ranAt'])
    receipt['reusedEvidence'] = {'sha256': body_hash(evidence), 'inputSha256': evidence['inputSha256'],
                                 'reviewedBodySha256': evidence['reviewedBodySha256']}
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('body', 'notes', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--media')
    parser.add_argument('--model', default=VERIFIER_MODEL)
    parser.add_argument('--effort', default=VERIFIER_EFFORT)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=1,
                        help='run independent verifier requests concurrently, returning verdicts in request order')
    parser.add_argument('--no-retry', action='store_true',
                        help='invoke the model once per request when running a new review')
    evidence_options = parser.add_mutually_exclusive_group()
    evidence_options.add_argument('--save-evidence', type=Path,
                                  help='save authentic model verdicts for the identical lesson after audio binding')
    evidence_options.add_argument('--reuse-evidence', type=Path,
                                  help='validate and reuse recorded model verdicts without a second model call')
    args = parser.parse_args()
    try:
        body = json.loads(Path(args.body).read_text(encoding='utf-8'))
        if 'stage' not in body and 'body' in body and 'lines' in body:
            body = body['body']
        notes = json.loads(Path(args.notes).read_text(encoding='utf-8'))
        requests = build_requests(body, notes, media=args.media or Path(args.body).resolve().parent / 'media', teaching=True)
        answers = {q['id']: q['answer'] for scene in body.get('scenes', []) if scene.get('type') == 'quiz'
                   for q in scene.get('content', {}).get('questions', [])}
        if args.reuse_evidence:
            evidence = json.loads(args.reuse_evidence.read_text(encoding='utf-8'))
            from courseware.tools import verify_delta, verify_presentation
            replayers = {verify_delta.EVIDENCE_SCHEMA: verify_delta.replay,
                         verify_presentation.EVIDENCE_SCHEMA: verify_presentation.replay}
            schema = evidence.get('schemaVersion') if isinstance(evidence, dict) else None
            replayer = replayers.get(schema) if isinstance(schema, str) else None
            if replayer is not None:
                receipt = replayer(body, notes, args.media or Path(args.body).resolve().parent / 'media',
                                   evidence, model=args.model, effort=args.effort)
            else:
                receipt = verification_from_evidence(body, notes, requests, answers, evidence,
                                                     model=args.model, effort=args.effort)
        else:
            if args.save_evidence and (args.save_evidence.exists() or args.save_evidence.resolve() == Path(args.out).resolve()):
                raise ValueError('Verification evidence requires a new file distinct from the receipt')
            input_hash = evidence_input_hash(body, requests) if args.save_evidence else None
            runner_options = {'runner': partial(default_runner, attempts=1)} if args.no_retry else {}
            verdicts = run_requests(requests, model=args.model, effort=args.effort, jobs=args.jobs,
                                    **runner_options)
            ran_at = datetime.now(timezone.utc).isoformat()
            receipt = build_receipt(body, notes, requests, verdicts, answers, model=args.model,
                                    effort=args.effort, ran_at=ran_at)
            if args.save_evidence:
                if input_hash != evidence_input_hash(body, requests):
                    raise ValueError('Independent review input changed during verification')
                evidence = {'schemaVersion': EVIDENCE_SCHEMA, 'inputSha256': input_hash,
                            'reviewedBodySha256': receipt['bodySha256'], 'notesSha256': receipt['notesSha256'],
                            'model': args.model, 'effort': args.effort, 'ranAt': ran_at, 'verdicts': verdicts}
                with args.save_evidence.open('x', encoding='utf-8') as stream:
                    json.dump(evidence, stream, ensure_ascii=False, indent=2)
                    stream.write('\n')
        if args.reuse_evidence and args.reuse_evidence.resolve() == Path(args.out).resolve():
            raise ValueError('The verification receipt must not overwrite its evidence')
        Path(args.out).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(2, 'Verification failed: %s\n' % exc)
    print('Checked %d speech lines and %d questions; %d disagreements.' %
          (receipt['speechChecked'], receipt['questionsChecked'], len(receipt['disagreements'])))
    for disagreement in receipt['disagreements']:
        print(json.dumps(disagreement, ensure_ascii=False))
    return int(bool(receipt['disagreements']))


if __name__ == '__main__':
    raise SystemExit(main())
