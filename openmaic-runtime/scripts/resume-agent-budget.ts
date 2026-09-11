/** Local operator only. Run with Native stopped; never calls a model or a job API. */
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { promises as fs } from 'node:fs';
import { resolve, join } from 'node:path';
import { createConnection } from 'node:net';

const NATIVE = resolve(__dirname, '../.runtime/OpenMAIC');
const nativeRequire = createRequire(join(NATIVE, 'package.json'));
const JOB = 'omformal_d57c133cbf917beb4cb30bb0';
const SESSION = 'miraformal_5eeb45b676d6fd8ba8fc68c2770936778b3c7f04d5276d6f8e5eccc4ebb5077e';
const EVENT = 'mira_formal_agent_budget_resume';
const ERRORS = new Set(['FORMAL_AGENT_CONTEXT_BUDGET_EXHAUSTED', 'FORMAL_AGENT_DISPATCH_BUDGET_EXHAUSTED']);
const ARCHIVES = join(NATIVE, 'data/formal-agent-budget-resume');
const JOB_FILE = join(NATIVE, 'data/classroom-jobs', `${JOB}.json`);
export const canonical = (value: unknown): string => JSON.stringify(value, (_k, v) =>
  v && typeof v === 'object' && !Array.isArray(v)
    ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : v);
export const sha = (value: unknown) => createHash('sha256').update(canonical(value)).digest('hex');
const fail = (code = 'SOURCE_MISMATCH'): never => { throw new Error(`LOCAL_AGENT_BUDGET_RESUME_${code}`); };

export function validateSnapshot(s: any) {
  const { job, session, events, entries, stages, scenes, outlines } = s;
  if (job?.id !== JOB || session?.id !== SESSION || session.status !== 'failed' ||
      !ERRORS.has(session.error) || job.status !== 'failed' ||
      job.error !== `FORMAL_PROFESSIONAL_SESSION_FAILED:${session.error}` ||
      Number(session.attempt) !== 3 || session.lease_worker_id || job.result || !job.completedAt ||
      !Array.isArray(stages) || stages.length !== 1 || !Array.isArray(scenes) || scenes.length !== 10 ||
      !Array.isArray(outlines) || !job.budgetResume || !job.prestageRecovery) fail();
  const input = job.formalInput;
  if (!input || sha(input) !== job.formalInputSha256 ||
      `miraformal_${createHash('sha256').update(`${job.runtimeRequestId}\n${canonical(input)}`).digest('hex')}` !== SESSION ||
      session.owner_id !== `mira-formal-professional:${SESSION.slice(11)}` ||
      stages[0].owner_id !== session.owner_id || scenes.some((scene: any) => scene.stage_id !== stages[0].id) ||
      outlines.some((outline: any) => outline.stage_id !== stages[0].id)) fail();
  const contract = JSON.parse(input.requirement), course = contract.teachingBrief?.course;
  if (course?.gradeCode !== 'primary_6' || course.subject !== 'math' ||
      course.skillId !== 'fraction_ratio_percentage' || course.difficultyCode !== 'standard') fail();
  if (events.at(-1)?.type !== 'session_end' || events.at(-1)?.data?.error !== session.error) fail();
  const starts = events.filter((e: any) => e.type === 'tool_execution_start');
  for (const start of starts) {
    if (events.filter((e: any) => e.type === 'tool_execution_end' && e.data?.toolCallId === start.data?.toolCallId).length !== 1) fail('UNFINISHED_TOOL');
  }
  if (starts.filter((e: any) => e.data?.toolName === 'web_search').length !== 4 ||
      events.filter((e: any) => e.type === 'mira_formal_research_search').length !== 1) fail();
  const last = entries.filter((e: any) => e.type === 'message').at(-1)?.data?.message;
  if (last?.role !== 'assistant' || last.stopReason !== 'error' || last.errorMessage !== session.error || last.content?.length !== 0) fail();
  return { jobId: JOB, sessionId: SESSION, sourceError: session.error, stageId: stages[0].id,
    sceneCount: scenes.length, searchAttemptCount: 4, remainingSearchAttemptCount: 0,
    buildItemId: contract.buildItemId, courseId: course.id, courseVersion: course.version,
    targetFingerprint: contract.targetFingerprint, runtimeRequestId: job.runtimeRequestId,
    authorizationId: input.paidBudget?.authorizationId, formalInputSha256: job.formalInputSha256,
    stageSha256: sha(stages), scenesSha256: sha(scenes), entriesSha256: sha(entries), eventsSha256: sha(events) };
}

async function archive(file: string, value: unknown) {
  await fs.mkdir(ARCHIVES, { recursive: true, mode: 0o700 });
  try { await fs.writeFile(file, canonical(value), { flag: 'wx', mode: 0o600 }); }
  catch (error) { if ((error as any).code !== 'EEXIST' || sha(JSON.parse(await fs.readFile(file, 'utf8'))) !== sha(value)) throw error; }
}
async function atomicJob(job: unknown) {
  const temp = `${JOB_FILE}.${process.pid}.tmp`;
  await fs.writeFile(temp, canonical(job), {mode:0o600}); await fs.rename(temp, JOB_FILE);
}
async function stopped() {
  for (const port of [3100,3101]) await new Promise<void>((done, reject) => {
    const socket = createConnection({host:'127.0.0.1',port});
    socket.once('connect',()=>{socket.destroy();reject(new Error('LOCAL_AGENT_BUDGET_RESUME_RUNTIME_RUNNING'));});
    socket.once('error',(e:any)=>{socket.destroy();e.code==='ECONNREFUSED'?done():reject(e);});
    socket.setTimeout(2000,()=>{socket.destroy();reject(new Error('LOCAL_AGENT_BUDGET_RESUME_STOP_UNPROVEN'));});
  });
}
async function budgetReady(authorizationId: string) {
  const base = new URL(process.env.MIRA_BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000');
  if (!['localhost','127.0.0.1'].includes(base.hostname)) fail('BACKEND_BOUNDARY');
  const response = await fetch(new URL('/internal/learning/budget/context',base), {method:'POST',redirect:'error',
    headers:{'Content-Type':'application/json','X-Mira-Internal-Token':process.env.MIRA_INTERNAL_API_TOKEN || '',
      'X-Mira-Internal-Source':'openmaic-runtime-gateway'}, body:JSON.stringify({authorizationId}),signal:AbortSignal.timeout(15000)});
  const result = await response.json();
  if (!response.ok || result.ok!==true || result.budget?.authorizationId!==authorizationId ||
      result.budget.purpose!=='production' || result.budget.aggregateLimitsEnabled!==false || result.budget.unsettledReservationCount!==0) fail('OBSERVATION_CONTEXT_REQUIRED');
}
async function snapshot(conn: any, lock: boolean): Promise<any> {
  const session=(await conn.query(`SELECT * FROM agent_sessions WHERE id=$1${lock?' FOR UPDATE':''}`,[SESSION])).rows[0];
  const stages=(await conn.query('SELECT * FROM document_stages WHERE owner_id=$1 ORDER BY id',[session?.owner_id])).rows;
  return {job:JSON.parse(await fs.readFile(JOB_FILE,'utf8')),session,stages,
    scenes:(await conn.query('SELECT * FROM document_scenes WHERE stage_id=ANY($1::text[]) ORDER BY stage_id,scene_order,id',[stages.map((s:any)=>s.id)])).rows,
    outlines:(await conn.query('SELECT * FROM document_outlines WHERE stage_id=ANY($1::text[]) ORDER BY stage_id',[stages.map((s:any)=>s.id)])).rows,
    events:(await conn.query('SELECT * FROM agent_session_events WHERE session_id=$1 ORDER BY seq',[SESSION])).rows,
    entries:(await conn.query('SELECT * FROM agent_session_entries WHERE session_id=$1 ORDER BY seq',[SESSION])).rows};
}
export async function run(input: any) {
  if (!['plan','apply'].includes(input.mode) || (input.mode==='apply' &&
      (input.confirmRuntimeStopped!==true || !/^[a-f0-9]{64}$/.test(input.expectedSha || '')))) fail('ARGUMENTS');
  if (input.mode==='apply') await stopped();
  if(input.feedback && (typeof input.feedback.text!=='string' || !input.feedback.text.trim() ||
      Buffer.byteLength(input.feedback.text)>32768 ||
      createHash('sha256').update(input.feedback.text).digest('hex')!==input.feedback.sha256)) fail('FEEDBACK_CHANGED');
  const connectionString=process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL || '';
  const url=new URL(connectionString);
  if (!['localhost','127.0.0.1','[::1]'].includes(url.hostname) || url.pathname!=='/openmaic_mira') fail('DATABASE_BOUNDARY');
  const {Client}=nativeRequire('pg'); const conn=new Client({connectionString,connectionTimeoutMillis:5000});
  // The package exposes this subpath only under its ESM import condition.
  // The local CJS/tsx operator uses the exact installed source, before any write.
  const {PgAgentSessionStore}=nativeRequire(join(NATIVE,'packages/@openmaic/storage/src/agent-session/pg.ts'));
  const store=new PgAgentSessionStore(conn,{withTransaction:async(body:any)=>body(conn)});
  let written=false, committed=false, originalJob:any;
  try {
    await conn.connect(); await conn.query(input.mode==='plan'?'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY':'BEGIN');
    if(input.mode==='apply') await conn.query('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',[`mira.formal-classroom-completion:${JOB}`]);
    const current=await snapshot(conn,input.mode==='apply');
    current.feedback=input.feedback ?? null;
    const applied=current.events.find((e:any)=>e.type===EVENT);
    if(applied){
      if(input.expectedSha!==applied.data.sourceSha256 || current.job.agentBudgetResume?.sourceSha256!==input.expectedSha ||
        (applied.data.feedbackSha256 ?? null)!==(input.feedback?.sha256 ?? null) ||
        !['queued','running','succeeded'].includes(current.session.status))fail('ALREADY_USED');
      await conn.query('ROLLBACK');return {...applied.data,applied:true,reused:true};
    }
    if(current.job.agentBudgetResume){
      if(input.expectedSha!==current.job.agentBudgetResume.sourceSha256)fail();
      const saved=JSON.parse(await fs.readFile(join(ARCHIVES,`${input.expectedSha}.json`),'utf8'));
      if(sha(saved)!==input.expectedSha)fail();current.job=saved.job;
    }
    const proof=validateSnapshot(current), sourceSha256=sha(current); originalJob=current.job;
    if(input.expectedSha && input.expectedSha!==sourceSha256)fail('SNAPSHOT_CHANGED');
    await archive(join(ARCHIVES,`${sourceSha256}.json`),current);
    if(input.mode==='plan'){await conn.query('ROLLBACK');return {...proof,sourceSha256,feedbackSha256:input.feedback?.sha256 ?? null,applied:false};}
    await budgetReady(proof.authorizationId);
    const others=(await conn.query("SELECT COUNT(*)::int AS count FROM agent_sessions WHERE status IN ('queued','running') AND deleted_at IS NULL")).rows[0];
    if(others.count!==0)fail('ACTIVE_SESSION');
    const audit={...proof,sourceSha256,feedbackSha256:input.feedback?.sha256 ?? null,resumedAt:new Date().toISOString()};
    await atomicJob({...originalJob,status:'running',step:'generating_scenes',error:undefined,completedAt:undefined,
      updatedAt:audit.resumedAt,agentBudgetResume:audit});written=true;
    if(input.feedback) await store.appendUserMessage(SESSION,{text:input.feedback.text,delivery:'queued',
      clientRequestId:`operator-feedback:${input.feedback.sha256}`});
    if(!await store.requeueForRetry(SESSION))fail('CAS');
    await store.appendControlEvent(SESSION,{type:EVENT,ts:Date.now(),data:audit});
    await conn.query('COMMIT');committed=true;return {...audit,applied:true};
  }catch(error){
    await conn.query('ROLLBACK').catch(()=>{});if(written&&!committed)await atomicJob(originalJob);
    const diagnostic={mode:input.mode,sourceSha256:input.expectedSha ?? null,written,committed,
      name:(error as any)?.name,code:(error as any)?.code,
      detail:String((error as any)?.stack || error).slice(0,12000)
        .replace(/Bearer\s+\S+/gi,'Bearer [redacted]')
        .replace(/(postgres(?:ql)?:\/\/)[^@\s]+@/gi,'$1[redacted]@')};
    await archive(join(ARCHIVES,`${Date.now()}-operator-failure.json`),diagnostic).catch(()=>{});
    throw error;
  }
  finally{await conn.end();}
}
if (require.main===module) {
  let body='';process.stdin.setEncoding('utf8');process.stdin.on('data',chunk=>body+=chunk);
  process.stdin.on('end',()=>run(JSON.parse(body)).then(result=>console.log(JSON.stringify(result)))
    .catch(error=>{console.error(/^LOCAL_AGENT_BUDGET_RESUME_[A-Z_]+$/.test(error.message)?error.message:'LOCAL_AGENT_BUDGET_RESUME_FAILED');process.exitCode=1;}));
}
