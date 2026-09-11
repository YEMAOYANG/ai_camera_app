"""Local plan/apply for the original ten-page Agent quota stop; no generation API."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from content.learning_budget_policy import canonical, digest
from content.single_course_budget import single_slot_identity
from core.security import now_ms
from scripts.generate_one_library_course import operator_app, LOCK_PATH
from services.service_factory import learning_curriculum_preparation_checkpoint_adapter, learning_budget_service
from services.learning_native_budget_resume import _settled_ledger_sha256, JOB

EVENT = 'single_course_agent_quota_resume'
ARCHIVES = ROOT / 'data/learning-provider-replies'
NATIVE = ROOT.parent / 'openmaic-runtime/.runtime/OpenMAIC'


def native(config, mode, expected=None, stopped=False, feedback=None):
    env = os.environ.copy()
    values = dotenv_values(ROOT / '.env')
    env['MIRA_OPENMAIC_AGENT_DATABASE_URL'] = values.get('MIRA_OPENMAIC_AGENT_DATABASE_URL') or ''
    env['MIRA_BACKEND_INTERNAL_URL'] = 'http://127.0.0.1:8000'
    env['MIRA_INTERNAL_API_TOKEN'] = config['INTERNAL_API_TOKEN']
    result = subprocess.run(['node','--require','tsx/cjs',str(ROOT.parent/'openmaic-runtime/scripts/resume-agent-budget.ts')],
        input=json.dumps({'mode':mode,'expectedSha':expected,'confirmRuntimeStopped':stopped,'feedback':feedback}),
        text=True,capture_output=True,cwd=NATIVE,env=env,timeout=90)
    if result.returncode:
        code = result.stderr.strip()
        raise ValueError(code if re.fullmatch(r'LOCAL_AGENT_BUDGET_RESUME_[A-Z_]+',code) else 'Local Native resume failed')
    return json.loads(result.stdout)


def public_event(proof, state):
    return {'recoveryReceiptId':proof['sourceSha256'],'nativeRecoveryReceiptId':proof['native']['sourceSha256'],
        'runtimeId':proof['runtime']['id'],'ownerId':proof['owner']['id'],'jobId':JOB,
        'sceneCount':proof['native']['sceneCount'],'status':state}


def run(args):
    feedback=None
    if args.feedback_file:
        text=Path(args.feedback_file).read_text()
        if not text.strip() or len(text.encode())>32768 or hashlib.sha256(text.encode()).hexdigest()!=args.feedback_sha:
            raise ValueError('Feedback file SHA does not match')
        feedback={'text':text,'sha256':args.feedback_sha}
    identity=single_slot_identity('primary_6','math','fraction_ratio_percentage',1)
    app=operator_app(SimpleNamespace(grade='primary_6',budget_policy=args.budget_policy))
    with app.app_context():
        adapter=learning_curriculum_preparation_checkpoint_adapter()
        repo=adapter.catalog_service.repository
        budget=learning_budget_service()
        if budget.policy.aggregate_limits_enabled or not budget.policy.raw['enabled']:
            raise ValueError('Explicit enabled observation mode is required')
        saved_path=ARCHIVES/('local-agent-budget-'+str(args.expected_sha)+'.json')
        saved=json.loads(saved_path.read_text()) if args.expected_sha and saved_path.exists() else None
        if saved and digest({k:v for k,v in saved.items() if k!='sourceSha256'})!=args.expected_sha:
            raise ValueError('Private archive changed')
        with repo.transaction() as conn:
            conn.execute('SELECT id FROM learning_budget_control WHERE id=1 FOR UPDATE').fetchone()
            budget._enabled(conn)
            release,build=repo.lock_build_authority(conn,build_id=identity['buildId'])
            rows=repo.list_build_items(conn,build_id=identity['buildId'],for_update=True)
            item=next((row for row in rows if row['id']==identity['buildItemId']),None)
            if (not item or item['status']!='course_ready' or item['content_gate_status']!='passed' or
                not repo._content_authority_is_exact(conn,release=release,build=build,rows=rows,allow_terminal=True) or
                any(row['status']!='pending' for row in rows if row['id']!=item['id'])):
                raise ValueError('Accepted content changed')
            proof=adapter.catalog_service.audit_locked_content_proofs(conn,build_id=build['id'])
            if tuple(proof.passed_item_ids)!=(item['id'],): raise ValueError('Host proof changed')
            requests=list(conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
                'WHERE target_fingerprint=? AND enabled=TRUE',(identity['targetFingerprint'],)).fetchall())
            if requests!=[{'subject':'math','skill_id':'fraction_ratio_percentage','variant_ordinal':1}]: raise ValueError('Scope changed')
            owners=list(conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
                'AND library_target_fingerprint=? FOR UPDATE',(build['id'],identity['targetFingerprint'])).fetchall())
            runtimes=list(conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? FOR UPDATE',(item['id'],)).fetchall())
            if len(owners)!=1 or len(runtimes)!=1: raise ValueError('Original owner/runtime is not unique')
            owner,runtime=owners[0],runtimes[0]
            if (owner.get('lease_token') or owner['status']!='running' or owner['stage']!='generating_content' or
                owner.get('superseded_at') or runtime['upstream_job_id']!=JOB or runtime.get('retired_at') or
                runtime['course_id']!=item['course_id'] or runtime['course_version']!=item['course_version'] or
                runtime['candidate_target_fingerprint']!=identity['targetFingerprint']): raise ValueError('Original authority changed')
            binding=json.loads(runtime['feature_manifest_json'])['paidBudget']
            authority=budget._authority(conn,binding['authorizationId'],now_ms())
            if json.loads(authority['scope_json'])!=identity['scope']: raise ValueError('Authorization changed')
            ledger=list(budget.repository.authorization_ledger(conn,binding['authorizationId']))
            _settled_ledger_sha256(ledger)
            previous=conn.execute('SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? '
                'AND event_type IN (?,?) ORDER BY created_at DESC,id DESC LIMIT 1',(owner['id'],EVENT,EVENT+'_pending')).fetchone()
            if previous:
                event=json.loads(previous['payload_json'])
                if (args.mode!='apply' or not saved or event['recoveryReceiptId']!=args.expected_sha or
                    runtime['id']!=saved['runtime']['id'] or owner['id']!=saved['owner']['id'] or saved.get('feedback')!=feedback): raise ValueError('Existing recovery requires its exact original SHA')
                if event['status']=='applied':
                    if runtime['status'] not in {'generating','ready'}: raise ValueError('A later failure needs diagnosis')
                    return {'applied':True,'reused':True,'sourceSha256':args.expected_sha}
                if runtime['status']!='recovering' or runtime['error_code']!='openmaic_agent_quota_resume_pending': raise ValueError('Pending recovery changed')
                current=saved
            else:
                if runtime['status']!='failed' or runtime['quality_status']!='rejected' or runtime['error_code']!='openmaic_formal_generation_failed': raise ValueError('Not the diagnosed failure')
                dispatches=list(conn.execute('SELECT * FROM learning_course_provider_dispatches WHERE build_item_id=? ORDER BY logical_attempt,phase_ordinal,id',(item['id'],)).fetchall())
                if len(dispatches)!=13 or any(row['status'] in {'reserved','dispatched','ambiguous'} for row in dispatches): raise ValueError('Content dispatches changed')
                events=list(conn.execute('SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? ORDER BY created_at,id',(owner['id'],)).fetchall())
                upstream=native(app.config,'plan',feedback=feedback)
                if (upstream['authorizationId']!=binding['authorizationId'] or upstream['buildItemId']!=item['id'] or
                    upstream['targetFingerprint']!=identity['targetFingerprint'] or upstream['runtimeRequestId']!=runtime['request_id']): raise ValueError('Native/backend mismatch')
                current={'schemaVersion':'mira.local.agent-budget-resume.v1','owner':dict(owner),'runtime':dict(runtime),
                    'item':dict(item),'dispatches':dispatches,'events':events,'ledger':ledger,'native':upstream,'feedback':feedback}
                current['sourceSha256']=digest(current)
                if args.expected_sha and current['sourceSha256']!=args.expected_sha: raise ValueError('Snapshot changed')
                ARCHIVES.mkdir(parents=True,exist_ok=True)
                path=ARCHIVES/('local-agent-budget-'+current['sourceSha256']+'.json')
                try:
                    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:
                        output.write(canonical(current));output.flush();os.fsync(output.fileno())
                except FileExistsError:
                    if json.loads(path.read_text())!=current: raise ValueError('Archive conflict')
                if args.mode=='plan': return {'applied':False,'sourceSha256':current['sourceSha256'],
                    'nativeSourceSha256':upstream['sourceSha256'],'sceneCount':upstream['sceneCount'],'ledgerCount':len(ledger)}
                now=now_ms()
                changed=conn.execute("UPDATE learning_openmaic_runtime_classrooms SET status='recovering',quality_status='pending_review',"
                    "error_code='openmaic_agent_quota_resume_pending',updated_at=? WHERE id=? AND status='failed' AND updated_at=?",(now,runtime['id'],runtime['updated_at']))
                if changed.rowcount!=1: raise ValueError('Runtime CAS rejected')
                changed=conn.execute('UPDATE learning_curriculum_preparation_plans SET next_run_at=?,updated_at=? WHERE id=? AND updated_at=? AND lease_token IS NULL',
                    (now,now,owner['id'],owner['updated_at']))
                if changed.rowcount!=1: raise ValueError('Owner CAS rejected')
                adapter.repository.append_event(conn,plan_id=owner['id'],event_type=EVENT+'_pending',stage='generating_content',payload=public_event(current,'pending'),now=now)
        if current.get('feedback')!=feedback: raise ValueError('Original feedback changed')
        result=native(app.config,'apply',current['native']['sourceSha256'],args.confirm_runtime_stopped,feedback)
        if result.get('applied') is not True: raise ValueError('Native continuation was not queued')
        with repo.transaction() as conn:
            changed=conn.execute("UPDATE learning_openmaic_runtime_classrooms SET status='generating',error_code=NULL,error_message_safe=NULL,updated_at=? "
                "WHERE id=? AND status='recovering' AND error_code='openmaic_agent_quota_resume_pending'",(now_ms(),current['runtime']['id']))
            if changed.rowcount!=1: raise ValueError('Runtime acknowledgement CAS rejected')
            adapter.repository.append_event(conn,plan_id=current['owner']['id'],event_type=EVENT,stage='generating_content',payload=public_event(current,'applied'),now=now_ms())
        return {'applied':True,'sourceSha256':current['sourceSha256'],'sceneCount':result['sceneCount'],'sameInstance':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('plan','apply'));parser.add_argument('--budget-policy',required=True)
    parser.add_argument('--expected-sha');parser.add_argument('--confirm-runtime-stopped',action='store_true')
    parser.add_argument('--feedback-file');parser.add_argument('--feedback-sha')
    args=parser.parse_args()
    if bool(args.feedback_file)!=bool(args.feedback_sha) or (args.feedback_sha and not re.fullmatch('[a-f0-9]{64}',args.feedback_sha)):
        parser.error('--feedback-file and --feedback-sha must be supplied together')
    if args.mode=='apply' and (not args.confirm_runtime_stopped or not re.fullmatch('[a-f0-9]{64}',args.expected_sha or '')):
        parser.error('apply requires --expected-sha and --confirm-runtime-stopped')
    try:
        with LOCK_PATH.open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            print(json.dumps(run(args),ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'stopped':True,'reason':str(error) if isinstance(error,ValueError) else type(error).__name__}));return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
