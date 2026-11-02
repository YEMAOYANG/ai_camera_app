"""Operator-verified post-dispatch source review follow-ups.

Hashes validate artifact identity, not human consent. The caller must separately
read the authentic conversation and supply the exact decision as an operator
attestation; the module cannot authenticate the conversation or its author.
"""
from copy import deepcopy
from datetime import datetime, timezone
import re
from uuid import UUID

from content.textbook_catalog import digest

KINDS = ('courseware', 'teachingDesign', 'learningTaskSheet', 'afterClassExercise')


def requires_official_followup(draft):
    """Require explicit selection for any revised v4 course with a video waiver."""
    review = draft.get('scopeReview', {}).get('officialResourceReview', {})
    hours = review.get('classHours', []) if isinstance(review, dict) else []
    return any(isinstance(hour, dict)
               and hour.get('resources', {}).get('video', {}).get('status') == 'waived_unavailable'
               for hour in hours)


def verify_operator_attestation(authorization, operator):
    fields = {'question', 'answer', 'userMessageId', 'reviewer', 'basis'}
    if (not isinstance(operator, dict) or set(operator) != fields
            or not all(isinstance(operator[k], str) and operator[k].strip() == operator[k] and operator[k] for k in fields)
            or not isinstance(authorization, dict)
            or any(operator[k] != authorization.get(k) for k in ('question', 'answer', 'userMessageId'))
            or authorization.get('resourceType') != 'video' or authorization.get('authorizedBy') != 'user'
            or authorization.get('timeSource') != 'uuidv7_message_id_timestamp_not_server_signed'):
        raise ValueError('operator must verify the exact actual conversation')
    try:
        value = UUID(operator['userMessageId'])
        timestamp = datetime.fromtimestamp((value.int >> 80) / 1000, timezone.utc)
        at = datetime.fromisoformat(authorization['authorizedAt'].replace('Z', '+00:00'))
        recorded = datetime.fromisoformat(authorization['recordedAt'].replace('Z', '+00:00'))
        if value.version != 7 or at.tzinfo is None or recorded.tzinfo is None or at.astimezone(timezone.utc) != timestamp or recorded < at:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError('operator authorization time or message identity differs') from None


def validate_effective_review(original, effective, class_hour_ids, nonvideo_sha):
    if (not isinstance(original, dict) or not isinstance(effective, dict) or class_hour_ids != ['lesson_1']
            or len(original.get('classHours', [])) != 1 or len(effective.get('classHours', [])) != 1
            or original['classHours'][0].get('classHourId') != 'lesson_1'
            or effective['classHours'][0].get('classHourId') != 'lesson_1'):
        raise ValueError('follow-up must match the original single hour')
    old_resources = original['classHours'][0]['resources']; new_resources = effective['classHours'][0]['resources']
    old_nonvideo = {key: old_resources[key] for key in KINDS}
    if (old_nonvideo != {key: new_resources[key] for key in KINDS}
            or nonvideo_sha not in (digest(old_nonvideo), digest({'lesson_1': old_nonvideo}))
            or any(old_nonvideo[key].get('status') != 'reviewed' for key in KINDS)):
        raise ValueError('non-video evidence changed or was not reviewed')
    before_video, after_video = old_resources['video'], new_resources['video']
    for field, allowed in (('findings', ('视频', '例外', '授权')),
                           ('reviewAssignmentHistory', ())):
        before, after = before_video.get(field), after_video.get(field)
        if before == after:
            continue
        if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
            raise ValueError('video evidence history changed')
        for a, b in zip(before, after):
            if a == b:
                continue
            if field == 'findings':
                if not isinstance(a, str) or not isinstance(b, str) or not any(k in a for k in allowed) or not any(k in b for k in allowed):
                    raise ValueError('unrelated video finding changed')
            else:
                if not isinstance(a, dict) or not isinstance(b, dict):
                    raise ValueError('video review history is invalid')
                mutable = {'status', 'reviewBoundary', 'supersededAt'}
                if ({k: v for k, v in a.items() if k not in mutable}
                        != {k: v for k, v in b.items() if k not in mutable}):
                    raise ValueError('historical video review evidence changed')
    before_boundaries = original.get('adaptation', {}).get('evidenceBoundaries')
    after_boundaries = effective.get('adaptation', {}).get('evidenceBoundaries')
    if before_boundaries != after_boundaries:
        if (not isinstance(before_boundaries, list) or not isinstance(after_boundaries, list)
                or len(before_boundaries) != len(after_boundaries)
                or any(a != b and (not isinstance(a, str) or not isinstance(b, str)
                                    or '视频' not in a or '视频' not in b)
                       for a, b in zip(before_boundaries, after_boundaries))):
            raise ValueError('unrelated evidence boundary changed')
    old, new = deepcopy(original), deepcopy(effective)
    for value in (old, new):
        for key in ('readiness', 'readinessReason', 'reviewBoundary', 'updatedAt', 'authorizationRecordedAt', 'reviewExceptions'):
            value.pop(key, None)
        value.get('adaptation', {}).pop('evidenceBoundaries', None)
        video = value['classHours'][0]['resources']['video']
        for key in ('method', 'findings', 'reviewAssignmentHistory'):
            video.pop(key, None)
    if old != new or old['classHours'][0]['resources']['video'].get('status') != 'waived_unavailable':
        raise ValueError('unrelated official evidence changed')


def validate_followup(path, expected_sha, operator, *, job, frozen, draft, dispatch, native_proof, followup):
    """Validate the selected immutable record and its evidence, never authenticate a user.

    The caller is responsible for checking the authentic conversation before
    providing ``operator``. On-disk JSON, UUIDs and hashes cannot prove consent.
    """
    import hashlib
    import json
    from pathlib import Path
    from content.textbook_authoring_candidate import _safe_child
    from content.textbook_official_resource_review import (validate_official_resource_review,
                                                            validate_new_course_post_class_practice)
    from content.textbook_review_followup import _read
    from services.course_file_store import course_bytes

    project = Path(__file__).resolve().parents[2]
    job = Path(job).resolve(); course = job.parent
    if not isinstance(expected_sha, str) or re.fullmatch(r'[a-f0-9]{64}', expected_sha) is None:
        raise ValueError('a specific reviewed follow-up digest is required')
    expected_path = course / 'review-followups/official-video-exception' / expected_sha / 'review-followup.json'
    path = Path(path)
    if not path.is_absolute(): path = project / path
    _safe_child(course, path)
    if path.resolve() != expected_path.resolve():
        raise ValueError('follow-up must be the exact managed digest path')
    record, raw = _read(path, course)
    from content.textbook_original_review_authorization import SCHEMA as ORIGINAL_AUTH_SCHEMA
    if record.get('schemaVersion') == ORIGINAL_AUTH_SCHEMA:
        if record.get('sha256') != expected_sha:
            raise ValueError('selected original authorization digest differs')
        from content.textbook_original_review_authorization import validate_original_authorization
        return validate_original_authorization(path, raw, record, operator, job=job, frozen=frozen,
            draft=draft, dispatch=dispatch, native_proof=native_proof, followup=followup)
    fields = {'schemaVersion','status','verification','binding','teachingRevision','classHourIds','authorization',
              'originals','currentNative','priorReview','effectiveReview','unchangedEvidence','evidenceBoundaries','sha256'}
    if (set(record) not in (fields, fields | {'supersedesFollowup'}) or record.get('schemaVersion') != 'mira.textbook.official-resource-review-followup.v1'
            or record.get('status') != 'authorized_for_current_review_followup'
            or record.get('verification') != 'authorization_record_only_not_play_audio_or_publication'
            or record.get('sha256') != expected_sha
            or digest({k:v for k,v in record.items() if k != 'sha256'}) != expected_sha
            or record.get('binding') != frozen.get('binding')
            or record.get('teachingRevision') != str(frozen.get('teachingRevision'))
            or record.get('classHourIds') != ['lesson_1']):
        raise ValueError('follow-up seal or lesson identity differs')
    verify_operator_attestation(record.get('authorization'), operator)
    auth = record['authorization']
    if (datetime.fromisoformat(auth['authorizedAt'].replace('Z','+00:00'))
            <= datetime.fromisoformat(dispatch['createdAt'].replace('Z','+00:00'))):
        raise ValueError('post-dispatch follow-up cannot predate the dispatch')
    refs = record['originals']
    def path_for(value):
        value = Path(value)
        if not value.is_absolute(): value = project / value
        _safe_child(course, value)
        return value
    def read_ref(meta, exact=None):
        if not isinstance(meta, dict) or not isinstance(meta.get('path'), str):
            raise ValueError('source evidence reference missing')
        value = path_for(meta['path'])
        if exact is not None and value.resolve() != exact.resolve():
            raise ValueError('source evidence path differs')
        data = course_bytes(value)
        if hashlib.sha256(data).hexdigest() != meta.get('sha256') or ('byteSize' in meta and len(data) != meta['byteSize']):
            raise ValueError('source evidence bytes changed')
        return data
    if path_for(refs['jobDir']).resolve() != job:
        raise ValueError('source job differs')
    for key, filename in (('frozen','frozen.json'),('draft','draft.json'),('dispatch','dispatch.json')):
        read_ref(refs[key], job / filename)
    if read_ref(refs['sourceDraft'], course/'source-input/request-draft.json') != course_bytes(job/'draft.json'):
        raise ValueError('source draft differs')
    if (refs.get('requestSha256') != dispatch.get('requestSha256')
            or ('sourceRequestSha256' in refs and refs['sourceRequestSha256'] != frozen.get('requestSha256'))
            or refs.get('sceneContractSha256') != frozen.get('sceneContract',{}).get('sha256')
            or refs.get('authorDispatchContractSha256') != frozen.get('authorDispatchContract',{}).get('sha256')):
        raise ValueError('original dispatch or contract differs')
    supersedes = record.get('supersedesFollowup')
    if supersedes is not None:
        if (not isinstance(supersedes, dict) or set(supersedes) != {'path','sha256','fileSha256','reason'}
                or not isinstance(supersedes.get('reason'), str) or not supersedes['reason'].strip()):
            raise ValueError('superseded follow-up reference is invalid')
        old_path = path_for(supersedes['path'])
        old, old_raw = _read(old_path, course)
        if (old_path.name != 'review-followup.json' or old_path.parent.name != supersedes['sha256']
                or old.get('sha256') != supersedes['sha256']
                or digest({k:v for k,v in old.items() if k != 'sha256'}) != supersedes['sha256']
                or hashlib.sha256(old_raw).hexdigest() != supersedes['fileSha256']
                or old.get('binding') != record['binding'] or old.get('teachingRevision') != record['teachingRevision']
                or old.get('classHourIds') != record['classHourIds'] or old.get('authorization') != record['authorization']
                or old.get('originals', {}).get('requestSha256') != frozen.get('requestSha256')):
            raise ValueError('superseded follow-up evidence differs')
    native = record['currentNative']
    wanted = {'sessionId':native_proof['sessionId'], 'stageId':native_proof['stageId'],
              'documentSha256':native_proof['nativeDocumentSha256'],
              'authoringSourceSha256':native_proof['authoringSourceSha256'],
              'candidateSha256':native_proof['candidateSha256'],
              'candidateFileSha256':native_proof['candidateFileSha256'],
              'completeSceneReviewFollowupSha256':followup['sha256']}
    if native != wanted:
        raise ValueError('current native candidate or revision chain differs')
    original = draft['scopeReview']['officialResourceReview']
    prior = record['priorReview']
    if (prior.get('sha256') != digest(original) or prior.get('reviewExceptions') != original.get('reviewExceptions')
            or prior.get('priorAuthorizationInterpretation') != 'insufficiently_explicit'):
        raise ValueError('original review or prior interpretation differs')
    evidence = record['unchangedEvidence']
    effective = record['effectiveReview']
    validate_effective_review(original, effective, record['classHourIds'], evidence['nonVideoResourcesSha256'])
    validate_official_resource_review(effective, frozen['binding'])
    exceptions = effective.get('reviewExceptions')
    if (not isinstance(exceptions, list) or len(exceptions) != 1
            or exceptions[0].get('resourceType') != 'video'
            or exceptions[0].get('classHourIds') != record['classHourIds']
            or exceptions[0].get('authorizedAt') != auth['authorizedAt']
            or exceptions[0].get('userInstruction') != auth['answer']
            or ('authorizationQuestion' in exceptions[0] and exceptions[0]['authorizationQuestion'] != auth['question'])
            or ('userMessageId' in exceptions[0] and exceptions[0]['userMessageId'] != auth['userMessageId'])
            or ('authorizationTimeSource' in exceptions[0] and exceptions[0]['authorizationTimeSource'] != auth['timeSource'])):
        raise ValueError('effective exception does not match the verified decision')
    if json.loads(read_ref(evidence['originalReviewFile'])) != original:
        raise ValueError('original review file differs from frozen draft')
    post = draft['scopeReview']['postClassPractice']
    if (path_for(evidence['postClassPracticeSource']['path']).resolve() != path_for(post['sourcePath']).resolve()
            or evidence['postClassPracticeSource']['sha256'] != post['sourceSha256']
            or post.get('officialResourceReviewSha256') != digest(original)):
        raise ValueError('post-class source changed')
    validate_new_course_post_class_practice(draft)
    read_ref(evidence['postClassPracticeSource'])
    source_meta = evidence['officialSourceManifest']
    source_path = path_for(source_meta['path'])
    linked_manifest = original.get('sourceManifest', {})
    if (linked_manifest.get('sha256') != source_meta.get('sha256')
            or (source_path.parent / linked_manifest.get('path', '')).resolve() != source_path.resolve()):
        raise ValueError('official manifest is not the reviewed source')
    manifest = json.loads(read_ref(source_meta))
    entries = manifest.get('entries')
    if not isinstance(entries, list) or not entries or len(entries) != source_meta.get('entryCount'):
        raise ValueError('official preview manifest differs')
    if any(manifest.get('binding',{}).get(key) != frozen['binding'].get(key)
           for key in ('editionId','revisionId','nodeId','gradeCode','subject','volume','schoolSystem')):
        raise ValueError('official source binding differs')
    from urllib.parse import urlsplit
    seen, kinds, pages = set(), set(), {kind: set() for kind in KINDS}
    for entry in entries:
        if (not isinstance(entry, dict) or entry.get('classHourId') != 'lesson_1'
                or entry.get('resourceType') not in KINDS or entry.get('path') in seen
                or type(entry.get('page')) is not int or entry['page'] < 1
                or entry['page'] in pages[entry['resourceType']]):
            raise ValueError('official source entry invalid')
        resource = original['classHours'][0]['resources'][entry['resourceType']]
        entry_url, reviewed_url = urlsplit(entry.get('sourceUrl', '')), urlsplit(resource.get('sourceUrl', ''))
        if (entry.get('resourceId') != resource.get('resourceId')
                or entry_url.scheme != 'https' or entry_url.hostname != reviewed_url.hostname
                or entry_url.path.rsplit('/', 1)[0] != reviewed_url.path.rsplit('/', 1)[0]):
            raise ValueError('official preview image is not bound to its reviewed resource')
        relative = Path(entry['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('official image path escaped source directory')
        image = source_path.parent / relative
        _safe_child(course, image)
        data = course_bytes(image)
        if len(data) != entry.get('byteSize') or hashlib.sha256(data).hexdigest() != entry.get('sha256'):
            raise ValueError('official preview image changed')
        seen.add(entry['path']); kinds.add(entry['resourceType']); pages[entry['resourceType']].add(entry['page'])
    if kinds != set(KINDS) or any(values != set(range(1, len(values) + 1)) for values in pages.values()):
        raise ValueError('official non-video sources are incomplete')
    if 'checksumFile' in source_meta:
        read_ref(source_meta['checksumFile'])
    if not isinstance(record.get('evidenceBoundaries'), list) or not record['evidenceBoundaries']:
        raise ValueError('follow-up lacks its evidence boundaries')
    return {'schemaVersion':'mira.textbook.operator-verified-official-followup.v1',
            'followupPath':str(path.resolve()), 'followupSha256':expected_sha,
            'followupFileSha256':hashlib.sha256(raw).hexdigest(),
            'effectiveReviewSha256':digest(effective), 'operatorAttestation':deepcopy(operator),
            'followup':deepcopy(record),
            'verification':'operator_checked_conversation_hashes_do_not_authenticate_human',
            'authorizationIsPostDispatch':True, 'newDispatchAllowed':False}


def validate_frozen_followup(value, native_source):
    """Validate a previously operator-verified record without claiming user authentication."""
    if isinstance(value, dict) and value.get('authorizationIsPostDispatch') is False:
        from content.textbook_original_review_authorization import validate_frozen_original
        return validate_frozen_original(value, native_source)
    fields = {'schemaVersion','followupPath','followupSha256','followupFileSha256','effectiveReviewSha256',
              'operatorAttestation','followup','verification','authorizationIsPostDispatch','newDispatchAllowed'}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get('schemaVersion') != 'mira.textbook.operator-verified-official-followup.v1'
            or value.get('verification') != 'operator_checked_conversation_hashes_do_not_authenticate_human'
            or value.get('authorizationIsPostDispatch') is not True or value.get('newDispatchAllowed') is not False
            or not isinstance(value.get('followupPath'), str)
            or re.fullmatch(r'[a-f0-9]{64}', str(value.get('followupFileSha256'))) is None
            or not isinstance(value.get('followup'), dict) or not isinstance(native_source, dict)):
        raise ValueError('frozen official follow-up is invalid')
    record = value['followup']
    if (record.get('schemaVersion') != 'mira.textbook.official-resource-review-followup.v1'
            or record.get('status') != 'authorized_for_current_review_followup'
            or record.get('verification') != 'authorization_record_only_not_play_audio_or_publication'
            or record.get('classHourIds') != ['lesson_1']
            or record.get('sha256') != value['followupSha256']
            or digest({k:v for k,v in record.items() if k != 'sha256'}) != value['followupSha256']
            or digest(record.get('effectiveReview')) != value['effectiveReviewSha256']
            or record.get('currentNative',{}).get('sessionId') != native_source.get('sessionId')
            or record.get('currentNative',{}).get('stageId') != native_source.get('stageId')
            or record.get('currentNative',{}).get('documentSha256') != native_source.get('nativeDocumentSha256')
            or record.get('currentNative',{}).get('authoringSourceSha256') != native_source.get('authoringSourceSha256')
            or record.get('currentNative',{}).get('candidateSha256') != native_source.get('candidateSha256')
            or record.get('currentNative',{}).get('candidateFileSha256') != native_source.get('candidateFileSha256')
            or record.get('currentNative',{}).get('completeSceneReviewFollowupSha256') != native_source.get('followupSha256')):
        raise ValueError('frozen official follow-up source changed')
    verify_operator_attestation(record.get('authorization'), value.get('operatorAttestation'))
