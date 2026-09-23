"""One EN2 HTTP-402 local transport terminal audit; the financial hold is unchanged."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

from content.learning_budget_policy import canonical, digest
from core.security import now_ms
from repositories.learning_budget_repository import LearningBudgetRepository

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'output/progressive-preview/saved-stage-english-slot2'
ARCHIVES = BASE / 'http402-terminal'
NATIVE = ROOT / 'openmaic-runtime/.runtime/OpenMAIC'
EVENT = 'http402_transport_terminal'
SCHEMA = 'mira.learning.exact-http402-transport-terminal.v1'
ITEM = 'catalog_build_item_d5a6b286d326400b49241b5d'
RUNTIME = 'omfc_8EsR81VIt_yHr1YpuYYAA5Jbyt3HkBfHiNuQgt4SlP4'
RESERVATION = 'a5d229086206479a8cf2937c92b3aec2d3962999cfd975bd5851af58325ef070'
AUTHORIZATION = 'ae9cf24415978b9cb0e24f9960bb61900fdf7604e969ede3188681b2fafabdd6'
REQUEST_SHA = 'da727a5dfbd3dea76adfbc3c760d97d8e6443c80480df7afcd137dd8e5c20a26'
DISPATCH = 'runtime:8610311a0e880bab2fe86b5e826b237dd050b306249aa2e8c7a348e2a6f92bef'
JOB = 'omformal_90ed56f8cb07a09d6c51296a'
JOB_SHA = 'a3fb84e1c4e1f16424aa255b9f035453109b7103a7d61c609cfcdff41aaec037'
FILES = {
    'source-audit.json': '889a83532086a9ae6ea29ba637d5b7988e1b6ccd0bd821e05220526ff82fa5b1',
    'six-scope-budget-audit.json': 'b5f57f930ba5bc6905b01a82380fc91056b0987b514afb0fcf3a797bb462fcf8',
    'terminal-blocker.json': '56f24c51d649870bb7c731da7772d92e540f0b310b0c4fa50b0acdae2dfa07ba',
    'original-native-job.json': JOB_SHA,
    'source-event-index.json': 'aec5a3b34c2cadb86f05bde9f19d374797262e071093e031fb25d0f9ba77b200',
}
TERMINAL_EVENT_HASHES = {
    8048: '31986f4ed6ed3ba81b0f13b5ab227d286d4d59e25eb9e5325b363445644f592b',
    8049: '09731db0c2ead2cbf877f550bbee55debc7de3af5abcaf41f323a3e3758496b4',
    8050: 'd4d7ed9d4a30533fd2156fff1989ba7884417332409d288630e05bfcd9c4bae8',
    8051: '973e9bd160f8975605b06f27fa74151da83604ae9605bae774393444d4c31067',
}


def terminal_events(index):
    entries = [e for e in index if int(e['seq']) in TERMINAL_EVENT_HASHES]
    require([int(e['seq']) for e in entries] == list(TERMINAL_EVENT_HASHES))
    require([e['type'] for e in entries] == ['message_end', 'turn_end', 'agent_end', 'session_end'])
    require(all(e['attempt'] == 1 and e['data_sha256'] == TERMINAL_EVENT_HASHES[int(e['seq'])] for e in entries))
    return entries


def require(ok, message='exact HTTP402 terminal evidence changed'):
    if not ok:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def basis():
    files = {}
    for name, expected in FILES.items():
        raw = (BASE / name).read_bytes()
        require(sha(raw) == expected, 'original archive changed: ' + name)
        files[name] = json.loads(raw)
    source = files['source-audit.json']; job = files['original-native-job.json']
    failure = files['terminal-blocker.json']
    scope = next(x for x in files['six-scope-budget-audit.json']['details'] if x['authorization']['id'] == AUTHORIZATION)
    row = next(x for x in scope['reservations'] if x['id'] == RESERVATION)
    require(source['identity']['job'] == JOB and source['identity']['runtime'] == RUNTIME
            and source['identity']['item'] == ITEM and source['sourceJobSha256'] == JOB_SHA)
    require(job['status'] == 'failed' and job['error'] == 'FORMAL_PROFESSIONAL_SESSION_FAILED:Insufficient Balance'
            and digest(job['formalInput']) == source['identity']['inputSha'])
    require(failure['httpStatus'] == 402 and failure['requestHostname'] == 'api.deepseek.com'
            and failure['requestPath'] == '/v1/chat/completions' and failure['retryable'] is False
            and failure['providerError'] == {'message': 'Insufficient Balance', 'type': 'unknown_error',
                                            'param': None, 'code': 'invalid_request_error'})
    require(row['state'] == 'unknown' and row['dispatch_id'] == DISPATCH and row['request_sha256'] == REQUEST_SHA
            and row['authorization_id'] == AUTHORIZATION and all(row[k] is None for k in
            ('actual_units_json', 'settlement_sha256', 'provider_request_id', 'settled_at')))
    # runner.ts uses the original session as the paid-budget namespace. This is
    # the exact JSON.stringify array used by mira-paid-budget.ts, not an inferred label.
    dispatch_bytes = json.dumps([AUTHORIZATION, source['identity']['session'], REQUEST_SHA],
                               ensure_ascii=False, separators=(',', ':')).encode()
    require('runtime:' + sha(dispatch_bytes) == DISPATCH)
    require(source['sourceEventIndexSha256'] == FILES['source-event-index.json'])
    ended = terminal_events(files['source-event-index.json'])
    require(row['created_at'] < row['dispatched_at'] < int(ended[0]['ts']) < int(ended[-1]['ts']))
    require(len(scope['reservations']) == 86 and sum(r['state'] == 'settled' for r in scope['reservations']) == 85)
    require(digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': scope['scope']}) == AUTHORIZATION)
    return source, job, scope, row


def native_proof(source, job):
    # Raw SELECTs only: never instantiate a store that performs schema writes.
    code = r"""const {Client}=require(process.argv[1]),fs=require('node:fs'),crypto=require('node:crypto'),{parseEnv}=require('node:util');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');let raw='';process.stdin.on('data',v=>raw+=v);process.stdin.on('end',async()=>{
const x=JSON.parse(raw),env=parseEnv(fs.readFileSync(x.env,'utf8')),db=new Client({connectionString:env.MIRA_OPENMAIC_AGENT_DATABASE_URL});
try{await db.connect();await db.query('BEGIN READ ONLY');const s=(await db.query('SELECT id,owner_id,prompt,status,attempt,stage_id,active_stage_id,lease_worker_id,deleted_at,cancel_requested_at,delivered_user_message_seq FROM agent_sessions WHERE id=$1',[x.session])).rows[0];
const st=(await db.query('SELECT id,owner_id,data FROM document_stages WHERE id=$1',[x.stage])).rows[0];const scenes=(await db.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id',[x.stage])).rows.map(r=>r.data);
const last=(await db.query('SELECT MAX(seq) AS seq FROM agent_session_events WHERE session_id=$1',[x.session])).rows[0].seq;
const terminalEvents=(await db.query("SELECT seq,type,attempt,ts,encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256 FROM agent_session_events WHERE session_id=$1 AND seq BETWEEN 8048 AND 8051 ORDER BY seq",[x.session])).rows;
const active=(await db.query("SELECT COUNT(*)::int AS n FROM agent_sessions WHERE deleted_at IS NULL AND status IN ('queued','running')")).rows[0].n;
console.log(JSON.stringify({sessionId:s.id,ownerId:s.owner_id,status:s.status,attempt:s.attempt,promptSha256:sha(s.prompt),sessionSha256:sha(JSON.stringify(s,null,2)+'\n'),lastEventSeq:last,terminalEvents,activeSessions:active,stageOwner:st.owner_id,documentSha256:sha(JSON.stringify({stage:st.data,scenes},null,2)+'\n')}));
}catch(e){process.stderr.write('Exact Native readonly evidence unavailable\n');process.exitCode=1}finally{await db.query('ROLLBACK');await db.end()}});"""
    result = subprocess.run(['node', '-e', code, str(NATIVE / 'node_modules/pg')],
        input=json.dumps({'env': str(ROOT / 'backend/.env'), 'session': source['identity']['session'], 'stage': source['identity']['stage']}),
        text=True, capture_output=True, timeout=25)
    require(result.returncode == 0, 'Native readonly terminal proof failed')
    proof = json.loads(result.stdout)
    # PostgreSQL jsonb::text hashing is deliberately preserved; Node JSON
    # canonicalization would produce different bytes for this original evidence.
    ended = terminal_events(proof['terminalEvents'])
    archived = terminal_events(json.loads((BASE / 'source-event-index.json').read_bytes()))
    require([{**e, 'seq': int(e['seq'])} for e in ended] == archived)
    require(proof['sessionId'] == source['identity']['session'] and proof['ownerId'] == source['identity']['owner']
            and proof['stageOwner'] == source['identity']['owner'] and proof['status'] == 'failed'
            and proof['sessionSha256'] == source['sourceSessionSha256'] and proof['promptSha256'] == source['promptSha256']
            and int(proof['lastEventSeq']) == int(source['lastEventSeq']) and proof['activeSessions'] == 0
            and proof['documentSha256'] == source['sourceDocumentSha256'])
    require(sha((NATIVE / 'data/classroom-jobs' / (JOB + '.json')).read_bytes()) == JOB_SHA)
    return proof


def events(conn):
    return [dict(r) for r in conn.execute('SELECT * FROM learning_budget_events WHERE reservation_id=? AND event_type=? ORDER BY id', (RESERVATION, EVENT)).fetchall()]


def current_rows(conn):
    r = conn.execute('SELECT * FROM learning_budget_reservations WHERE id=?', (RESERVATION,)).fetchone()
    a = conn.execute('SELECT * FROM learning_budget_authorizations WHERE id=?', (AUTHORIZATION,)).fetchone()
    require(r is not None and a is not None)
    return dict(r), dict(a)


def validate_current(plan, row, auth):
    require(row == plan['reservation'], 'the original unknown financial row changed')
    expected = dict(plan['authorization']); revoked = auth.get('revoked_at')
    require(revoked is None or type(revoked) is int and plan['capturedAt'] <= revoked <= now_ms())
    expected['revoked_at'] = revoked
    require(auth == expected, 'authorization scope, price, limit or identity changed')


def validate_plan(plan):
    source, job, saved, row = basis()
    require(set(plan) == {'schemaVersion', 'scope', 'sourceFiles', 'capturedAt', 'nativeProof', 'reservation',
                          'authorization', 'sourceEvents', 'runtime', 'settledSourceRowsSha256'})
    require(plan['schemaVersion'] == SCHEMA and plan['scope'] == 'local_transport_concurrency_only'
            and plan['sourceFiles'] == FILES and type(plan['capturedAt']) is int
            and plan['reservation'] == row and plan['authorization'] == saved['authorization'])
    proof = plan['nativeProof']
    ended = terminal_events(proof['terminalEvents'])
    require([{**e, 'seq': int(e['seq'])} for e in ended]
            == terminal_events(json.loads((BASE / 'source-event-index.json').read_bytes())))
    require(proof['status'] == 'failed' and proof['sessionSha256'] == source['sourceSessionSha256']
            and proof['documentSha256'] == source['sourceDocumentSha256'] and proof['activeSessions'] == 0
            and proof['sessionId'] == source['identity']['session'] and proof['ownerId'] == source['identity']['owner']
            and proof['promptSha256'] == source['promptSha256'] and int(proof['lastEventSeq']) == int(source['lastEventSeq']))
    require(plan['settledSourceRowsSha256'] == digest([r for r in saved['reservations'] if r['state'] == 'settled']))
    e = plan['sourceEvents']
    require([r['event_type'] for r in e] == ['reserved', 'dispatched', 'unknown']
            and all(r['reservation_id'] == RESERVATION for r in e)
            and json.loads(e[-1]['evidence_json']) == {'reasonCode': 'provider_result_unknown'})
    r = plan['runtime'];require(r['id'] == RUNTIME and r['upstream_job_id'] == JOB
        and r['candidate_build_item_id'] == ITEM and r['request_id'] == job['runtimeRequestId']
        and r['course_id'] == source['identity']['course'] and r['status'] in {'generating', 'failed'} and not r['retired_at'])
    return plan


def read_plan(identity):
    require(isinstance(identity, str) and len(identity) == 64 and all(c in '0123456789abcdef' for c in identity))
    plan = json.loads((ARCHIVES / (identity + '.json')).read_bytes());require(digest(plan) == identity)
    return validate_plan(plan)


def verified_http402_terminal_ids(conn, *, pending_rows):
    if not any(r.get('id') == RESERVATION and r.get('state') == 'unknown' for r in pending_rows):
        return set()
    try:
        es = events(conn);require(len(es) == 1)
        e = json.loads(es[0]['evidence_json'])
        require(set(e) == {'schemaVersion', 'auditSha256', 'reservationId'} and e['schemaVersion'] == SCHEMA and e['reservationId'] == RESERVATION)
        plan = read_plan(e['auditSha256']);require(es[0]['created_at'] >= plan['capturedAt'])
        validate_current(plan, *current_rows(conn))
        return {RESERVATION}
    except (RuntimeError, ValueError, KeyError, TypeError, OSError, StopIteration):
        return set()


def assert_selected_http402_terminal(conn, *, identity, runtime_id):
    _, _, saved, _ = basis()
    require(identity['buildItemId'] == ITEM and identity['scope'] == saved['scope'] and runtime_id == RUNTIME)
    pending = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')", (AUTHORIZATION,)).fetchall()]
    require(len(pending) == 1 and pending[0]['id'] == RESERVATION
            and verified_http402_terminal_ids(conn, pending_rows=pending) == {RESERVATION})


def preflight(conn):
    source, job, saved, row = basis()
    require(conn.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()['n'] == 0, 'active Provider request exists')
    current = [dict(r) for r in conn.execute('SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY created_at,id', (AUTHORIZATION,)).fetchall()]
    require(current == saved['reservations'], 'the original 85 settled calls or unknown hold changed')
    r, auth = current_rows(conn);require(r == row and auth == saved['authorization'])
    require(conn.execute('SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?', (ITEM,)).fetchone()['n'] == 0, 'already has a classroom receipt')
    runtime = conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?', (RUNTIME,)).fetchone();require(runtime is not None)
    e = [dict(r) for r in conn.execute('SELECT * FROM learning_budget_events WHERE reservation_id=? AND event_type<>? ORDER BY id', (RESERVATION, EVENT)).fetchall()]
    return validate_plan({'schemaVersion': SCHEMA, 'scope': 'local_transport_concurrency_only', 'sourceFiles': FILES,
        'capturedAt': now_ms(), 'nativeProof': native_proof(source, job), 'reservation': row, 'authorization': auth,
        'sourceEvents': e, 'runtime': dict(runtime), 'settledSourceRowsSha256': digest([r for r in current if r['state'] == 'settled'])})


def prepare(database):
    conn = database.connect()
    try:
        conn.execute('START TRANSACTION READ ONLY');require(not events(conn), 'terminal event already recorded')
        plan = preflight(conn)
    finally:conn.rollback();conn.close()
    identity = digest(plan);ARCHIVES.mkdir(parents=True, exist_ok=True)
    path = ARCHIVES / (identity + '.json')
    with path.open('x') as f:path.chmod(0o600);f.write(canonical(plan) + '\n')
    return {'status': 'prepared', 'auditSha256': identity, 'auditPath': str(path), 'providerCalls': 0,
            'databaseWrites': 0, 'financialState': 'unknown', 'fundsReleased': False}


def apply(database, expected_sha):
    plan = read_plan(expected_sha)
    with database.transaction() as conn:
        require(conn.execute('SELECT id FROM learning_budget_control WHERE id=1 FOR UPDATE').fetchone() is not None)
        prior = events(conn)
        if prior:
            require(len(prior) == 1 and json.loads(prior[0]['evidence_json']).get('auditSha256') == expected_sha
                    and verified_http402_terminal_ids(conn, pending_rows=[plan['reservation']]) == {RESERVATION})
            return {'status': 'already_recorded', 'auditSha256': expected_sha}
        current = preflight(conn)
        require({k: v for k, v in current.items() if k != 'capturedAt'} == {k: v for k, v in plan.items() if k != 'capturedAt'}, 'preflight changed')
        LearningBudgetRepository(database).event(conn, RESERVATION, EVENT,
            {'schemaVersion': SCHEMA, 'auditSha256': expected_sha, 'reservationId': RESERVATION}, now_ms())
        validate_current(plan, *current_rows(conn))
        require(verified_http402_terminal_ids(conn, pending_rows=[plan['reservation']]) == {RESERVATION})
    return {'status': 'recorded', 'auditSha256': expected_sha, 'financialState': 'unknown', 'fundsReleased': False,
            'providerCalls': 0, 'reservationUpdates': 0, 'authorizationUpdates': 0}
