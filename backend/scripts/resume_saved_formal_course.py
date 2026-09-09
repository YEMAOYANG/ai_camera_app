"""Reconcile one audited saved-stage recovery, then drain its publication work.

No content, classroom, or Agent creation is reachable from this operator.
It preserves the original rejected Runtime in an audit event before reopening
validation of the identical upstream request. Existing publication gates apply.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.security import now_ms
from integrations.openmaic_formal_quality import quality_sha
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from scripts.course_library import assert_budget
from scripts.generate_one_formal_course import _operator_app, LOCK_PATH
from services.course_library_service import CourseLibraryService
from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, openmaic_full_runtime_service


def emit(event, **payload):
    print(json.dumps(dict(event=event, **payload), ensure_ascii=False), flush=True)


def run(runtime_id: str, completion_path: Path):
    completion = json.loads(completion_path.read_text())
    receipt_sha = completion.pop('receiptSha256', None)
    if not receipt_sha or quality_sha(completion) != receipt_sha or completion.get('kind') != 'operator_saved_stage_repair':
        raise RuntimeError('saved-stage recovery receipt is invalid')
    app = _operator_app()
    app.config.update(LEARNING_COURSE_LIBRARY_ENABLED=True, LEARNING_COURSE_SUPPLY_SCOPE='canary',
                      LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT=3)
    with LOCK_PATH.open('a') as lock, app.app_context():
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime_service = openmaic_full_runtime_service()
        adapter = learning_curriculum_preparation_checkpoint_adapter()
        # This operator deliberately drains the formal tail only. The adapter's
        # normal tail may enqueue a successor, which is forbidden here.
        adapter.runtime_candidate_processor = None
        library = CourseLibraryService(app.config['DATABASE_URL'], preparation_repository=adapter.repository)
        owner = library.ensure_owner()
        with runtime_service.repository.transaction() as conn:
            runtime = runtime_service.repository.get_runtime_classroom(conn, runtime_id=runtime_id)
            if not runtime or runtime.get('retired_at') is not None or runtime.get('candidate_target_fingerprint') != library.fingerprint:
                raise RuntimeError('Runtime is not the current library candidate')
            assert_budget(conn, owner['catalog_build_id'], 3)
        upstream = runtime_service.client.get_generation_job_by_request_id(str(runtime['request_id']))
        manifest = runtime_service.repository.decode_json(runtime['feature_manifest_json'], {})
        expected_sha = runtime_service._formal_input_sha256(runtime_request_id=str(runtime['request_id']),
            generation_contract=manifest.get('generationContract'), formal_contract=manifest.get('formalRuntimeContract'))
        if not upstream or upstream.status != 'succeeded' or upstream.job_id != runtime['upstream_job_id'] \
                or upstream.classroom_id != completion['stageId'] \
                or not OpenMaicFullRuntimeClient.formal_job_identity_matches(upstream,
                    runtime_request_id=str(runtime['request_id']), formal_input_sha256=expected_sha):
            raise RuntimeError('recovered upstream request identity does not match')
        with adapter.repository.transaction() as conn:
            published = conn.execute(
                "SELECT publication_status FROM learning_curriculum_classroom_item_receipts "
                "WHERE runtime_classroom_id = ? AND target_fingerprint = ?",
                (runtime_id, library.fingerprint),
            ).fetchone()
        if published and published['publication_status'] == 'published':
            emit('already_published', runtimeId=runtime_id, status=library.status())
            return
        # Completion is governed by the running library owner, never by a child
        # follower. Claim that owner before revalidating any completed runtime.
        with adapter.repository.transaction() as conn:
            plan = adapter.repository.claim_next(conn, now=now_ms(), lease_ms=600_000,
                supported_stages=('generating_content', 'building_classrooms', 'generating_speech', 'validating'),
                grade_code='primary_1', target_fingerprint=library.fingerprint)
        if not plan or plan['id'] != owner['id']:
            raise RuntimeError('library publication lease is unavailable')
        try:
            if runtime['status'] == 'failed':
                # Preparation events are public progress messages. Preserve private
                # artifact identities in the operator audit, outside that stream.
                audit_path = completion_path.parent / f'backend-reconciliation-{runtime_id}-{runtime["updated_at"]}.json'
                audit = {'runtimeId': runtime_id, 'originalErrorCode': runtime['error_code'],
                    'originalUpdatedAt': runtime['updated_at'], 'upstreamJobId': runtime['upstream_job_id'],
                    'recoveryReceiptSha256': receipt_sha, 'sourceJobSha256': completion['sourceJobSha256']}
                try:
                    with audit_path.open('x') as audit_file:
                        json.dump(audit, audit_file, ensure_ascii=False, indent=2)
                except FileExistsError:
                    if json.loads(audit_path.read_text()) != audit:
                        raise RuntimeError('original Runtime audit has changed')
                with runtime_service.repository.transaction() as conn:
                    if runtime['quality_status'] == 'quarantined' and runtime['error_code'] == 'openmaic_formal_generation_ambiguous':
                        changed = runtime_service.repository.resume_formal_candidate_after_authoritative_completion(conn,
                            runtime_id=runtime_id, expected_upstream_job_id=str(runtime['upstream_job_id']),
                            expected_request_id=str(runtime['request_id']),
                            expected_feature_manifest_json=str(runtime['feature_manifest_json']), now=now_ms())
                    else:
                        changed = runtime_service.repository.resume_formal_candidate_after_validator_fix(conn,
                            runtime_id=runtime_id, expected_upstream_job_id=str(runtime['upstream_job_id']),
                            expected_error_code=str(runtime['error_code']), now=now_ms())
                    if not changed:
                        raise RuntimeError('Runtime no longer matches the original rejection')
                    adapter.repository.append_event(conn, plan_id=str(owner['id']), event_type='saved_classroom_recovery',
                        stage=str(owner['stage']), payload={'code': 'saved_classroom_recovery',
                          'errorCode': runtime['error_code'], 'status': 'pending_review'}, now=now_ms())
                result = runtime_service.generation_status(str(runtime['upstream_job_id']))
                emit('runtime_revalidated', result=result)
                if (result or {}).get('runtime', {}).get('status') != 'ready':
                    raise RuntimeError('same saved course did not pass Runtime validation')
            elif runtime['status'] != 'ready':
                raise RuntimeError('Runtime must be rejected or ready')
            if int(plan.get('lease_expires_at') or 0) <= now_ms():
                # The old generation coordinator can expire while an approved
                # saved-stage recovery runs. Only a ready, receipted classroom
                # may receive a fresh, bounded publication window.
                audit = {'planId': plan['id'], 'runtimeId': runtime_id,
                    'oldHardDeadlineAt': plan['hard_deadline_at'], 'oldLeaseExpiresAt': plan['lease_expires_at'],
                    'recoveryReceiptSha256': receipt_sha, 'requestedPublicationLeaseMs': 600_000}
                audit_path = completion_path.parent / f'publication-window-{runtime_id}-{now_ms()}.json'
                with audit_path.open('x') as audit_file:
                    json.dump(audit, audit_file, ensure_ascii=False, indent=2)
                with adapter.repository.transaction() as conn:
                    renewed = adapter.repository.renew_saved_classroom_publication_lease(conn,
                        plan_id=str(plan['id']), lease_token=str(plan['lease_token']), runtime_id=runtime_id,
                        upstream_job_id=str(runtime['upstream_job_id']), target_fingerprint=library.fingerprint,
                        now=now_ms(), lease_ms=600_000)
                if renewed is None:
                    raise RuntimeError('saved classroom publication window could not be renewed')
                plan = renewed
            for _ in range(3):
                result = adapter._process_progressive_formal_tail(plan, stage=str(plan['stage']))
                emit('publication_tail', result=result)
                with adapter.repository.transaction() as conn:
                    adapter.repository.persist_progressive_formal_counts(conn, plan_id=str(plan['id']),
                        lease_token=str(plan['lease_token']), target_fingerprint=library.fingerprint,
                        expected_stage=str(plan['stage']), now=now_ms())
                if int((result or {}).get('published') or 0) >= 1:
                    break
            with adapter.repository.transaction() as conn:
                exact = conn.execute(
                    "SELECT publication_status FROM learning_curriculum_classroom_item_receipts "
                    "WHERE runtime_classroom_id = ? AND target_fingerprint = ?",
                    (runtime_id, library.fingerprint),
                ).fetchone()
                if not exact or exact['publication_status'] != 'published':
                    raise RuntimeError('the requested saved classroom has not been published')
        finally:
            with adapter.repository.transaction() as conn:
                adapter.repository.release_lease(conn, plan_id=str(plan['id']), lease_token=str(plan['lease_token']),
                    expected_stage=str(plan['stage']), now=now_ms())
        emit('library', status=library.status())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-id', required=True)
    parser.add_argument('--completion', required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.runtime_id, args.completion)
    except Exception as exc:
        emit('stopped', reason=str(exc))
        raise SystemExit(1)
