"""Build immutable light releases from in-memory evidence and media bytes.

Inputs: identity, manifest, body, notes, brief, receipt, verification, roster,
confirmation, media (source filename -> bytes), and gateIssues from the shared
checker. Identity names every author in authorModels and requires integer
estimatedMinutes (5-120). The verification receipt's verifier.model must differ
from every author model, case-insensitively. Evidence hashes are over canonical
JSON records. No model, database, network or filesystem operations run here.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import PurePosixPath
import re

from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA, MEDIA, check_questions, validate_release
from content.textbook_release_media import media_mime_type
from core.errors import ApiError

LIGHT_SCHEMA = 'mira.courseware.light-release.v1'
# Namespace identifiers inside page scripts and inline SVG are not fetched media.
NAMESPACE = re.compile(r'https?://www\.w3\.org/(?:2000/svg|1999/xlink|1999/xhtml)')
GATES = tuple('G%d' % i for i in range(8))
AUDIO_METHOD = ('every speech action has an audio file whose bytes match the sha256 in its file name; '
                'no speech recognition and no listening review')


def require(condition, code):
    if not condition:
        raise ValueError(code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _independent_verifier(author_models, verifier):
    require(isinstance(author_models, list) and bool(author_models) and all(_text(model) for model in author_models)
            and isinstance(verifier, dict) and _text(verifier.get('model'))
            and verifier['model'].strip().casefold() not in {model.strip().casefold() for model in author_models},
            'verification_not_independent')
    return verifier['model']


def _confirmation(value):
    require(isinstance(value, dict) and _text(value.get('userQuote'))
            and value.get('confirmedBy') == 'owner', 'authorization_missing')
    try:
        stamp = datetime.fromisoformat(value.get('confirmedAt', '').replace('Z', '+00:00'))
        require(stamp.utcoffset() is not None, 'confirmation_time_invalid')
    except (ValueError, TypeError, AttributeError):
        raise ValueError('confirmation_time_invalid') from None
    attestation = value.get('authorAttestation')
    require(_text(attestation) and len(attestation.strip()) >= 20
            and any(mark in attestation for mark in ('.', '。', '!', '！'))
            and all(re.search(pattern, attestation, re.I) for pattern in (
                r'\bI\b|\bauthor\b|我|作者', r'original|原创', r'official|官方',
                r'text|原文|文字', r'picture|image|图片', r'question|题目', r'layout|布局|版式',
                r'\bno\b|\bnot\b|没有|未', r'reproduc|复制|复刻|照搬')), 'attestation_missing')
    # The author supplies the sentence; this is not an originality detector.
    return deepcopy(value)


def _evidence(inputs, speech, questions):
    notes, verification, receipt = (inputs.get(key) for key in ('notes', 'verification', 'receipt'))
    require(isinstance(notes, dict), 'notes_invalid')
    resources = notes.get('resources', {})
    require(isinstance(resources, dict), 'notes_invalid')
    for name in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise'):
        item = resources.get(name, {})
        require(isinstance(item, dict) and isinstance(item.get('findings'), list)
                and bool(item['findings']) and all(_text(v) for v in item['findings'])
                and isinstance(item.get('pageRefs'), list) and bool(item['pageRefs'])
                and all(_text(v) or type(v) is int and v > 0 for v in item['pageRefs']), 'notes_invalid')
    require(isinstance(inputs.get('brief'), dict) and bool(inputs['brief']), 'brief_missing')
    body_sha = digest(inputs['body'])
    require(isinstance(verification, dict) and verification.get('bodySha256') == body_sha
            and verification.get('disagreements') == []
            and type(verification.get('speechChecked')) is int and verification['speechChecked'] >= len(speech)
            and type(verification.get('questionsChecked')) is int and verification['questionsChecked'] >= len(questions),
            'verification_invalid')
    _independent_verifier(inputs['identity'].get('authorModels'), verification.get('verifier'))
    require(isinstance(receipt, dict) and receipt.get('bodySha256') == body_sha and receipt.get('ok') is True
            and isinstance(receipt.get('viewports'), list)
            and all(v in receipt['viewports'] for v in ('1280x720', '1000x563', '640x360')), 'audit_invalid')
    require(isinstance(inputs.get('roster'), dict) and bool(inputs['roster']), 'roster_missing')
    issues = inputs.get('gateIssues')
    require(isinstance(issues, list) and not any(i.get('severity') == 'error' for i in issues), 'gates_failed')
    return {name: digest(inputs[key]) for name, key in (
        ('notesSha256', 'notes'), ('briefSha256', 'brief'), ('receiptSha256', 'receipt'),
        ('verificationSha256', 'verification'))}


def _review(evidence, confirmation, author_models, verifier_model):
    return {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
        'publicationAuthorized': True, 'reviewer': 'owner (quoted) + automated gates G0-G7',
        'basis': ('Independent AI verification (not a human review), sha256 %s, covers every speech action and question. '
            'Author models: %s; verifier model: %s. '
            'Official notes passed G0, sha256 %s. Author attestation (not an independent originality check): %s '
            'Owner authorization: %s; confirmedAt %s. Browser audit receipt sha256 %s; brief sha256 %s.' % (
                evidence['verificationSha256'], canonical(author_models), canonical(verifier_model),
                evidence['notesSha256'], canonical(confirmation['authorAttestation']),
                canonical(confirmation['userQuote']), confirmation['confirmedAt'], evidence['receiptSha256'], evidence['briefSha256']))}


def build_release(inputs):
    identity, manifest, body = (inputs[key] for key in ('identity', 'manifest', 'body'))
    require(all(_text(identity.get(k)) for k in ('title', 'objective', 'teacherCode'))
            and identifier(identity.get('teachingRevision')), 'identity_invalid')
    require(type(identity.get('estimatedMinutes')) is int and 5 <= identity['estimatedMinutes'] <= 120,
            'estimated_minutes_invalid')
    require(identity.get('editionId') == manifest.get('editionId')
            and identity.get('revisionId') == manifest.get('revisionId'), 'manifest_mismatch')
    try:
        _, node = lesson_by_id(manifest, identity.get('nodeId'))
    except ApiError:
        raise ValueError('node_missing') from None
    source_id = body.get('stage', {}).get('id')
    require(isinstance(source_id, str) and re.fullmatch(r'[A-Za-z0-9_-]+', source_id)
            and body.get('id', source_id) == source_id and bool(body.get('scenes'))
            and body['stage'].get('name') == identity['title'], 'classroom_invalid')
    try:
        questions = check_questions(body)
    except (ApiError, KeyError, TypeError):
        raise ValueError('questions_invalid') from None
    require(all(_text(q.get('skill')) for q in questions), 'questions_invalid')
    speech = [a for s in body['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
    require(bool(speech), 'speech_missing')
    confirmation = _confirmation(inputs.get('confirmation'))
    evidence = _evidence(inputs, speech, questions)
    # The registered catalog stays as it is (its brief may still be a draft); the lesson's own goals come from the reviewed notes.
    objectives = inputs['notes'].get('objectives')
    require(isinstance(objectives, list) and bool(objectives) and all(_text(v) for v in objectives), 'objectives_invalid')
    raw_media = inputs.get('media', {})
    require(isinstance(raw_media, dict) and bool(raw_media), 'media_missing')
    assets = {}
    for name, raw in sorted(raw_media.items()):
        require(isinstance(name, str) and PurePosixPath(name).name == name
                and isinstance(raw, bytes), 'media_invalid')
        suffix = PurePosixPath(name).suffix.lower()
        sha = hashlib.sha256(raw).hexdigest()
        filename_hash = re.search(r'([a-fA-F0-9]{64})\.[^.]+$', name)
        require(filename_hash is not None and filename_hash.group(1).lower() == sha, 'media_hash_mismatch')
        try:
            mime = media_mime_type(suffix, raw)
        except ApiError:
            raise ValueError('media_invalid') from None
        assets[name] = {'sha256': sha, 'byteSize': len(raw), 'mimeType': mime,
                        'relative': ('audio/' if mime.startswith('audio/') else 'media/') + sha + suffix}
    referenced = set()

    def asset(match):
        require(match.group(1) == source_id and not match.group(0).startswith('http'), 'media_reference_invalid')
        name = match.group(2).split('/', 1)[1]
        require(name in assets, 'media_missing')
        referenced.add(name)
        return assets[name]

    def scan(value):
        if isinstance(value, dict):
            for item in value.values():
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)
        elif isinstance(value, str):
            for match in MEDIA.finditer(value):
                asset(match)
            require('/api/classroom-media/' not in MEDIA.sub('', value), 'media_reference_invalid')
            require(not re.search(r'(?:https?://|data:|file:|blob:)', NAMESPACE.sub('', value)), 'external_media')
    scan(body)
    require(referenced == set(assets), 'media_unreferenced')
    for url in [a.get('audioUrl') for a in speech] + [q.get('questionAudioUrl') for q in questions]:
        match = MEDIA.fullmatch(url or '')
        require(match is not None and asset(match)['mimeType'].startswith('audio/'), 'audio_invalid')
    binding = {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
        'alignmentManifestSha256': digest(manifest), 'nodeId': identity['nodeId'],
        'partIndex': 1, 'teachingRevision': identity['teachingRevision']}
    frozen = {'schemaVersion': INPUT_SCHEMA, 'textbookBinding': binding,
        'knowledgeBrief': deepcopy(node['brief']), 'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'],
        'sourceSha256': digest(body), 'identity': {k: deepcopy(identity[k]) for k in (
            'editionId', 'revisionId', 'nodeId', 'teachingRevision', 'title', 'objective', 'teacherCode',
            'authorModels', 'estimatedMinutes')},
        'verifier': deepcopy(inputs['verification']['verifier']),
        'media': [{'sourceName': name, **entry} for name, entry in sorted(assets.items())],
        'rosterSha256': digest(inputs['roster']), 'authorAttestation': confirmation['authorAttestation'],
        'coursewareLight': {'schemaVersion': LIGHT_SCHEMA,
            'source': {'stageId': source_id, 'bodySha256': digest(body)},
            'gates': {gate: {'passed': True, 'warnings': sorted({issue['code'] for issue in inputs['gateIssues']
                if issue.get('gate') == gate and issue.get('severity') == 'warn'})} for gate in GATES},
            'confirmation': {k: confirmation[k] for k in ('userQuote', 'confirmedAt', 'confirmedBy')},
            'evidence': evidence}}
    key = digest(frozen)
    frozen['contentKey'] = key
    classroom_id = 'tbpub_' + key[:24]

    def convert(value):
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str):
            return classroom_id if value == source_id else MEDIA.sub(
                lambda match: '/api/classroom-media/' + classroom_id + '/' + asset(match)['relative'], value)
        return value
    classroom = convert(body)
    classroom['id'] = classroom_id
    for scene in classroom['scenes']:
        scene['stageId'] = classroom_id
    inventory = sorted({entry['relative']: {'path': '/api/classroom-media/' + classroom_id + '/' + entry['relative'],
        **{k: entry[k] for k in ('sha256', 'byteSize', 'mimeType')}} for entry in assets.values()}.values(),
        key=lambda entry: entry['path'])
    release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': key, 'classroomId': classroom_id,
        'classroom': classroom, 'classroomSha256': digest(classroom), 'media': inventory,
        'audioAudit': {'passed': True, 'segments': len(speech), 'method': AUDIO_METHOD}}
    release['sha256'] = digest(release)
    review = {**_review(evidence, confirmation, identity['authorModels'], inputs['verification']['verifier']['model']),
        'release': release}
    content = {'schemaVersion': 'mira.learning.fixed-textbook-course.v1', 'textbookBinding': binding,
        'title': identity['title'], 'objectives': objectives, 'estimatedMinutes': identity['estimatedMinutes'],
        'questions': [{'id': q['id'], 'type': 'single_choice', 'prompt': q['question'],
            'choices': [{'id': o['value'], 'text': o['label']} for o in q['options']],
            'answer': q['answer'][0] if isinstance(q['answer'], list) else q['answer'],
            'explanation': q['analysis'], 'skill': q['skill']} for q in questions], 'releaseSha256': release['sha256']}
    course = {'id': 'textbook_' + key[:40], 'version': identity['teachingRevision'],
        'grade_code': manifest['gradeCode'], 'subject': manifest['subject'],
        'node_code': 'textbook:%s:%s' % (manifest['editionId'], identity['nodeId']),
        'title': identity['title'], 'objective': identity['objective'], 'content_json': canonical(content),
        'status': 'published', 'quality_status': 'released', 'retired_at': None, 'content_origin': 'openmaic_generated'}
    prepared = {'frozen': frozen, 'release': release, 'review': review, 'course': course,
        'content_json': content, 'media': inventory, 'classroom': classroom, 'manifest': deepcopy(manifest)}
    errors = validate_light_release(prepared, manifest)
    require(not errors, errors[0] if errors else 'release_invalid')
    return prepared


def validate_light_release(prepared, manifest):
    """Use the unchanged student validator as the final release authority."""
    try:
        frozen, course = prepared['frozen'], prepared['course']
        light = frozen['coursewareLight']
        confirmation = _confirmation({**light['confirmation'], 'authorAttestation': frozen['authorAttestation']})
        verifier_model = _independent_verifier(frozen['identity'].get('authorModels'), frozen.get('verifier'))
        require(light['schemaVersion'] == LIGHT_SCHEMA and set(light) == {
            'schemaVersion', 'source', 'gates', 'confirmation', 'evidence'}
            and set(light['confirmation']) == {'userQuote', 'confirmedAt', 'confirmedBy'}
            and set(light['evidence']) == {'notesSha256', 'briefSha256', 'receiptSha256', 'verificationSha256'}
            and all(isinstance(sha, str) and re.fullmatch(r'[a-f0-9]{64}', sha) for sha in light['evidence'].values())
            and set(light['source']) == {'stageId', 'bodySha256'}
            and isinstance(light['source']['stageId'], str)
            and re.fullmatch(r'[A-Za-z0-9_-]+', light['source']['stageId'])
            and isinstance(frozen['sourceSha256'], str) and re.fullmatch(r'[a-f0-9]{64}', frozen['sourceSha256'])
            and light['source']['bodySha256'] == frozen['sourceSha256']
            and set(light['gates']) == set(GATES)
            and all(light['gates'][gate]['passed'] is True for gate in GATES)
            and {k: v for k, v in prepared['review'].items() if k != 'release'} == _review(
                light['evidence'], confirmation, frozen['identity']['authorModels'], verifier_model),
            'release_invalid')
        binding = frozen['textbookBinding']
        build = {'status': 'published', 'content_key': frozen['contentKey'], 'node_id': binding['nodeId'],
            'part_index': 1, 'teaching_revision': binding['teachingRevision'], 'input_json': canonical(frozen),
            'review_json': canonical(prepared['review']), 'course_id': course['id'], 'course_version': course['version'],
            'course_content_sha256': digest(prepared['content_json'])}
        result = validate_release(build, manifest, course)
        if result is None or result != prepared['release'] or result['sha256'] != prepared['content_json']['releaseSha256']:
            return ['release_invalid']
    except (ApiError, KeyError, TypeError, ValueError):
        return ['release_invalid']
    return []
