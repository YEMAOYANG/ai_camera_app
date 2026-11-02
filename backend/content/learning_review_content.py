"""Immutable, lesson-bound review sources and original picture-question packs."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import re


SOURCE_SCHEMA = 'mira.learning.review-source.v1'
PACK_SCHEMA = 'mira.learning.review-pack.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
MEDIA_TOKEN = re.compile(r'reviewpack\.([a-f0-9]{64})\.(png|jpg|webp|wav|mp3)\Z')
MIMES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
         'audio/wav': 'wav', 'audio/mpeg': 'mp3', 'application/pdf': 'pdf', 'text/plain': 'txt'}
MODES = {'listening_picture', 'character_picture', 'pinyin_picture', 'picture_comprehension'}


class ReviewContentError(ValueError):
    """Diagnostics never include provider responses, private paths or secrets."""


def require(condition, code):
    if not condition:
        raise ReviewContentError(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, maximum=8000):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def texts(value):
    return isinstance(value, list) and 0 < len(value) <= 40 and all(text(x) for x in value)


def validate_source(value):
    require(isinstance(value, dict) and value.get('schemaVersion') == SOURCE_SCHEMA, 'review_source_invalid')
    binding, identity = value.get('binding'), value.get('sourceIdentity')
    require(isinstance(binding, dict) and all(text(binding.get(k), 255) for k in
        ('editionId', 'revisionId', 'nodeId', 'gradeCode', 'subject', 'volume')), 'review_source_binding_invalid')
    require(binding['subject'] in {'chinese', 'math', 'english', 'science'}
        and re.fullmatch(r'primary_[1-6]', binding['gradeCode']), 'review_source_binding_invalid')
    require(isinstance(identity, dict) and all(text(identity.get(k), 255) for k in
        ('courseId', 'courseVersion', 'contentKey', 'releaseSha256', 'title'))
        and SHA.fullmatch(identity['releaseSha256']), 'review_release_identity_invalid')
    official = value.get('officialExercise')
    require(isinstance(official, dict) and all(text(official.get(k)) for k in
        ('path', 'sha256', 'sourceUrl', 'reviewer', 'reviewedAt', 'exerciseText'))
        and SHA.fullmatch(official['sha256']) and texts(official.get('locations'))
        and texts(official.get('findings')), 'review_official_exercise_incomplete')
    require(official.get('sourceKind') in {'reviewed-official-assignment-record', 'official-downloaded-file'},
        'review_official_source_kind_required')
    if official['sourceKind'] == 'reviewed-official-assignment-record':
        require(official.get('originalFileDownloaded') is False, 'review_official_download_claim_invalid')
    else:
        require(official.get('originalFileDownloaded') is True, 'review_official_download_claim_invalid')
    reviewed_at(official['reviewedAt'])
    from content.textbook_official_resource_review import _official_url
    _official_url(official['sourceUrl'])
    for reference in official.get('references', []):
        require(isinstance(reference, dict) and text(reference.get('classHourId'))
            and texts(reference.get('locations')) and texts(reference.get('findings')),
            'review_official_reference_invalid')
        _official_url(reference.get('sourceUrl'))
    scope = value.get('originalScope')
    require(isinstance(scope, dict) and texts(scope.get('allowed')) and texts(scope.get('excluded')),
        'review_original_scope_required')
    objectives = value.get('objectives')
    require(isinstance(objectives, list) and 0 < len(objectives) <= 40, 'review_objectives_required')
    ids = set()
    for objective in objectives:
        require(isinstance(objective, dict) and text(objective.get('id'), 128)
            and objective['id'] not in ids and all(text(objective.get(k), 255) for k in
                ('label', 'knowledgeId')), 'review_objective_invalid')
        if 'targetTexts' in objective:
            require(texts(objective['targetTexts']) and all(len(t) <= 24 for t in objective['targetTexts']),
                'review_target_texts_invalid')
        ids.add(objective['id'])
    media = value.get('media')
    require(isinstance(media, list) and 1 <= len(media) <= 200, 'review_source_media_required')
    asset_ids = set()
    for asset in media:
        validate_media(asset)
        require(asset['id'] not in asset_ids, 'review_media_duplicate')
        asset_ids.add(asset['id'])
    return value


def reviewed_at(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(stamp.tzinfo is not None, 'review_timestamp_invalid')
        return stamp
    except (ValueError, TypeError, AttributeError):
        raise ReviewContentError('review_timestamp_invalid') from None


def validate_media(asset):
    require(isinstance(asset, dict) and text(asset.get('id'), 128)
        and ID.fullmatch(asset['id']) and text(asset.get('path'))
        and SHA.fullmatch(str(asset.get('sha256', '')))
        and asset.get('mimeType') in MIMES and text(asset.get('meaning')),
        'review_media_invalid')
    return asset


def validate_questions(questions, source):
    require(isinstance(questions, list) and 1 <= len(questions) <= 30, 'review_questions_invalid')
    goals = {x['id']: x for x in source['objectives']}
    pictures = {x['id'] for x in source['media'] if x['mimeType'].startswith('image/')}
    ids, fingerprints = set(), set()
    result = []
    for raw in questions:
        q = deepcopy(raw)
        require(isinstance(q, dict) and text(q.get('id'), 128) and ID.fullmatch(q['id'])
            and q['id'] not in ids and q.get('targetId') in goals, 'review_question_identity_invalid')
        require(text(q.get('prompt'), 2000) and text(q.get('explanation'), 3000)
            and texts(q.get('hints')) and len(q['hints']) <= 3
            and q.get('assessmentMode') in MODES and q.get('visualAssetId') in pictures,
            'review_question_presentation_invalid')
        require(type(q.get('estimatedSeconds')) is int and 15 <= q['estimatedSeconds'] <= 300,
            'review_question_duration_invalid')
        claim = q.get('evidenceClaim')
        require(isinstance(claim, dict) and texts(claim.get('observed'))
            and texts(claim.get('supports')) and texts(claim.get('doesNotSupport')),
            'review_evidence_claim_required')
        if q['assessmentMode'] in {'character_picture', 'pinyin_picture'}:
            require(text(q.get('targetText'), 24) and q['targetText'] in goals[q['targetId']].get('targetTexts', [])
                and q['targetText'] not in q['prompt'], 'review_target_narration_must_be_separate')
        options = q.get('options')
        require(isinstance(options, list) and 2 <= len(options) <= 4, 'review_picture_options_required')
        values, option_pictures = [], []
        for option in options:
            require(isinstance(option, dict) and text(option.get('value'), 16)
                and text(option.get('label'), 100) and option.get('pictureAssetId') in pictures,
                'review_picture_option_invalid')
            values.append(option['value']); option_pictures.append(option['pictureAssetId'])
        require(len(set(values)) == len(values) and len(set(option_pictures)) == len(option_pictures)
            and q.get('correctAnswer') in values, 'review_answer_invalid')
        # The answer key is never part of the public picture/narration contract.
        require(not any(k in option for option in options for k in ('correct', 'selected', 'highlight')),
            'review_answer_leaked')
        image_hashes = {a['id']: a['sha256'] for a in source['media'] if a['id'] in pictures}
        option_hashes = [image_hashes[p] for p in option_pictures]
        require(len(set(option_hashes)) == len(option_hashes)
            and image_hashes[q['visualAssetId']] not in option_hashes,
            'review_picture_match_shortcut')
        correct_image = next(o['pictureAssetId'] for o in options if o['value'] == q['correctAnswer'])
        fingerprint = digest({'knowledgeId': goals[q['targetId']]['knowledgeId'], 'prompt': q['prompt'],
            'targetText': q.get('targetText'),
            'options': sorted(image_hashes[o['pictureAssetId']] for o in options),
            'answerPicture': image_hashes[correct_image]})
        require(fingerprint not in fingerprints, 'review_question_duplicate')
        ids.add(q['id']); fingerprints.add(fingerprint)
        q['fingerprint'] = fingerprint
        result.append(q)
    return result


def media_token(asset):
    validate_media(asset)
    require(asset['mimeType'].split('/')[0] in {'image', 'audio'}, 'review_media_not_playable')
    return 'reviewpack.' + asset['sha256'] + '.' + MIMES[asset['mimeType']]


def public_question(q, source, assets, pack_sha):
    objective = next(x for x in source['objectives'] if x['id'] == q['targetId'])
    by_id = {a['id']: a for a in assets}
    def image(asset_id):
        a = by_id[asset_id]
        return {'src': media_token(a), 'alt': a['meaning']}
    def audio(spoken):
        found = [a for a in assets if a['mimeType'].startswith('audio/') and a.get('text') == spoken]
        require(len(found) == 1, 'review_exact_teacher_audio_missing')
        return media_token(found[0])
    identity, b = source['sourceIdentity'], source['binding']
    return {'id': q['id'], 'version': pack_sha, 'renderer': 'picture_choices',
        'subject': b['subject'], 'gradeCode': b['gradeCode'], 'knowledgeId': objective['knowledgeId'],
        'knowledgeLabel': objective['label'], 'targetId': q['targetId'],
        'courseId': identity['courseId'], 'courseVersion': identity['courseVersion'], 'courseTitle': identity['title'],
        'sourceIdentity': deepcopy(identity), 'prompt': q['prompt'],
        'visual': {'art': image(q['visualAssetId'])},
        'options': [{'value': o['value'], 'label': o['label'], 'picture': image(o['pictureAssetId'])} for o in q['options']],
        'correctAnswer': q['correctAnswer'], 'hints': q['hints'], 'explanation': q['explanation'],
        'promptAudioAsset': audio(q['prompt']), 'hintAudioAssets': [audio(t) for t in q['hints']],
        'explanationAudioAsset': audio(q['explanation']), 'estimatedSeconds': q['estimatedSeconds'],
        'assessmentMode': q['assessmentMode'], 'evidenceClaim': deepcopy(q['evidenceClaim']),
        **({'target': q['targetText']} if q.get('targetText') else {}),
        'packSha256': pack_sha, 'fingerprint': q['fingerprint'], 'approved': True, 'private': False}
