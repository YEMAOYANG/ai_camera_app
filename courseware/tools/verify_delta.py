"""Continue an exact first-round G7 review with one independent delta round."""

import argparse
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote

from courseware.kit import slides
from courseware.tools import check, verify


EVIDENCE_SCHEMA = 'mira.courseware.verification-delta-evidence.v1'
APPEND_AUTHORIZATION_SCHEMA = 'mira.courseware.verification-append-authorization.v1'
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_PRIOR_MEDIA = Path('/mira-g7-prior-picture-digests')


@dataclass
class DeltaPlan:
    body: dict
    notes: dict
    media: Path
    prior: dict
    full: list
    requests: list
    reused: dict
    teaching: dict
    extra_goals: tuple
    pictures: dict
    input_sha256: str
    model: str
    effort: str
    append_authorization: dict | None = None


def _answers(body):
    return {q['id']: q['answer'] for scene in body['scenes'] if scene['type'] == 'quiz'
            for q in scene['content']['questions']}


def _date(value):
    if not isinstance(value, str):
        raise ValueError('Invalid verifier timestamp')
    date = datetime.fromisoformat(value)
    if date.tzinfo is None:
        raise ValueError('Invalid verifier timestamp')
    return date


def _picture_paths(requests):
    return {filename for request in requests for filename in request['images']}


def _read_pictures(requests, media):
    root = Path(media).resolve()
    pictures = {}
    for filename in _picture_paths(requests):
        path = Path(filename)
        original = root / path.name
        if path.parent != root or original.is_symlink() or not original.is_file():
            raise ValueError('Verifier picture is outside the declared media directory')
        pictures[filename] = sha256(path.read_bytes()).hexdigest()
    return pictures


def _stored_pictures(requests, pictures):
    paths = _picture_paths(requests)
    if (not isinstance(pictures, dict) or set(pictures) != {Path(p).name for p in paths}
            or any(not isinstance(digest, str) or not _SHA.fullmatch(digest) for digest in pictures.values())
            or any(Path(p).parent != _PRIOR_MEDIA for p in paths)):
        raise ValueError('Incomplete or invalid prior picture digests')
    return {path: pictures[Path(path).name] for path in paths}


def _request_digest(request, pictures):
    return verify.body_hash({
        'kind': request['kind'], 'prompt': request['prompt'], 'schema': verify._schema(request['kind']),
        'pictures': [pictures[p] for p in request['images']],
    })


def _verdict_index(requests, verdicts):
    indexed = {}
    offset = 0
    for request in requests:
        end = offset + len(request['items'])
        batch = verify._validate(request, {'verdicts': verdicts[offset:end]})
        for verdict in batch:
            key = (request['kind'], verdict['id'])
            if key in indexed:
                raise ValueError('Duplicate verifier item: ' + repr(key))
            indexed[key] = verdict
        offset = end
    if offset != len(verdicts):
        raise ValueError('Unexpected extra verdicts')
    return indexed


def _item_index(requests, pictures):
    indexed = {}
    for request in requests:
        for item in request['items']:
            key = (request['kind'], item['id'])
            if key in indexed:
                raise ValueError('Duplicate verifier item: ' + repr(key))
            canonical = deepcopy(item)
            for picture in canonical.get('pictures', ()):
                if 'attachment' in picture:
                    index = picture.pop('attachment') - 1
                    picture['sha256'] = pictures[request['images'][index]]
            indexed[key] = verify.body_hash(canonical)
    return indexed


def _subset(full, selected, body, notes):
    requests = []
    for request in full:
        kind = request['kind']
        items = [deepcopy(item) for item in request['items'] if (kind, item['id']) in selected]
        if not items:
            continue
        images = []
        for item in items:
            for picture in item.get('pictures', ()):
                if 'attachment' in picture:
                    images.append(request['images'][picture['attachment'] - 1])
                    picture['attachment'] = len(images)
        narration = verify._narration(body) if kind == 'teaching' else None
        requests.append(verify._request(kind, items, notes, images=images, narration=narration))
    return requests


def _replace_media_namespace(value, prefix):
    if isinstance(value, str):
        return value.replace(prefix, '/api/classroom-media/_stage_/')
    if isinstance(value, list):
        return [_replace_media_namespace(item, prefix) for item in value]
    if isinstance(value, dict):
        return {key: _replace_media_namespace(item, prefix) for key, item in value.items()}
    return value


def _comparison_body(body):
    normalized = verify._evidence_body(body)
    stage_id = normalized['stage'].pop('id')
    if not isinstance(stage_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', stage_id):
        raise ValueError('Invalid stage namespace')
    prefix = f'/api/classroom-media/{stage_id}/'
    for scene in normalized['scenes']:
        if 'stageId' in scene and scene.pop('stageId') != stage_id:
            raise ValueError('Scene belongs to a different stage')
        if 'content' not in scene:
            continue
        canvas = scene['content'].get('canvas') if scene['type'] == 'slide' else None
        compiled_canvas = (isinstance(canvas, dict) and isinstance(canvas.get('elements'), list)
                           and canvas.get('id') == slides.canvas(canvas['elements'])['id'])
        scene['content'] = _replace_media_namespace(scene['content'], prefix)
        if compiled_canvas:
            canvas = scene['content']['canvas']
            canvas['id'] = slides.canvas(canvas['elements'])['id']
    return normalized


def _changed_scenes(prior, body):
    old, new = _comparison_body(prior), _comparison_body(body)
    old_ids = [scene['id'] for scene in old['scenes']]
    new_ids = [scene['id'] for scene in new['scenes']]
    if (old['stage'] != new['stage'] or old_ids != new_ids or len(set(new_ids)) != len(new_ids)
            or any(not isinstance(key, str) or not key for key in new_ids)):
        raise ValueError('Delta requires the same stage and stable scene order')
    return {i for i, (a, b) in enumerate(zip(old['scenes'], new['scenes']), 1) if a != b}


def _cited_scenes(value, count):
    if not re.fullmatch(r'\s*[1-9]\d*(?:\s*,\s*[1-9]\d*)*\s*', value):
        return None
    citations = [int(number) for number in value.split(',')]
    if len(citations) != len(set(citations)) or any(n > count for n in citations):
        return None
    return set(citations)


def _validate_prior(prior, notes, model, effort):
    if (not isinstance(prior, dict) or set(prior) != {'body', 'evidenceUtf8', 'evidenceSha256', 'pictures'}
            or not isinstance(prior['evidenceUtf8'], str)):
        raise ValueError('Malformed prior verification evidence')
    raw = prior['evidenceUtf8'].encode('utf-8')
    if sha256(raw).hexdigest() != prior['evidenceSha256']:
        raise ValueError('Wrong prior evidence SHA')
    evidence = json.loads(raw)
    if not isinstance(evidence, dict) or evidence.get('schemaVersion') != verify.EVIDENCE_SCHEMA:
        raise ValueError('Delta requires original first-round v1 evidence')
    body = prior['body']
    if evidence.get('reviewedBodySha256') != verify.body_hash(body):
        raise ValueError('Wrong prior body for independent verification')
    if evidence.get('notesSha256') != verify.body_hash(notes):
        raise ValueError('Delta requires unchanged official notes')
    if (evidence.get('model'), evidence.get('effort')) != (model, effort):
        raise ValueError('Prior verification used a different model or effort')
    _date(evidence.get('ranAt'))
    requests = verify.build_requests(body, notes, media=_PRIOR_MEDIA, teaching=True, check_files=False)
    pictures = _stored_pictures(requests, prior['pictures'])
    if evidence.get('inputSha256') != verify._evidence_input_hash(body, requests, pictures):
        raise ValueError('Wrong prior verifier inputs')
    receipt = verify.build_receipt(body, notes, requests, evidence['verdicts'], _answers(body),
                                   model=model, effort=effort, ran_at=evidence['ranAt'])
    return requests, pictures, evidence, receipt


def _plan(body, notes, media, prior, extra_goals, model, effort):
    old, old_pictures, evidence, receipt = _validate_prior(prior, notes, model, effort)
    full = verify.build_requests(body, notes, media=media, teaching=True, strict_media=True)
    pictures = _read_pictures(full, media)
    previous = _item_index(old, old_pictures)
    current = _item_index(full, pictures)
    original = _verdict_index(old, evidence['verdicts'])
    changed_scenes = _changed_scenes(prior['body'], body)
    failed_kinds = {'speech': 'speech', 'analysis': 'question_analysis', 'teaching': 'teaching'}
    failed = {(failed_kinds.get(item['kind'], 'question_solve'), item['id']) for item in receipt['disagreements']}
    changed = {key for key, signature in current.items() if previous.get(key) != signature}
    changed_quiz = {ident for kind, ident in changed if kind in ('question_solve', 'question_analysis')}
    changed_scenes.update(i for i, scene in enumerate(body['scenes'], 1) if scene['type'] == 'quiz'
                          and any(q['id'] in changed_quiz for q in scene['content']['questions']))
    goals = {ident for kind, ident in current if kind == 'teaching'}
    if not set(extra_goals) <= goals:
        raise ValueError('Unknown additional teaching goal')

    selected = set()
    teaching = {}
    for key in current:
        kind, ident = key
        if kind == 'teaching':
            verdict = original.get(key)
            cited = _cited_scenes(verdict['taughtAt'], len(body['scenes'])) if verdict else None
            affected = sorted(changed_scenes & (cited or set()))
            revisit = key in changed or key in failed or cited is None or bool(affected) or ident in extra_goals
            teaching[ident] = {'reviewAgain': revisit, 'priorFailed': key in failed,
                               'citedScenes': sorted(cited) if cited else None, 'changedCitedScenes': affected,
                               'explicitlyIncluded': ident in extra_goals}
        else:
            revisit = key in changed or key in failed or (kind != 'speech' and ident in changed_quiz)
        if revisit:
            selected.add(key)
    if not selected:
        raise ValueError('No changed or unresolved verifier items to review')

    return DeltaPlan(body, notes, Path(media), prior, full, _subset(full, selected, body, notes),
                     {key: original[key] for key in current if key not in selected}, teaching,
                     tuple(sorted(set(extra_goals))), pictures,
                     verify._evidence_input_hash(body, full, pictures), model, effort)


def _append_scope(authorization, prior, body, input_sha, previous_time):
    expected = {'schemaVersion', 'confirmedBy', 'userQuote', 'confirmedAt', 'priorDeltaSha256',
                'canonicalBodySha256', 'inputSha256', 'speechIds', 'goalId'}
    if (not isinstance(authorization, dict) or set(authorization) != expected
            or authorization['schemaVersion'] != APPEND_AUTHORIZATION_SCHEMA
            or authorization['confirmedBy'] != 'owner'
            or not isinstance(authorization['userQuote'], str) or not authorization['userQuote'].strip()
            or authorization['priorDeltaSha256'] != sha256(prior).hexdigest()
            or authorization['canonicalBodySha256'] != verify.body_hash(verify._evidence_body(body))
            or authorization['inputSha256'] != input_sha
            or _date(authorization['confirmedAt']) < _date(previous_time)):
        raise ValueError('Append-only review authorization does not match the frozen inputs')
    speech_ids, goal_id = authorization['speechIds'], authorization['goalId']
    if (not isinstance(speech_ids, list) or len(speech_ids) != 2
            or not all(isinstance(ident, str) and ident.strip() for ident in speech_ids)
            or len(set(speech_ids)) != 2
            or not isinstance(goal_id, str) or not re.fullmatch(r'goal-[1-9][0-9]*', goal_id)):
        raise ValueError('Append-only review requires two distinct speech IDs and one learning goal')
    return set(speech_ids), goal_id


def _append_scenes(before, after, speech_ids):
    original, restored = verify._evidence_body(before), verify._evidence_body(after)
    old_lines = {action['id']: action['text'] for scene in original['scenes'] for action in scene.get('actions', [])
                 if action.get('type') == 'speech' and action['id'] in speech_ids}
    found, changed = set(), set()
    for number, scene in enumerate(restored['scenes'], 1):
        for action in scene.get('actions', []):
            if action.get('type') != 'speech' or action['id'] not in speech_ids:
                continue
            ident, text = action['id'], action['text']
            prefix = old_lines.get(ident)
            if (ident in found or not prefix or not text.startswith(prefix)
                    or not text[len(prefix):].strip()):
                raise ValueError('Append-only review must retain each authorized speech as an exact prefix')
            found.add(ident)
            changed.add(number)
            action['text'] = prefix
    if found != speech_ids or restored != original:
        raise ValueError('Append-only review changes content outside the two authorized speech suffixes')
    return changed


def _plan_append(body, notes, media, prior, authorization, model, effort, *, prior_media=None):
    if not isinstance(prior, dict) or set(prior) != {'evidenceUtf8'} or not isinstance(prior['evidenceUtf8'], str):
        raise ValueError('Malformed prior delta evidence for append-only review')
    raw = prior['evidenceUtf8'].encode('utf-8')
    previous = json.loads(raw)
    if (not isinstance(previous, dict) or previous.get('schemaVersion') != EVIDENCE_SCHEMA
            or 'appendAuthorization' in previous):
        raise ValueError('Append-only review requires the original second-round delta evidence')
    before = previous['reviewedBody']
    prior_media = prior_media if prior_media is not None else media
    receipt = replay(before, notes, prior_media, previous, model=model, effort=effort)
    old = _replay_plan(before, notes, prior_media, previous, model, effort)
    prior_verdicts = old.reused | _verdict_index(old.requests, previous['deltaVerdicts'])

    full = verify.build_requests(body, notes, media=media, teaching=True, strict_media=True)
    pictures = _read_pictures(full, media)
    input_sha = verify._evidence_input_hash(body, full, pictures)
    speech_ids, goal_id = _append_scope(authorization, raw, body, input_sha, previous['ranAt'])
    if [(item['kind'], item['id']) for item in receipt['disagreements']] != [('teaching', goal_id)]:
        raise ValueError('The authorized learning goal must be the only unresolved prior item')
    changed_scenes = _append_scenes(before, body, speech_ids)
    citations = {ident: _cited_scenes(verdict['taughtAt'], len(body['scenes']))
                 for (kind, ident), verdict in prior_verdicts.items() if kind == 'teaching'}
    prior_goal_citations = citations[goal_id]
    if (any(scenes is None for ident, scenes in citations.items() if ident != goal_id)
            or (prior_goal_citations is not None and not changed_scenes <= prior_goal_citations)):
        raise ValueError('Append-only review requires valid reused teaching citations and a matching goal scope')
    _verify_presentation_media(before, prior_media, old.pictures)
    _verify_presentation_media(body, media, pictures)
    if {Path(path).name: digest for path, digest in pictures.items()} != {
            Path(path).name: digest for path, digest in old.pictures.items()}:
        raise ValueError('Append-only review requires unchanged quiz pictures')
    old_items, current_items = _item_index(old.full, old.pictures), _item_index(full, pictures)
    speech_keys = {('speech', ident) for ident in speech_ids}
    if (old_items.keys() != current_items.keys()
            or {key for key in old_items if old_items[key] != current_items[key]} != speech_keys):
        raise ValueError('Append-only review changed an unapproved verifier item')
    selected = speech_keys | {('teaching', goal_id)}
    teaching = {goal_id: {'reviewAgain': True, 'priorFailed': True,
                          'citedScenes': sorted(prior_goal_citations) if prior_goal_citations else None,
                          'changedCitedScenes': sorted(changed_scenes), 'explicitlyIncluded': True}}
    return DeltaPlan(body, notes, Path(media), prior, full, _subset(full, selected, body, notes),
                     {key: verdict for key, verdict in prior_verdicts.items() if key not in selected},
                     teaching, (), pictures, input_sha, model, effort, deepcopy(authorization))


def plan_review(*, body, notes, media, prior_body, prior_notes, prior_media, prior_evidence,
                prior_evidence_sha256, extra_goals=(), model=verify.VERIFIER_MODEL, effort=verify.VERIFIER_EFFORT,
                append_authorization=None):
    if sha256(prior_evidence).hexdigest() != prior_evidence_sha256:
        raise ValueError('Wrong prior evidence SHA')
    if verify.body_hash(prior_notes) != verify.body_hash(notes):
        raise ValueError('Delta requires unchanged official notes')
    if append_authorization is not None:
        if extra_goals:
            raise ValueError('Append-only review scope comes exclusively from the owner authorization')
        previous = json.loads(prior_evidence)
        if not isinstance(previous, dict) or previous.get('reviewedBody') != prior_body:
            raise ValueError('Wrong exact prior body for append-only review')
        return _plan_append(deepcopy(body), deepcopy(notes), media, {'evidenceUtf8': prior_evidence.decode('utf-8')},
                            append_authorization, model, effort, prior_media=prior_media)
    requests = verify.build_requests(prior_body, prior_notes, media=prior_media, teaching=True, strict_media=True)
    pictures = {Path(path).name: digest for path, digest in _read_pictures(requests, prior_media).items()}
    prior = {'body': deepcopy(prior_body), 'evidenceUtf8': prior_evidence.decode('utf-8'),
             'evidenceSha256': prior_evidence_sha256, 'pictures': pictures}
    return _plan(deepcopy(body), deepcopy(notes), media, prior, extra_goals, model, effort)


def _compose(plan, evidence):
    fresh = _verdict_index(plan.requests, evidence['deltaVerdicts'])
    if plan.append_authorization is not None:
        goal_id = plan.append_authorization['goalId']
        goal = fresh['teaching', goal_id]
        cited = _cited_scenes(goal['taughtAt'], len(plan.body['scenes']))
        changed = set(plan.teaching[goal_id]['changedCitedScenes'])
        if goal['verdict'] == 'taught' and (cited is None or not changed <= cited):
            raise ValueError('Append-only review produced invalid teaching citations')
    combined = plan.reused | fresh
    verdicts = [combined[(request['kind'], item['id'])]
                for request in plan.full for item in request['items']]
    receipt = verify.build_receipt(plan.body, plan.notes, plan.full, verdicts, _answers(plan.body),
                                   model=plan.model, effort=plan.effort, ran_at=evidence['ranAt'])
    receipt['reusedEvidence'] = {'schemaVersion': EVIDENCE_SCHEMA, 'sha256': verify.body_hash(evidence),
                                 'inputSha256': plan.input_sha256,
                                 'reviewedBodySha256': evidence['reviewedBodySha256']}
    return receipt


def _request_hashes(plan):
    return [_request_digest(request, plan.pictures) for request in plan.requests]


def _spotlight_swap(prior, body):
    old, new = _comparison_body(prior), _comparison_body(body)
    if len(old['scenes']) != len(new['scenes']):
        raise ValueError('Presentation rebind requires the same scenes')
    changed = [(a, b) for a, b in zip(old['scenes'], new['scenes']) if a != b]
    if len(changed) != 1 or changed[0][0].get('type') != 'slide':
        raise ValueError('Presentation rebind requires one changed slide')
    before, after = changed[0]
    old_actions, new_actions = before['actions'], after['actions']
    if len(old_actions) != len(new_actions):
        raise ValueError('Presentation rebind cannot add or remove actions')
    actions = [(a, b) for a, b in zip(old_actions, new_actions) if a != b]
    elements = [e['id'] for e in before['content']['canvas']['elements']]
    action_ids = [a.get('id') for a, _ in actions]
    old_targets = [a.get('elementId') for a, _ in actions]
    new_targets = [b.get('elementId') for _, b in actions]
    if (len(actions) != 2 or len(set(elements)) != len(elements)
            or any(not isinstance(key, str) or not key or sum(a.get('id') == key for a in old_actions) != 1
                   for key in action_ids)
            or old_targets == new_targets or old_targets != new_targets[::-1]
            or any(not isinstance(target, str) or target not in elements for target in old_targets)
            or any(a.get('type') != 'spotlight' or a.get('id') != b.get('id') for a, b in actions)):
        raise ValueError('Presentation rebind requires an exact swap of two existing spotlight targets')
    for a, b in actions:
        a['elementId'] = b['elementId']
    if old != new:
        raise ValueError('Presentation rebind changes data outside the two spotlight targets')
    return {'sceneId': before['id'], 'actionIds': action_ids, 'priorTargets': old_targets, 'currentTargets': new_targets}


def _verify_presentation_media(body, media, reviewed_pictures):
    """Non-quiz pictures must be content-addressed by the already reviewed body."""
    known = {Path(filename).name for filename in reviewed_pictures}
    names = {unquote(m.group().split('/media/', 1)[1].split('?', 1)[0].split('#', 1)[0])
             for value in check.strings(verify._evidence_body(body)) for m in check.MEDIA_URL.finditer(value)}
    for name in names - known:
        if Path(name).suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'):
            continue
        digest = check.HASH.search(name)
        path = Path(media) / name
        if (not digest or Path(name).name != name or path.is_symlink() or not path.is_file()
                or sha256(path.read_bytes()).hexdigest() != digest.group(1).lower()):
            raise ValueError('Presentation media differs from its reviewed content address: ' + name)


def _replay_plan(body, notes, media, evidence, model, effort):
    plan = _plan(body, notes, media, evidence['prior'], evidence['extraTeaching'], model, effort)
    if evidence['inputSha256'] != plan.input_sha256:
        raise ValueError('Wrong current verifier inputs for delta review')
    if evidence['extraTeaching'] != list(plan.extra_goals) or evidence['deltaRequestSha256'] != _request_hashes(plan):
        raise ValueError('Delta requests do not match the current comparison')
    prior_time = json.loads(plan.prior['evidenceUtf8'])['ranAt']
    if _date(evidence['ranAt']) < _date(prior_time):
        raise ValueError('Delta review predates the prior review')
    return plan


def replay(body, notes, media, evidence, *, model=verify.VERIFIER_MODEL, effort=verify.VERIFIER_EFFORT):
    expected = {'schemaVersion', 'prior', 'extraTeaching', 'inputSha256', 'notesSha256', 'reviewedBody', 'reviewedBodySha256',
                'model', 'effort', 'ranAt', 'deltaRequestSha256', 'deltaVerdicts'}
    append_review = isinstance(evidence, dict) and 'appendAuthorization' in evidence
    if append_review:
        expected.add('appendAuthorization')
    if not isinstance(evidence, dict) or set(evidence) != expected or evidence['schemaVersion'] != EVIDENCE_SCHEMA:
        raise ValueError('Malformed delta verification evidence')
    if (evidence['model'], evidence['effort']) != (model, effort):
        raise ValueError('Delta verification used a different model or effort')
    if (evidence['notesSha256'] != verify.body_hash(notes)
            or evidence['reviewedBodySha256'] != verify.body_hash(evidence['reviewedBody'])):
        raise ValueError('Wrong notes or body identity for delta review')
    if not isinstance(evidence['extraTeaching'], list) or not all(isinstance(x, str) for x in evidence['extraTeaching']):
        raise ValueError('Invalid extra teaching goals')
    if not isinstance(evidence['deltaVerdicts'], list):
        raise ValueError('Missing delta verdicts')
    reviewed = evidence['reviewedBody']
    if append_review:
        if (evidence['extraTeaching'] or verify._evidence_body(reviewed) != verify._evidence_body(body)
                or not isinstance(evidence['appendAuthorization'], dict)):
            raise ValueError('Append-only evidence requires the exact reviewed lesson')
        plan = _plan_append(body, notes, media, evidence['prior'], evidence['appendAuthorization'], model, effort)
        if (evidence['inputSha256'] != plan.input_sha256 or evidence['deltaRequestSha256'] != _request_hashes(plan)
                or _date(evidence['ranAt']) < _date(plan.append_authorization['confirmedAt'])):
            raise ValueError('Append-only review requests or timestamp do not match the authorized plan')
        return _compose(plan, evidence)
    if verify._evidence_body(reviewed) == verify._evidence_body(body):
        return _compose(_replay_plan(body, notes, media, evidence, model, effort), evidence)
    swap = _spotlight_swap(reviewed, body)
    prior_plan = _replay_plan(reviewed, notes, media, evidence, model, effort)
    _compose(prior_plan, evidence)
    current = verify.build_requests(body, notes, media=media, teaching=True, strict_media=True)
    pictures = _read_pictures(current, media)
    if ([_request_digest(q, pictures) for q in current] !=
            [_request_digest(q, prior_plan.pictures) for q in prior_plan.full]):
        raise ValueError('Presentation rebind changed verifier requests or attached pictures')
    _verify_presentation_media(body, media, pictures)
    updated = replace(prior_plan, body=body, full=current,
                      input_sha256=verify._evidence_input_hash(body, current, pictures))
    receipt = _compose(updated, evidence)
    receipt['reusedEvidence']['presentationRebind'] = {**swap, 'reviewedInputSha256': prior_plan.input_sha256}
    return receipt


def _run_requests(plan, jobs):
    runner = partial(verify.default_runner, attempts=1)
    if not _picture_paths(plan.requests):
        return verify.run_requests(plan.requests, runner=runner, model=plan.model, effort=plan.effort, jobs=jobs)
    with tempfile.TemporaryDirectory() as directory:
        attachments = {}
        for i, filename in enumerate(sorted(_picture_paths(plan.requests))):
            raw = Path(filename).read_bytes()
            if sha256(raw).hexdigest() != plan.pictures[filename]:
                raise ValueError('Current verifier picture changed before submission')
            target = Path(directory) / (str(i) + Path(filename).suffix)
            target.write_bytes(raw)
            attachments[filename] = str(target)
        requests = [{**r, 'images': [attachments[p] for p in r['images']]} for r in plan.requests]
        return verify.run_requests(requests, runner=runner, model=plan.model, effort=plan.effort, jobs=jobs)


def run_review(plan, *, jobs=1, save_received=None):
    if plan.append_authorization is None and set(plan.prior) == {'evidenceUtf8'}:
        raise ValueError('Append-only review plan is missing its bound owner authorization')
    if _read_pictures(plan.full, plan.media) != plan.pictures:
        raise ValueError('Current verifier pictures changed before submission')
    if plan.append_authorization is not None:
        if _date(plan.append_authorization['confirmedAt']) > datetime.now(timezone.utc):
            raise ValueError('Append-only review authorization time is in the future')
        rebuilt = _plan_append(plan.body, plan.notes, plan.media, plan.prior, plan.append_authorization,
                               plan.model, plan.effort)
        if rebuilt != plan:
            raise ValueError('Append-only review plan changed before submission')
    verdicts = _run_requests(plan, jobs)
    evidence = {'schemaVersion': EVIDENCE_SCHEMA, 'prior': plan.prior, 'extraTeaching': list(plan.extra_goals),
                'inputSha256': plan.input_sha256, 'notesSha256': verify.body_hash(plan.notes),
                'reviewedBody': plan.body, 'reviewedBodySha256': verify.body_hash(plan.body),
                'model': plan.model, 'effort': plan.effort,
                'ranAt': datetime.now(timezone.utc).isoformat(), 'deltaRequestSha256': _request_hashes(plan),
                'deltaVerdicts': verdicts}
    if plan.append_authorization is not None:
        evidence['appendAuthorization'] = plan.append_authorization
    if save_received is not None:
        save_received(evidence)
    return replay(plan.body, plan.notes, plan.media, evidence, model=plan.model, effort=plan.effort), evidence


def _read_body(path):
    result = json.loads(path.read_text(encoding='utf-8'))
    return result['body'] if 'stage' not in result and 'body' in result and 'lines' in result else result


def _write_json(path, value, *, replace=False):
    if not replace:
        with path.open('x', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', encoding='utf-8', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('plan', 'run'):
        sub = commands.add_parser(command)
        for name in ('body', 'notes', 'prior-body', 'prior-evidence'):
            sub.add_argument('--' + name, type=Path, required=True)
        for name in ('media', 'prior-notes', 'prior-media'):
            sub.add_argument('--' + name, type=Path)
        sub.add_argument('--prior-evidence-sha256', required=True)
        sub.add_argument('--review-goal', action='append', default=[])
        sub.add_argument('--append-authorization', type=Path,
                         help='owner record authorizing two exact speech additions and one unresolved goal')
        sub.add_argument('--model', default=verify.VERIFIER_MODEL)
        sub.add_argument('--effort', default=verify.VERIFIER_EFFORT)
        if command == 'run':
            sub.add_argument('--out', type=Path, required=True)
            sub.add_argument('--save-evidence', type=Path, required=True)
            sub.add_argument('--expected-input-sha256', required=True,
                             help='the current input SHA-256 printed by plan and approved for submission')
            sub.add_argument('--jobs', type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    try:
        notes = json.loads(args.notes.read_text(encoding='utf-8'))
        prior_notes = json.loads(args.prior_notes.read_text(encoding='utf-8')) if args.prior_notes else notes
        plan = plan_review(body=_read_body(args.body), notes=notes, media=args.media or args.body.parent / 'media',
                           prior_body=_read_body(args.prior_body), prior_notes=prior_notes,
                           prior_media=args.prior_media or args.prior_body.parent / 'media',
                           prior_evidence=args.prior_evidence.read_bytes(), prior_evidence_sha256=args.prior_evidence_sha256,
                           extra_goals=args.review_goal, model=args.model, effort=args.effort,
                           append_authorization=json.loads(args.append_authorization.read_text(encoding='utf-8'))
                           if args.append_authorization is not None else None)
        if args.command == 'plan':
            print(json.dumps({'inputSha256': plan.input_sha256, 'reusedCount': len(plan.reused),
                              'teaching': plan.teaching,
                              'requests': [{'kind': r['kind'], 'ids': [x['id'] for x in r['items']],
                                            'images': len(r['images'])} for r in plan.requests]}, ensure_ascii=False))
            return 0
        if args.expected_input_sha256 != plan.input_sha256:
            raise ValueError('Current input does not match the approved SHA')
        if (os.path.lexists(args.out) or not args.out.parent.is_dir()
                or args.out.resolve() == args.save_evidence.resolve()):
            raise ValueError('Delta review needs new, distinct output and evidence paths')
        started = {'schemaVersion': EVIDENCE_SCHEMA, 'state': 'started_outcome_unconfirmed',
                   'inputSha256': plan.input_sha256, 'deltaRequestSha256': _request_hashes(plan)}
        if plan.append_authorization is not None:
            if os.path.lexists(args.save_evidence) or not args.save_evidence.parent.is_dir():
                raise ValueError('Append-only review requires a new evidence path')
            # Keep the claim even if the process fails after the external submission begins.
            # Its name binds one exception to the original archived second-round evidence.
            if _date(plan.append_authorization['confirmedAt']) > datetime.now(timezone.utc):
                raise ValueError('Append-only review authorization time is in the future')
            prior_sha = plan.append_authorization['priorDeltaSha256']
            claim = args.prior_evidence.resolve().with_name(f'.g7-append-{prior_sha}.json')
            started['appendAuthorization'] = plan.append_authorization
            try:
                _write_json(claim, started)
            except FileExistsError as exc:
                raise ValueError('The append-only review for this prior delta has already been claimed') from exc
        _write_json(args.save_evidence, started)
        if plan.append_authorization is not None:
            save_received = partial(_write_json, args.save_evidence, replace=True)
            receipt, _ = run_review(plan, jobs=args.jobs, save_received=save_received)
        else:
            receipt, evidence = run_review(plan, jobs=args.jobs)
            _write_json(args.save_evidence, evidence, replace=True)
        _write_json(args.out, receipt)
        print(json.dumps({'disagreements': receipt['disagreements'], 'deltaBatches': len(plan.requests),
                          'reusedCount': len(plan.reused)}, ensure_ascii=False))
        return int(bool(receipt['disagreements']))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(2, 'Delta verification failed: %s\n' % exc)


if __name__ == '__main__':
    raise SystemExit(main())
