"""Independently verify lesson speech and questions against official notes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile

from courseware.tools.check import body_hash


VERIFIER_MODEL = 'gpt-6.1-terra'
VERIFIER_EFFORT = 'low'
PROMPT = Path(__file__).parent / 'prompts' / 'verify.v1.md'
ANALYSIS_PROMPT = Path(__file__).parent / 'prompts' / 'verify_analysis.v1.md'
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
                   'issue': {'type': ['string', 'null']}},
    'required': ['id', 'solved', 'skillMatchesObjectives', 'issue'],
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
                solves.append({'id': question['id'], 'question': question['question'],
                               'options': options, 'skill': question['skill']})
                analyses.append({'id': question['id'], 'question': question['question'],
                                 'options': options, 'answer': answer[0], 'analysis': question['analysis']})
    for items in (speeches, solves):
        ids = [item['id'] for item in items]
        if any(not isinstance(ident, str) or not ident for ident in ids) or len(ids) != len(set(ids)):
            raise ValueError('Item ids must be nonempty and unique within each kind')
    return speeches, solves, analyses


def build_requests(body, notes, *, batch_size=40):
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('batch_size must be a positive integer')
    requests = []
    for kind, items in zip(('speech', 'question_solve', 'question_analysis'), _items(body)):
        template = (ANALYSIS_PROMPT if kind == 'question_analysis' else PROMPT).read_text(encoding='utf-8')
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            prompt = template.replace('$NOTES', json.dumps(notes, ensure_ascii=False, sort_keys=True))
            prompt = prompt.replace('$KIND', kind).replace('$ITEMS', json.dumps(batch, ensure_ascii=False, sort_keys=True))
            requests.append({'kind': kind, 'items': batch, 'prompt': prompt})
    return requests


def _schema(kind):
    item_schema = {'speech': SPEECH_VERDICT_SCHEMA, 'question_solve': QUESTION_SOLVE_VERDICT_SCHEMA,
                   'question_analysis': QUESTION_ANALYSIS_VERDICT_SCHEMA}[kind]
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
        if request['kind'] == 'question_solve' and verdict['solved'] not in [option['value'] for option in items[ident]['options']]:
            raise ValueError('Solved answer is not an option: ' + ident)
        seen.add(ident)
    if seen != set(items):
        raise ValueError('Missing verdict ids: ' + ', '.join(sorted(set(items) - seen)))
    return result['verdicts']


def default_runner(prompt, schema, model, effort):
    binary = os.environ.get('MIRA_CODEX_BIN', '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
    with tempfile.TemporaryDirectory() as directory:
        schema_path = Path(directory) / 'schema.json'
        output_path = Path(directory) / 'output.json'
        schema_path.write_text(json.dumps(schema), encoding='utf-8')
        command = [binary, 'exec', '-m', model, '-c', 'model_reasoning_effort=' + effort,
                   '-s', 'read-only', '--skip-git-repo-check', '--ephemeral', '--output-schema', str(schema_path), '-o', str(output_path), '-']
        for attempt in range(2):
            stderr = ''
            try:
                output_path.unlink(missing_ok=True)
                result = subprocess.run(command, input=prompt, text=True, cwd=directory, check=True, capture_output=True)
                stderr = result.stderr or ''
                return json.loads(output_path.read_text(encoding='utf-8'))
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                if attempt == 1:
                    stderr = getattr(exc, 'stderr', None) or stderr
                    detail = ': ' + stderr[-300:] if stderr else ''
                    raise RuntimeError('Codex verification failed after two attempts: ' + str(exc) + detail) from exc


def run_requests(requests, runner=default_runner, *, model=VERIFIER_MODEL, effort=VERIFIER_EFFORT):
    verdicts = []
    for request in requests:
        result = runner(request['prompt'], _schema(request['kind']), model, effort)
        verdicts.extend(_validate(request, result))
    return verdicts


def build_receipt(body, notes, requests, verdicts, stored_answers, *, model, effort, ran_at):
    speeches, questions, analyses = _items(body)
    expected = {'speech': speeches, 'question_solve': questions, 'question_analysis': analyses}
    supplied = {'speech': [], 'question_solve': [], 'question_analysis': []}
    for request in requests:
        supplied[request['kind']].extend(request['items'])
    if supplied != expected:
        raise ValueError('Requests do not cover the body exactly')
    if len(verdicts) != len(speeches) + len(questions) + len(analyses):
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
                if verdict['solved'] != answer[0]:
                    disagreements.append({'kind': 'answer', 'id': ident, 'issue': issue})
                if not verdict['skillMatchesObjectives']:
                    disagreements.append({'kind': 'skill', 'id': ident, 'issue': issue})
            elif not verdict['analysisOk']:
                disagreements.append({'kind': 'analysis', 'id': ident, 'issue': issue})
    return {'schemaVersion': 'mira.courseware.verification.v1', 'bodySha256': body_hash(body),
            'notesSha256': body_hash(notes), 'speechChecked': len(speeches),
            'questionsChecked': len(questions), 'disagreements': disagreements,
            'verifier': {'model': model, 'effort': effort, 'ranAt': ran_at}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('body', 'notes', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--model', default=VERIFIER_MODEL)
    parser.add_argument('--effort', default=VERIFIER_EFFORT)
    args = parser.parse_args()
    try:
        body = json.loads(Path(args.body).read_text(encoding='utf-8'))
        notes = json.loads(Path(args.notes).read_text(encoding='utf-8'))
        requests = build_requests(body, notes)
        answers = {q['id']: q['answer'] for scene in body.get('scenes', []) if scene.get('type') == 'quiz'
                   for q in scene.get('content', {}).get('questions', [])}
        verdicts = run_requests(requests, model=args.model, effort=args.effort)
        receipt = build_receipt(body, notes, requests, verdicts, answers, model=args.model,
                                effort=args.effort, ran_at=datetime.now(timezone.utc).isoformat())
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
