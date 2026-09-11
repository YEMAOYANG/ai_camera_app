"""One explicit shared slot: prepare, produce to review, then publish through existing gates.

This module never starts background workers. make-policy/status are read-only to
business data; prepare/run/publish require an explicit operator invocation.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask
from core.config import AppConfig, validate_flask_config
from core.security import now_ms
from content.learning_budget_policy import LearningBudgetPolicy, digest
from content.single_course_budget import build_single_course_policy, single_slot_identity, with_single_teaching_scope, validate_single_search_provider, observe_single_course_budget, PRICE_SOURCES
from services.course_library_service import CourseLibraryService
from services.learning_curriculum_preparation_runner import learning_curriculum_preparation_runner
from services.service_factory import (learning_curriculum_preparation_service,
    openmaic_full_runtime_service)

LOCK_PATH = Path('/tmp/mira-generate-one-formal-course.lock')


def emit(event, **payload):
    print(json.dumps({'event': event, **payload}, ensure_ascii=False, sort_keys=True, default=str), flush=True)


def write_policy(path, policy, *, create_only=False):
    import tempfile
    # Do not resolve the final path for exclusive creation: an existing dangling
    # symlink is still an existing output and must never be followed/overwritten.
    path = Path(os.path.abspath(path)) if create_only else Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(json.dumps(policy.raw, ensure_ascii=False, indent=2) + '\n')
            output.flush()
            os.fsync(output.fileno())
        if create_only:
            try:
                os.link(temporary, path)  # Atomic no-clobber install of the complete 0600 file.
            except FileExistsError as exc:
                raise RuntimeError('policy output already exists; refusing to replace its state or authorization window') from exc
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def assert_search_budget_ready(args, library, identity, runtime_service, state):
    """Read-only guard; never issue/renew a grant or call a search provider."""
    from services.learning_budget_service import LearningBudgetService
    if not args.budget_policy:
        raise RuntimeError('an explicit existing budget policy is required before a production tick')
    policy = LearningBudgetPolicy.load(args.budget_policy)
    readiness = runtime_service.client.formal_generation_readiness()
    validate_single_search_provider(policy, readiness)
    budget = LearningBudgetService(library.database, policy=policy)
    key = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': identity['scope']})
    for runtime in state.get('runtimes', []):
        binding = json.loads(runtime['feature_manifest_json']).get('paidBudget') or {}
        if binding.get('authorizationId') != key or binding.get('required') is not True:
            raise RuntimeError('existing Runtime does not use the original single-course budget')
    with library.database.transaction() as conn:
        budget._enabled(conn)
        budget._scope_allowed(identity['scope'], now_ms())
        row = budget.repository.authorization(conn, key)
        if row is None:
            if state.get('dispatches') or state.get('runtimes'):
                raise RuntimeError('started course is missing its original frozen authorization')
        else:
            row = budget._authority(conn, key, now_ms())
            if json.loads(row['scope_json']) != identity['scope']:
                raise RuntimeError('original production budget scope changed')
            validate_single_search_provider(policy, readiness,
                frozen_prices=json.loads(row['price_keys_json'])['prices'])


def operator_app(args, *, publishing=False):
    app = Flask('mira-single-shared-course-operator')
    app.config.update(AppConfig.from_env().to_flask_config())
    app.config.update(LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=[args.grade],
        LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK=1,
        LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD=1,
        LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED=True,
        LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND=False,
        LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED=False,
        LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT=1,
        LEARNING_COURSE_LIBRARY_ENABLED=True, LEARNING_COURSE_SUPPLY_GRADE_SCOPES={},
        LEARNING_CLASSROOM_GENERATION_ENABLED=True,
        LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED=True,
        OPENMAIC_FULL_RUNTIME_ENABLED=True, OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=True,
        # This flag admits manual formal candidate progression. This standalone
        # Flask constructor never registers or starts the normal runner threads.
        OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED=True,
        LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED=True,
        LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED=publishing)
    if args.budget_policy:
        app.config['LEARNING_BUDGET_POLICY_PATH'] = str(Path(args.budget_policy).resolve())
    validate_flask_config(app.config)
    return app


def inventory(library, identity):
    with library.database.transaction() as conn:
        requests = list(conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (library.fingerprint,)).fetchall())
        owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans '
            'WHERE library_target_fingerprint=? AND grade_code=?', (library.fingerprint,library.target['gradeCode'])).fetchone()
        item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?', (identity['buildItemId'],)).fetchone()
        calls = conn.execute('SELECT COUNT(*) AS count FROM learning_course_provider_dispatches WHERE build_item_id=?',
            (identity['buildItemId'],)).fetchone()
        runtimes = list(conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms '
            'WHERE candidate_build_item_id=? ORDER BY created_at,id', (identity['buildItemId'],)).fetchall())
        receipt = conn.execute('SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?',
            (identity['buildItemId'],)).fetchone()
        touched = conn.execute('SELECT COUNT(DISTINCT item.id) AS count FROM learning_catalog_build_items item '
            'WHERE item.build_job_id=? AND item.id<>? AND (EXISTS '
            '(SELECT 1 FROM learning_course_provider_dispatches d WHERE d.build_item_id=item.id) OR EXISTS '
            '(SELECT 1 FROM learning_openmaic_runtime_classrooms r WHERE r.candidate_build_item_id=item.id))',
            (identity['buildId'],identity['buildItemId'])).fetchone()
    return {'requests':[dict(r) for r in requests], 'owner':dict(owner) if owner else None,
        'item':dict(item) if item else None, 'dispatches':int(calls['count']), 'runtimes':[dict(r) for r in runtimes],
        'receipt':dict(receipt) if receipt else None, 'otherTouchedItems':int(touched['count'])}


def assert_scope(state, args, *, require_request=True):
    expected = [{'subject':args.subject,'skill_id':args.skill,'variant_ordinal':args.slot}]
    if require_request and state['requests'] != expected:
        raise RuntimeError('enabled shared scope is not exactly the requested single slot')
    enforce_calls = (LearningBudgetPolicy.load(args.budget_policy).aggregate_limits_enabled
                     if args.budget_policy else True)
    if state['otherTouchedItems'] or enforce_calls and state['dispatches'] > 14 or len(state['runtimes']) > 1:
        raise RuntimeError('single-course production ceiling exceeded; no further dispatch')
    if state['owner'] and state['owner']['status'] in {'failed','superseded'}:
        raise RuntimeError('shared owner requires diagnosis; no automatic retry')
    item = state.get('item') or {}
    if item.get('status') == 'failed' or item.get('content_phase') == 'failed':
        raise RuntimeError('the existing course content stopped: ' + str(item.get('error_code') or 'content_failed')
                           + '; saved provider outputs require diagnosis before continuation')
    if any(r['status'] in {'failed','recovering'} or r.get('retired_at') for r in state['runtimes']):
        raise RuntimeError('course instance failed or has a retry history; stopping without another instance')


def review_ready(state):
    receipt = state['receipt'] or {}
    return bool(len(state['runtimes']) == 1 and state['runtimes'][0]['status'] == 'ready'
        and all(receipt.get(key) == 'passed' for key in ('classroom_status','tts_status','asr_roundtrip_status')))


def review_identity(state, identity):
    runtime = state['runtimes'][0]
    manifest = json.loads(runtime['feature_manifest_json'])
    from integrations.openmaic_formal_visual import validate_visual_review
    visual = validate_visual_review(manifest)
    if not visual or visual.get('status') != 'passed':
        raise RuntimeError('real automated visual review has not passed')
    return {'schemaVersion':'mira.single-course.visual-confirmation.v1', 'buildItemId':identity['buildItemId'],
        'upstreamClassroomId':runtime['upstream_classroom_id'], 'featureManifestSha256':digest(manifest), 'visualReviewReceiptSha256':visual['receiptSha256']}


def write_review_request(path, state, identity):
    data = {**review_identity(state,identity),'status':'awaiting_visual_observation',
            'featureManifest':json.loads(state['runtimes'][0]['feature_manifest_json'])}
    path = Path(path).resolve(); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n'); path.chmod(0o600)
    return str(path)


def authorize_teaching(args, library, identity, state):
    from services.learning_budget_service import LearningBudgetService
    from services.learning_paid_authority import scope_digest, teaching_budget_scope
    if not args.budget_policy or not args.learning_session_id:
        raise RuntimeError('authorize-teaching requires --budget-policy and --learning-session-id')
    if (state['receipt'] or {}).get('publication_status') != 'published' or not review_ready(state):
        raise RuntimeError('only the exact fully published sample can receive teaching authorization')
    service = openmaic_full_runtime_service()
    with library.database.transaction() as conn:
        session = conn.execute('SELECT * FROM learning_sessions WHERE id=?', (args.learning_session_id,)).fetchone()
        if session is None or session['status'] != 'in_progress' or session.get('completed_at') is not None:
            raise RuntimeError('start this published lesson normally before authorizing its active teaching session')
        row = service.repository.get_owned_session_runtime(conn, family_id=session['family_id'],
            child_id=session['child_id'], learning_session_id=session['id'])
        if (row is None or row.get('candidate_build_item_id') != identity['buildItemId']
                or row.get('runtime_classroom_id') != state['runtimes'][0]['id']
                or row.get('child_grade_code') != args.grade or row.get('course_grade_code') != args.grade
                or row.get('course_subject') != args.subject or row.get('course_node_code') != args.skill):
            raise RuntimeError('teaching session does not belong to this exact published sample and active grade')
        service._require_formal_quality_for_student_access(row)
        _, valid = service._formal_session_binding_state(row, family_id=session['family_id'], child_id=session['child_id'])
        if not valid:
            raise RuntimeError('create a normal Student classroom launch first; formal session binding is required')
        manifest = service._formal_manifest_for_launch(json.loads(row['feature_manifest_json']), row)
        if not manifest or int((manifest.get('formalEvidence') or {}).get('discussionActionCount') or 0) < 1:
            raise RuntimeError('the sample has no verified required live teaching contract')
        scope = teaching_budget_scope({**row, 'child_id': session['child_id']}, manifest, 'required_teaching')
    policy = with_single_teaching_scope(LearningBudgetPolicy.load(args.budget_policy),
        identity=identity, scope=scope, now=now_ms())
    budget = LearningBudgetService(library.database, policy=policy)
    # Freeze the exact teaching scope; cumulative admission applies only in enforcing mode.
    binding = budget.issue_course_authorization(authorization_id=scope_digest(scope), scope=scope)
    write_policy(args.budget_policy, policy)
    emit('required_teaching_authorized', learningSessionId=session['id'], courseId=scope['courseId'],
        authorizationId=binding['authorizationId'], aggregateLimitsEnabled=policy.aggregate_limits_enabled,
        maximumCny=(policy.raw['authorizationTemplates']['required_teaching']['maxUnits']['money_micros'] / 1000000
                    if policy.aggregate_limits_enabled else None),
        globalMaximumCny=(policy.raw['limits']['global']['day']['money_micros'] / 1000000
                          if policy.aggregate_limits_enabled else None),
        expiresAt=policy.raw['authorizationWindow']['expiresAt'], policySha256=policy.sha256,
        optionalInteraction=False)
    return 0


def close_budget(args, library, identity):
    from services.learning_budget_service import LearningBudgetService
    from services.learning_paid_authority import scope_digest
    if not args.budget_policy:
        raise RuntimeError('close-budget requires --budget-policy')
    policy = LearningBudgetPolicy.load(args.budget_policy)
    scopes = (policy.raw.get('authorizationWindow') or {}).get('scopes') or []
    if not scopes or scopes[0] != identity['scope'] or len(scopes) > 2 or any(
            scope['purpose'] != 'required_teaching' for scope in scopes[1:]):
        raise RuntimeError('policy does not belong to this single sample')
    budget = LearningBudgetService(library.database, policy=policy)
    closed = []
    for scope in scopes:
        key = (digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': scope})
               if scope['purpose'] == 'production' else scope_digest(scope))
        with library.database.transaction() as conn:
            exists = budget.repository.authorization(conn, key) is not None
        if exists:
            budget.close_authorization(authorization_id=key)
            closed.append(key)
    raw = policy.raw.copy()
    raw['enabled'] = False
    write_policy(args.budget_policy, LearningBudgetPolicy(raw))
    emit('sample_budget_closed', closedAuthorizationIds=closed, unresolvedChargesPreserved=True)
    return 0


def pause_budget(args, identity):
    """Disable new calls without revoking the original frozen authorization."""
    if not args.budget_policy:
        raise RuntimeError('pause-budget requires the original --budget-policy')
    policy = LearningBudgetPolicy.load(args.budget_policy)
    scopes = (policy.raw.get('authorizationWindow') or {}).get('scopes') or []
    if not scopes or scopes[0] != identity['scope'] or len(scopes) > 2 or any(
            scope['purpose'] != 'required_teaching' for scope in scopes[1:]):
        raise RuntimeError('policy does not belong to this single sample')
    raw = policy.raw.copy()
    raw['enabled'] = False
    write_policy(args.budget_policy, LearningBudgetPolicy(raw))
    emit('sample_budget_paused', authorizationRevoked=False, priorChargesPreserved=True,
         expiresAt=raw['authorizationWindow']['expiresAt'], windowExtended=False)
    return 0


def run(args):
    identity = single_slot_identity(args.grade,args.subject,args.skill,args.slot)
    if args.command == 'observe-budget':
        if not args.budget_policy:
            raise RuntimeError('observe-budget requires the original paused --budget-policy')
        original = LearningBudgetPolicy.load(args.budget_policy)
        policy = observe_single_course_budget(original, identity=identity)
        write_policy(args.budget_policy, policy)
        emit('sample_budget_metering_only', oldPolicySha256=original.sha256,
             policySha256=policy.sha256, aggregateLimitsEnabled=False, enabled=False,
             authorizationChanged=False, priorChargesPreserved=True,
             expiresAt=policy.raw['authorizationWindow']['expiresAt'], windowExtended=False)
        return 0
    app = operator_app(args,publishing=args.command == 'publish')
    with app.app_context():
        preparation = learning_curriculum_preparation_service()
        library = CourseLibraryService(app.config['DATABASE_URL'],grade_code=args.grade,
                                       preparation_repository=preparation.repository)
        if args.command == 'close-budget':
            return close_budget(args,library,identity)
        if args.command == 'pause-budget':
            return pause_budget(args,identity)
        if args.command in {'plan-budget-continuation', 'apply-budget-continuation'}:
            from services.learning_single_budget_continuation import continue_single_budget
            apply = args.command == 'apply-budget-continuation'
            if not args.budget_policy or args.continuation_expires_at is None:
                raise RuntimeError('continuation requires the original --budget-policy and fixed --continuation-expires-at')
            if apply and (not args.confirm_workers_stopped or not args.expected_continuation_sha):
                raise RuntimeError('continuation apply requires --confirm-workers-stopped and --expected-continuation-sha')
            result = continue_single_budget(database=library.database, policy_path=args.budget_policy,
                identity=identity, now=now_ms(), expires_at=args.continuation_expires_at,
                expected_sha=args.expected_continuation_sha, apply=apply, write_policy=write_policy)
            emit('budget_continuation_applied' if apply else 'budget_continuation_plan', **result)
            return 0
        if args.command in {'plan-search-transition', 'apply-search-transition'}:
            from services.learning_single_search_transition import transition_single_search
            if not args.budget_policy:
                raise RuntimeError('search transition requires the original paused --budget-policy')
            apply = args.command == 'apply-search-transition'
            if apply and (not args.confirm_workers_stopped or not args.expected_transition_sha):
                raise RuntimeError('search transition apply requires --confirm-workers-stopped and --expected-transition-sha')
            result = transition_single_search(database=library.database, policy_path=args.budget_policy,
                identity=identity, now=now_ms(), expected_sha=args.expected_transition_sha,
                apply=apply, write_policy=write_policy, continuation_expires_at=args.continuation_expires_at)
            emit('search_transition_applied' if apply else 'search_transition_plan', **result)
            return 0
        if args.command == 'prepare':
            before = inventory(library,identity)
            assert_scope(before,args,require_request=False)
            emit('prepared', **library.request_slot(subject=args.subject,skill_id=args.skill,variant_ordinal=args.slot),
                 buildItemId=identity['buildItemId'])
            return 0
        state = inventory(library,identity)
        if args.command == 'status':
            emit('status',gradeCode=args.grade,buildItemId=identity['buildItemId'],dispatches=state['dispatches'],
                 instances=len(state['runtimes']),reviewReady=review_ready(state),receipt=state['receipt'])
            return 0
        if args.command == 'reconcile-saved-stage':
            from services.learning_saved_stage_reconciliation import reconcile_saved_stage
            if not args.confirm_workers_stopped or not args.runtime_id or not args.completion:
                raise RuntimeError('saved-stage reconciliation requires --runtime-id, --completion and --confirm-workers-stopped')
            # The reconciliation helper validates the single failed Runtime;
            # retain the ordinary owner/content/supply checks without rejecting it first.
            assert_scope({**state, 'runtimes': []}, args)
            result = reconcile_saved_stage(runtime_service=openmaic_full_runtime_service(),
                preparation_repository=preparation.repository, identity=identity, state=state,
                runtime_id=args.runtime_id, completion_path=args.completion, now=now_ms())
            emit('saved_stage_reconciled', **result)
            if (result.get('result') or {}).get('runtime', {}).get('status') != 'ready':
                raise RuntimeError('same saved classroom did not pass normal Runtime validation; saved outcome retained')
            return 0
        if args.command in {'plan-native-budget-resume', 'resume-native-budget'}:
            from services.learning_native_budget_resume import resume_single_native_budget_failure
            from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, learning_budget_service
            if not args.budget_policy:
                raise RuntimeError('Native budget resume requires the original --budget-policy')
            apply = args.command == 'resume-native-budget'
            if apply and (not args.confirm_workers_stopped or not args.expected_history_sha):
                raise RuntimeError('Native budget resume requires --confirm-workers-stopped and --expected-history-sha')
            if apply:
                assert_search_budget_ready(args, library, identity, openmaic_full_runtime_service(), state)
            result = resume_single_native_budget_failure(adapter=learning_curriculum_preparation_checkpoint_adapter(),
                budget=learning_budget_service(),config=app.config,identity=identity,
                expected_history_sha=args.expected_history_sha,now=now_ms(),apply=apply)
            emit('native_budget_resume_applied' if apply else 'native_budget_resume_plan',**result)
            return 0
        if args.command in {'plan-native-prestage-recovery', 'recover-native-prestage'}:
            from services.learning_native_prestage_recovery import recover_single_native_prestage
            from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, learning_budget_service
            if not args.budget_policy:
                raise RuntimeError('Native recovery requires the original --budget-policy')
            apply = args.command == 'recover-native-prestage'
            if apply and (not args.confirm_workers_stopped or not args.expected_history_sha):
                raise RuntimeError('Native recovery requires --confirm-workers-stopped and --expected-history-sha')
            if apply:
                assert_search_budget_ready(args, library, identity, openmaic_full_runtime_service(), state)
            result = recover_single_native_prestage(adapter=learning_curriculum_preparation_checkpoint_adapter(),
                budget=learning_budget_service(),config=app.config,identity=identity,
                expected_history_sha=args.expected_history_sha,now=now_ms(),apply=apply)
            emit('native_prestage_recovery_applied' if apply else 'native_prestage_recovery_plan',**result)
            return 0
        if args.command in {'plan-content-recovery', 'recover-content', 'plan-billed-reply-recovery', 'recover-billed-reply', 'plan-runtime-preflight-recovery', 'recover-runtime-preflight'}:
            from services.learning_content_recovery import recover_single_content_item, recover_billed_single_content_reply, recover_single_runtime_preflight
            from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, learning_budget_service
            if not args.budget_policy:
                raise RuntimeError('content recovery requires the original --budget-policy')
            policy = LearningBudgetPolicy.load(args.budget_policy)
            window = policy.raw.get('authorizationWindow') or {}
            if (not policy.raw['enabled'] or window.get('scopes') != [identity['scope']]
                    or not window.get('startsAt', now_ms()+1) <= now_ms() < window.get('expiresAt', 0)):
                raise RuntimeError('original single-course authorization is no longer active')
            apply = args.command in {'recover-content','recover-billed-reply','recover-runtime-preflight'}
            if apply:
                if not args.confirm_workers_stopped or not args.expected_history_sha:
                    raise RuntimeError('recover-content requires --confirm-workers-stopped and --expected-history-sha')
                learning_budget_service().authorization_context(
                    authorization_id=digest({'schema':'mira.catalog-paid-budget.v1','scope':identity['scope']}))
            operation = recover_billed_single_content_reply if 'billed' in args.command else recover_single_content_item
            extra = {}
            if 'runtime-preflight' in args.command:
                operation = recover_single_runtime_preflight
                extra['readiness'] = openmaic_full_runtime_service().client.formal_generation_readiness()
            result = operation(adapter=learning_curriculum_preparation_checkpoint_adapter(),
                identity=identity, expected_history_sha=args.expected_history_sha, now=now_ms(), apply=apply, **extra)
            emit('content_recovery_applied' if apply else 'content_recovery_plan', **result)
            return 0
        if not args.confirm_workers_stopped:
            raise RuntimeError('--confirm-workers-stopped is required; the operator never starts ordinary workers')
        assert_scope(state,args)
        if args.command == 'authorize-teaching':
            return authorize_teaching(args,library,identity,state)
        if args.command == 'run-to-review' and review_ready(state):
            request_file = write_review_request(args.review_output,state,identity)
            emit('awaiting_visual_observation',buildItemId=identity['buildItemId'],reviewRequest=request_file,
                 dispatches=state['dispatches'],instances=1)
            return 0
        if args.command == 'publish':
            if not review_ready(state):
                raise RuntimeError('real classroom quality and audio receipts are not ready')
            confirmation = json.loads(Path(args.visual_confirmation).read_text())
            if confirmation != {**review_identity(state,identity),'status':'approved'}:
                raise RuntimeError('visual confirmation does not match the exact final candidate')
            # This acknowledgement is additional to, never a replacement for, Native/Python quality gates.
        else:
            if not args.budget_policy:
                raise RuntimeError('--budget-policy with an explicit fixed scope is required')
            policy = LearningBudgetPolicy.load(args.budget_policy)
            window = policy.raw.get('authorizationWindow') or {}
            if window.get('scopes') != [identity['scope']] or not policy.raw['enabled']:
                raise RuntimeError('budget policy is not bound to this exact frozen slot')
            if not window['startsAt'] <= now_ms() < window['expiresAt']:
                raise RuntimeError('single-slot paid authorization has expired')
        if args.command == 'run-to-review':
            from services.service_factory import _checkpoint_question_phase_profile
            profile = _checkpoint_question_phase_profile()
            if (not profile or profile.get('name') != 'openmaic_runtime' or profile.get('model') != 'courseware-v2'
                    or str(profile.get('baseUrl') or '').rstrip('/')
                    != str(app.config.get('OPENMAIC_FULL_RUNTIME_INTERNAL_URL') or '').rstrip('/')):
                raise RuntimeError('single course requires the configured private OpenMAIC courseware authority')
            # Native owns the configured DeepSeek credentials and actual model
            # request. The exact production grant admits only its declared prices.
        runtime_service = openmaic_full_runtime_service()
        # No paid probe is silently performed. Existing Host/provider gates remain authoritative.
        if args.command == 'run-to-review' and not runtime_service.formal_provider_circuit_status()['dispatchAllowed']:
            raise RuntimeError('existing provider circuit is not ready; no provider probe or generation was dispatched')
        deadline = time.monotonic()+args.timeout_seconds
        observed = None
        while time.monotonic() < deadline:
            state = inventory(library,identity); assert_scope(state,args)
            receipt = state['receipt'] or {}
            if receipt.get('publication_status') == 'published':
                emit('published',buildItemId=identity['buildItemId'],courseId=receipt.get('course_id'),courseVersion=receipt.get('course_version'))
                return 0
            if args.command == 'run-to-review' and review_ready(state):
                request_file = write_review_request(args.review_output,state,identity)
                emit('awaiting_visual_observation',buildItemId=identity['buildItemId'],reviewRequest=request_file,
                     dispatches=state['dispatches'],instances=1)
                return 0
            if args.command == 'run-to-review' and policy.aggregate_limits_enabled and state['dispatches'] >= 14 and (state['item'] or {}).get('content_gate_status') != 'passed':
                raise RuntimeError('14 content dispatches reached without passed content; no automatic extra attempt')
            # Publication consumes the already verified receipts, without authorizing a new paid call.
            if args.command != 'publish':
                assert_search_budget_ready(args, library, identity, runtime_service, state)
            for runtime in state['runtimes']:
                if runtime['status'] == 'generating' and runtime.get('upstream_job_id'):
                    runtime_service.generation_status(runtime['upstream_job_id'])
            observation = (state['dispatches'],(state['item'] or {}).get('content_phase'),
                tuple((r['status'],r.get('quality_status')) for r in state['runtimes']),
                tuple(receipt.get(k) for k in ('classroom_status','tts_status','asr_roundtrip_status','publication_status')))
            if observation != observed:
                emit('progress',buildItemId=identity['buildItemId'],dispatches=state['dispatches'],
                     contentPhase=observation[1],instances=len(state['runtimes']),quality=observation[2],receipts=observation[3])
                observed=observation
            learning_curriculum_preparation_runner.run_once(app,now_ms=now_ms())
            if args.once:
                emit('step_completed', buildItemId=identity['buildItemId'],
                     previousContentPhase=observation[1], reviewReady=False)
                return 0
            time.sleep(1.25)
        raise RuntimeError('operator timeout; persisted dispatches and candidates retained without retry')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('make-policy','prepare','status','run-to-review','publish','authorize-teaching','close-budget','pause-budget','observe-budget','plan-search-transition','apply-search-transition','plan-budget-continuation','apply-budget-continuation','plan-content-recovery','recover-content','plan-billed-reply-recovery','recover-billed-reply','plan-runtime-preflight-recovery','recover-runtime-preflight','plan-native-prestage-recovery','recover-native-prestage','plan-native-budget-resume','resume-native-budget','reconcile-saved-stage'))
    p.add_argument('--grade',choices=tuple(f'primary_{n}' for n in range(1,7)),required=True)
    p.add_argument('--subject',choices=('chinese','math','english'),required=True)
    p.add_argument('--skill',required=True);p.add_argument('--slot',type=int,required=True)
    p.add_argument('--budget-policy');p.add_argument('--vision-provider',choices=('openai','deepseek'),default='deepseek')
    p.add_argument('--search-provider', choices=('brave','baidu'),
        help='make-policy only: explicitly choose the search price scope (default: brave)')
    p.add_argument('--policy-output',default=str(ROOT.parent/'output/single-course-budget.json'))
    p.add_argument('--review-output',default=str(ROOT.parent/'output/single-course-review-request.json'))
    p.add_argument('--visual-confirmation');p.add_argument('--confirm-workers-stopped',action='store_true')
    p.add_argument('--learning-session-id')
    p.add_argument('--runtime-id'); p.add_argument('--completion')
    p.add_argument('--expected-history-sha')
    p.add_argument('--expected-transition-sha')
    p.add_argument('--expected-continuation-sha')
    p.add_argument('--continuation-expires-at', type=int,
        help='reviewed fixed expiry in epoch milliseconds; same-day budget continuation or one search transition')
    p.add_argument('--once', action='store_true', help='run one existing preparation tick without claiming review readiness')
    p.add_argument('--timeout-seconds',type=int,default=7200);p.add_argument('--ttl-minutes',type=int,default=180)
    args=p.parse_args()
    if args.search_provider is not None and args.command != 'make-policy':
        p.error('--search-provider is only for make-policy; it cannot switch an existing authorization')
    if args.continuation_expires_at is not None and args.command not in {'plan-search-transition','apply-search-transition','plan-budget-continuation','apply-budget-continuation'}:
        p.error('--continuation-expires-at is only for an audited continuation or search transition')
    if not 60 <= args.timeout_seconds <= 21600: p.error('timeout must be 60..21600 seconds')
    if args.command=='publish' and not args.visual_confirmation: p.error('publish requires --visual-confirmation')
    if args.once and args.command != 'run-to-review': p.error('--once is only valid with run-to-review')
    if args.learning_session_id and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,254}',args.learning_session_id):
        p.error('learning session identifier is invalid')
    if args.expected_history_sha and not re.fullmatch(r'[a-f0-9]{64}',args.expected_history_sha):
        p.error('expected history must be a SHA256')
    if args.expected_transition_sha and not re.fullmatch(r'[a-f0-9]{64}',args.expected_transition_sha):
        p.error('expected transition must be a SHA256')
    if args.expected_continuation_sha and not re.fullmatch(r'[a-f0-9]{64}',args.expected_continuation_sha):
        p.error('expected continuation must be a SHA256')
    try:
        if args.command=='make-policy':
            policy,identity=build_single_course_policy(grade=args.grade,subject=args.subject,skill=args.skill,ordinal=args.slot,
                now=now_ms(),ttl_ms=args.ttl_minutes*60000,vision_provider=args.vision_provider,
                search_provider=args.search_provider or 'brave')
            path=write_policy(args.policy_output,policy,create_only=True)
            emit('policy_file_prepared_not_activated',path=str(path),sha256=policy.sha256,identity=identity,
                 expiresAt=policy.raw['authorizationWindow']['expiresAt'],maximumCny=10,
                 searchProvider=args.search_provider or 'brave',priceSources=PRICE_SOURCES)
            return 0
        with LOCK_PATH.open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return run(args)
    except Exception as exc:
        emit('stopped',reason=str(exc) if isinstance(exc,(RuntimeError,ValueError)) else type(exc).__name__)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
