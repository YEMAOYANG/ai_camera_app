"""Verify an existing frozen authorization without creating a new exception.

The operator must read the authentic conversation. Hashes only bind that
attestation to the original job and the current candidate; they do not prove
consent, source viewing, play, audio quality, or publication acceptance.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path

from content.textbook_catalog import digest

SCHEMA = 'mira.textbook.frozen-review-authorization.v1'
FIELDS = {'schemaVersion', 'status', 'verification', 'binding', 'teachingRevision',
          'classHourIds', 'authorization', 'originals', 'currentNative',
          'originalReview', 'unchangedEvidence', 'evidenceBoundaries', 'sha256'}


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('authorization time must have an offset')
    return result


def validate_record(record, operator, native_source):
    from content.textbook_official_followup import verify_operator_attestation
    from content.textbook_official_resource_review import validate_official_resource_review

    if (not isinstance(record, dict) or set(record) != FIELDS
            or record.get('schemaVersion') != SCHEMA
            or record.get('status') != 'original_authorization_verified_for_current_candidate'
            or record.get('verification') != 'authorization_record_only_not_play_audio_or_publication'
            or digest({k: v for k, v in record.items() if k != 'sha256'}) != record.get('sha256')
            or not isinstance(record.get('evidenceBoundaries'), list) or not record['evidenceBoundaries']):
        raise ValueError('original authorization seal is invalid')
    auth = record['authorization']
    verify_operator_attestation(auth, operator)
    if any(auth.get(k) != record[k] for k in ('binding', 'teachingRevision', 'classHourIds')):
        raise ValueError('operator did not verify the exact frozen scope')
    review = record['originalReview']
    validate_official_resource_review(review, record['binding'])
    exceptions = review.get('reviewExceptions', [])
    if (len(exceptions) != 1 or exceptions[0].get('resourceType') != 'video'
            or exceptions[0].get('classHourIds') != record['classHourIds']
            or exceptions[0].get('userInstruction') != auth.get('answer')
            or record['unchangedEvidence'].get('originalReviewSha256') != digest(review)):
        raise ValueError('attestation cannot introduce or expand a frozen exception')
    old_scope = exceptions[0].get('binding', {})
    if any(old_scope.get(k) != v for k, v in record['binding'].items() if k != 'teachingRevision'):
        raise ValueError('frozen exception belongs to another lesson')
    # Historical recordedAt may be later than the real message. Preserve it;
    # bind the verified message time separately, always before original POST.
    if not (_time(auth['authorizedAt']) <= _time(exceptions[0]['authorizedAt'])
            <= _time(record['originals']['dispatchCreatedAt'])):
        raise ValueError('this path only verifies an existing pre-dispatch authorization')
    expected = {'sessionId': native_source['sessionId'], 'stageId': native_source['stageId'],
                'documentSha256': native_source['nativeDocumentSha256'],
                'authoringSourceSha256': native_source['authoringSourceSha256'],
                'candidateSha256': native_source['candidateSha256'],
                'candidateFileSha256': native_source['candidateFileSha256'],
                'completeSceneReviewFollowupSha256': native_source['followupSha256']}
    if record['currentNative'] != expected:
        raise ValueError('original authorization is not bound to the current candidate')


def validate_original_authorization(path, raw, record, operator, *, job, frozen,
                                    draft, dispatch, native_proof, followup):
    from content.textbook_review_followup import _read
    from content.textbook_official_resource_review import validate_new_course_post_class_practice

    project = Path(__file__).resolve().parents[2]
    job = Path(job).resolve()
    course = job.parent
    source = {**native_proof, 'followupSha256': followup['sha256']}
    validate_record(record, operator, source)
    if (record['binding'] != frozen['binding']
            or record['teachingRevision'] != str(frozen['teachingRevision'])
            or record['originalReview'] != draft['scopeReview']['officialResourceReview']
            or record['originals']['dispatchCreatedAt'] != dispatch['createdAt']):
        raise ValueError('frozen source or scope changed')

    def read_ref(meta, exact):
        ref = Path(meta['path'])
        if not ref.is_absolute():
            ref = project / ref
        if ref.resolve() != exact.resolve():
            raise ValueError('original evidence path changed')
        value, data = _read(ref, course)
        if hashlib.sha256(data).hexdigest() != meta['sha256'] or len(data) != meta['byteSize']:
            raise ValueError('original evidence bytes changed')
        return value, data

    refs = record['originals']
    for key, expected in (('frozen', frozen), ('draft', draft), ('dispatch', dispatch)):
        value, _ = read_ref(refs[key], job / f'{key}.json')
        if value != expected:
            raise ValueError('original job changed')
    _, source_draft = read_ref(refs['sourceDraft'], course / 'source-input/request-draft.json')
    _, frozen_draft = read_ref(refs['draft'], job / 'draft.json')
    if source_draft != frozen_draft:
        raise ValueError('original source draft changed')
    unchanged = record['unchangedEvidence']
    review_path = Path(unchanged['originalReviewFile']['path'])
    if not review_path.is_absolute():
        review_path = project / review_path
    review, _ = read_ref(unchanged['originalReviewFile'], review_path)
    if review != record['originalReview']:
        raise ValueError('original source review changed')
    post = draft['scopeReview']['postClassPractice']
    post_path = Path(post.get('sourcePath', unchanged['postClassPracticeSource']['path']))
    if not post_path.is_absolute():
        post_path = project / post_path
    if ('sourcePath' not in post and
            (post.get('sourceKind') != 'official-inventory-absence'
             or not post_path.resolve().is_relative_to(course / 'source-input'))):
        raise ValueError('legacy absence evidence must remain in the original source directory')
    read_ref(unchanged['postClassPracticeSource'], post_path)
    if (unchanged['postClassPracticeSource']['sha256'] != post['sourceSha256']
            or post['officialResourceReviewSha256'] != digest(review)):
        raise ValueError('post-class evidence changed')
    validate_new_course_post_class_practice(draft)
    return {'schemaVersion': 'mira.textbook.operator-verified-official-followup.v1',
            'followupPath': str(Path(path).resolve()), 'followupSha256': record['sha256'],
            'followupFileSha256': hashlib.sha256(raw).hexdigest(),
            'effectiveReviewSha256': digest(review), 'operatorAttestation': deepcopy(operator),
            'followup': deepcopy(record),
            'verification': 'operator_checked_conversation_hashes_do_not_authenticate_human',
            'authorizationIsPostDispatch': False, 'newDispatchAllowed': False}


def validate_frozen_original(value, native_source):
    fields = {'schemaVersion', 'followupPath', 'followupSha256', 'followupFileSha256',
              'effectiveReviewSha256', 'operatorAttestation', 'followup', 'verification',
              'authorizationIsPostDispatch', 'newDispatchAllowed'}
    import re
    if (not isinstance(value, dict) or set(value) != fields
            or value.get('schemaVersion') != 'mira.textbook.operator-verified-official-followup.v1'
            or value.get('authorizationIsPostDispatch') is not False
            or value.get('newDispatchAllowed') is not False
            or value.get('verification') != 'operator_checked_conversation_hashes_do_not_authenticate_human'
            or not isinstance(value.get('followupPath'), str)
            or re.fullmatch(r'[a-f0-9]{64}', str(value.get('followupFileSha256'))) is None):
        raise ValueError('frozen original authorization is invalid')
    record = value['followup']
    validate_record(record, value['operatorAttestation'], native_source)
    if (value['followupSha256'] != record['sha256']
            or value['effectiveReviewSha256'] != digest(record['originalReview'])):
        raise ValueError('frozen original review changed')
