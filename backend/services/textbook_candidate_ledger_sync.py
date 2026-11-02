"""CAS synchronization of a reviewed private author's candidate ledger.

The old registry object and native-author evidence remain unchanged. This
adapter can only advance the exact verified ledger; it cannot dispatch a model,
change a lesson, or publish. Its two validations surround object creation and
registry CAS so a concurrent authoring change cannot be silently accepted.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from content.textbook_authoring_candidate import (
    CANDIDATE_SCHEMA, V4_JOB_SCHEMA, _assets, _contract, _find_job,
    _image_coverage, _questions, _scenes,
)
from content.textbook_catalog import digest
from core.errors import ApiError
from repositories.course_storage_repository import storage_id_for
from services.course_file_store import course_bytes
from services.course_file_writer import CourseFileWriter, CourseFileWriteError, _hash, _json_bytes, _require
from services.textbook_partial_preview_revision import _native_review_events, verify_reviewed_scene_chain
from services.textbook_preview_audio import core_content


def _seal(ledger, *, session, stage, contract):
    fields = {'schemaVersion', 'sessionId', 'stageId', 'frozenContract', 'status', 'verification',
              'assetBindings', 'bindingHistory', 'scenes', 'sha256'}
    if (not isinstance(ledger, dict) or set(ledger) != fields
            or ledger.get('schemaVersion') != CANDIDATE_SCHEMA
            or ledger.get('sessionId') != session or ledger.get('stageId') != stage
            or ledger.get('status') != 'author_candidate'
            or ledger.get('verification') != 'static_contract_only_not_play_or_semantic_review'
            or ledger.get('frozenContract') != contract
            or digest({k: v for k, v in ledger.items() if k != 'sha256'}) != ledger.get('sha256')):
        raise ValueError('candidate_ledger_seal_invalid')


def verify_transition(*, old, new, target, session, stage, frozen, contract, job, events, frozen_sha,
                      classroom_directory):
    """Validate exact scenes, immutable assets, and authenticated patch chain."""
    native = frozen.get('authorDispatchContract') if frozen.get('schemaVersion') == V4_JOB_SCHEMA else frozen.get('sceneContract')
    _seal(old, session=session, stage=stage, contract=native)
    _seal(new, session=session, stage=stage, contract=native)
    if any(old.get(k) != new.get(k) for k in old if k not in {'scenes', 'sha256'}):
        raise ValueError('candidate_ledger_identity_changed')
    if (target.get('id') != stage or target.get('stage', {}).get('id') != stage
            or not isinstance(target.get('scenes'), list)):
        raise ValueError('candidate_ledger_target_invalid')
    old_scenes = []
    for item in old.get('scenes', []):
        raw = item.get('canonicalJson') if isinstance(item, dict) else None
        if (not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != item.get('sha256')):
            raise ValueError('candidate_ledger_old_scene_invalid')
        old_scenes.append(json.loads(raw))
    previous = {'id': stage, 'stage': deepcopy(target['stage']), 'scenes': old_scenes}
    assets = _assets(new, Path(classroom_directory).resolve(), stage)
    _scenes(old, previous, contract)
    _scenes(new, target, contract)
    _image_coverage(target, contract, assets)
    _questions(target, contract, assets)
    chain = verify_reviewed_scene_chain(source_room=previous, target_room=target, stage_id=stage,
        session_id=session, frozen_file_sha256=frozen_sha, job_directory=job, events=events)
    if not chain['patches']:
        raise ValueError('candidate_ledger_no_reviewed_changes')
    return {'chainSha256': digest(chain), 'patchCount': len(chain['patches']),
            'targetSha256': digest(target), 'oldLedgerSha256': old['sha256'], 'newLedgerSha256': new['sha256']}


class CandidateLedgerWriter(CourseFileWriter):
    """Restrict the generic CAS writer to one verified candidate and parent."""
    def __init__(self, *, preview_service, parent_key, classroom_directory, config=None, repository=None):
        super().__init__(config=config, repository=repository)
        self.preview_service = preview_service
        self.parent_key = parent_key
        self.classrooms = Path(classroom_directory).resolve()

    def _verify(self, path, old, new):
        service = self.preview_service
        with service.repository.transaction() as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?',
                               (self.parent_key,)).fetchone()
            if row is None or row['runtime_origin'] != service.runtime.base_url:
                raise ValueError('candidate_ledger_parent_invalid')
            frozen_input = service.repository.parse(row['input_json'])
            parent_room = service.repository.parse(row['classroom_json'])
            result = service.repository.parse(row['result_json'])
            if (frozen_input.get('previewKey') != self.parent_key
                    or digest({k: v for k, v in frozen_input.items() if k not in ('previewKey', 'requirement')}) != self.parent_key
                    or digest(parent_room) != row['classroom_sha256']
                    or frozen_input.get('executionPolicy') != 'operator-authored-saved-classroom.v1'
                    or result.get('audioPartial') is not True):
                raise ValueError('candidate_ledger_parent_invalid')
            manifest = service._manifest(conn, row['edition_id'], row['revision_id'])
        author = frozen_input.get('authoring', {})
        stage, session_id = author.get('stageId'), author.get('sessionId')
        expected_path = self._source(self.classrooms / str(stage) / 'textbook-authoring-candidate.json')
        if path != expected_path or not stage or not session_id:
            raise ValueError('candidate_ledger_path_invalid')
        found = _find_job(service.authoring_output_root, row['edition_id'], row['revision_id'], row['node_id'],
                          session_id, stage, True)
        if found is None:
            raise ValueError('candidate_ledger_job_missing')
        job, frozen, state = found
        # Existing workbench verifier checks frozen request/attachments, owner
        # fingerprint, original session identity, and performs GETs only.
        relative_job = job.resolve().relative_to(self.root)
        client, session = self._authoring_readback(relative_job, state)
        if session.get('id') != session_id or session.get('status') != 'succeeded':
            raise ValueError('candidate_ledger_session_not_terminal')
        stages = self._authoring_stages(relative_job, state, client, session)
        if stage not in stages:
            raise ValueError('candidate_ledger_stage_missing')
        document = stages[stage][0]
        target = {'id': stage, 'stage': deepcopy(document['stage']), 'scenes': deepcopy(document['scenes'])}
        previous = core_content(parent_room)
        if previous.get('id') != row['classroom_id'] or previous.get('stage', {}).get('id') != row['classroom_id']:
            raise ValueError('candidate_ledger_parent_invalid')
        previous['id'] = previous['stage']['id'] = stage
        for scene in previous.get('scenes', []):
            if scene.get('stageId') != row['classroom_id']:
                raise ValueError('candidate_ledger_parent_invalid')
            scene['stageId'] = stage
        from_ledger = {'id': stage, 'stage': deepcopy(target['stage']),
                       'scenes': [json.loads(item['canonicalJson']) for item in old['scenes']]}
        if previous != from_ledger:
            raise ValueError('candidate_ledger_parent_changed')
        events = _native_review_events(client, session_id)
        raw = course_bytes(job / 'frozen.json')
        frozen_sha = hashlib.sha256(raw).hexdigest()
        contract = _contract(job, frozen, manifest, row['node_id'])
        return verify_transition(old=old, new=new, target=target, session=session_id, stage=stage,
            frozen=frozen, contract=contract, job=job, events=events, frozen_sha=frozen_sha,
            classroom_directory=self.classrooms)

    def _policy(self, path, old_raw, new_raw, old, new, meta, conn):
        # Preserve the existing registry's published immutability and preview
        # guard; no other file or candidate identity is accepted by _verify.
        storage_id = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        bound = json.dumps({'sourcePathSha256': _hash(path.encode()), 'sha256': _hash(old_raw)}, separators=(',', ':'))
        published = conn.execute("SELECT scope_key FROM course_storage_scopes WHERE storage_id=? "
            "AND JSON_UNQUOTE(JSON_EXTRACT(scope_json,'$.status'))='published' "
            "AND JSON_CONTAINS(bindings_json,?) LIMIT 1 FOR UPDATE", (storage_id, bound)).fetchone()
        _require(published is None, 'course_storage_published_immutable')
        _require(meta.get('status') in {'generated_saved', 'preview_ready', 'review_required', 'prepared', 'running', 'generating'})
        self._preview_guard(conn, meta, meta.get('classroomId'), required=False)
        try:
            self._verify(path, old, new)
        except (ApiError, OSError, ValueError, KeyError, TypeError, AttributeError):
            raise CourseFileWriteError('candidate_ledger_verification_failed') from None
        return 'reviewed_authoring_candidate_ledger'

    def dry_run(self, path, *, expected_old_sha256, expected_new_sha256):
        relative = self._source(path)
        source = self.root / relative
        if source.is_symlink() or not source.is_file():
            raise CourseFileWriteError('candidate_ledger_local_missing')
        raw = source.read_bytes()
        if _hash(raw) != expected_new_sha256:
            raise CourseFileWriteError('candidate_ledger_local_changed')
        old_raw = self._read(relative, expected_old_sha256)
        old, new = _json_bytes(old_raw), _json_bytes(raw)
        storage = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        current = self.repository.resolve(relative, storage)
        scope = self.repository.head_scope(relative, storage)
        if current is None or scope is None or current['sha256'] != expected_old_sha256:
            raise CourseFileWriteError('course_storage_head_conflict')
        with self.repository.database.transaction() as conn:
            policy = self._policy(relative, old_raw, raw, old, new, scope['metadata'], conn)
        proof = self._verify(relative, old, new)
        return {'status': 'validated_not_written', 'oldByteSha256': _hash(old_raw),
                'newByteSha256': _hash(raw), 'scopeKey': scope['scopeKey'],
                'writePolicy': policy, **proof}

    def synchronize(self, path, *, expected_old_sha256, expected_new_sha256):
        proof = self.dry_run(path, expected_old_sha256=expected_old_sha256, expected_new_sha256=expected_new_sha256)
        raw = (self.root / self._source(path)).read_bytes()
        if _hash(raw) != expected_new_sha256:
            raise CourseFileWriteError('candidate_ledger_local_changed')
        result = self.write_bytes(path, raw, expected_sha256=expected_old_sha256)
        # The reader verifies the committed immutable object, not the local copy.
        observed = self._read(path, expected_new_sha256)
        if _hash(observed) != expected_new_sha256:
            raise CourseFileWriteError('candidate_ledger_remote_readback_failed', 502)
        storage = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        head = self.repository.resolve(self._source(path), storage)
        if head is None or head.get('sha256') != expected_new_sha256:
            raise CourseFileWriteError('course_storage_head_conflict')
        return {'status': 'synchronized', 'dryRun': proof, 'remoteByteSha256': _hash(observed),
                'scopeKey': result['scopeKey'] if 'scopeKey' in result else None}
