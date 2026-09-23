/** Exact English first-set terminal document export. No stores, writes to databases,
 * HTTP, Provider calls or Native recovery operations are invoked here. */
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {parseEnv} from 'node:util';
import {readFileSync,writeFileSync,existsSync,mkdirSync,readdirSync,renameSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,join} from 'node:path';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const NATIVE=join(ROOT,'openmaic-runtime/.runtime/OpenMAIC');
const OUT=join(ROOT,'output/progressive-preview/saved-stage-english-slot1');
const FIXED={jobId:'omformal_35329ccda267db6155963636',
  runtimeId:'omfc__9FoaAfdhcHc5krhoDgSXbI9u6R3hoPXemPj3cQMr9o',
  runtimeRequestId:'mira-formal-runtime-catalog_build_item_4b59d735f1373e60196aa25a-attempt-1',
  buildItemId:'catalog_build_item_4b59d735f1373e60196aa25a',
  courseId:'progressive_0d05776662c086c2260ae732',
  packageId:'formal_runtime_package_6eccac9bc153d15ea547fe3a738636226dbf862caab187d8',
  sourceJobSha256:'9229b9a216abfaa5e7b30a87140e758a7b2d67186843f5fef1c06d8b7f0e1ab1',
  formalInputSha256:'ec788e0b8393230e870a2f221cfe1329d1b40263ab814485c9d8b1671f6c414e',
  sessionId:'miraformal_232f8120d6c3b73196ccc60b06740e695fe52d97db911af5ca282f05fb4f645e',
  ownerId:'mira-formal-professional:232f8120d6c3b73196ccc60b06740e695fe52d97db911af5ca282f05fb4f645e',
  stageId:'stage-McsF1obUqo'};
const sha=x=>createHash('sha256').update(x).digest('hex');
const json=x=>JSON.stringify(x,null,2)+'\n';
const demand=(condition,message)=>{if(!condition)throw Error(message);};
function immutable(name,bytes){
  const p=join(OUT,name),b=Buffer.from(bytes);
  if(existsSync(p)){demand(readFileSync(p).equals(b),'Existing archive differs: '+name);return;}
  writeFileSync(p,b,{flag:'wx',mode:0o600});
}
process.chdir(NATIVE);
const require=createRequire(join(NATIVE,'package.json'));
require('tsx/cjs');require(join(ROOT,'openmaic-runtime/scripts/native-operator-esm-compat.cjs'));
const {qualitySnapshot,qualitySha}=require(join(NATIVE,'lib/server/mira-formal-quality-contract.ts'));
const {buildLifecycleSegments}=require(join(NATIVE,'lib/server/mira-formal-audio-lifecycle.ts'));
const raw=readFileSync(join(NATIVE,'data/classroom-jobs',FIXED.jobId+'.json'));
const job=JSON.parse(raw),spec=JSON.parse(job.formalInput.requirement);
demand(sha(raw)===FIXED.sourceJobSha256&&job.id===FIXED.jobId&&job.status==='failed'
  &&job.error.startsWith('FORMAL_QUALITY_FINAL_SNAPSHOT_REJECTED:')&&job.runtimeRequestId===FIXED.runtimeRequestId
  &&job.formalInputSha256===FIXED.formalInputSha256&&qualitySha(job.formalInput)===FIXED.formalInputSha256
  &&spec.buildItemId===FIXED.buildItemId&&spec.course.id===FIXED.courseId&&spec.course.packageId===FIXED.packageId,
  'Exact terminal English source changed');

const [mode,...args]=process.argv.slice(2);
demand(mode==='export'&&args.length===0,
  'Usage: node export_progressive_english1_saved_stage.mjs export');
const env=parseEnv(readFileSync(process.env.MIRA_OPENMAIC_PROVIDER_ENV_FILE||join(ROOT,'backend/.env'),'utf8'));
const {Client}=require('pg');
const client=new Client({connectionString:process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL||env.MIRA_OPENMAIC_AGENT_DATABASE_URL});
await client.connect();
try{
  await client.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const session=(await client.query('SELECT id,owner_id,prompt,status,attempt,stage_id,active_stage_id,lease_worker_id,deleted_at,cancel_requested_at FROM agent_sessions WHERE id=$1',[FIXED.sessionId])).rows[0];
  demand(session&&session.owner_id===FIXED.ownerId&&['succeeded','failed','cancelled'].includes(session.status)&&!session.lease_worker_id
    &&!session.deleted_at&&!session.cancel_requested_at&&!session.active_stage_id,'Terminal source session required');
  const rows=(await client.query('SELECT id,owner_id,data FROM document_stages WHERE id=$1',[FIXED.stageId])).rows;
  demand(rows.length===1&&rows[0].owner_id===FIXED.ownerId,'Exact source stage owner required');
  const scenes=(await client.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id',[FIXED.stageId])).rows.map(r=>r.data);
  demand(scenes.length===8,'Expected eight original scenes');
  const events=(await client.query("SELECT seq,type,attempt,encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256 FROM agent_session_events WHERE session_id=$1 ORDER BY seq",[FIXED.sessionId])).rows;
  const source={stage:rows[0].data,scenes},snapshot=qualitySnapshot(source.stage,scenes);
  const sourceSnapshotSha256=qualitySha(snapshot);
  // Normal formal promotion uses contiguous scene order; retain the unmodified
  // document above, and project only order for the old audio identity audit.
  const audio=buildLifecycleSegments({buildItemId:FIXED.buildItemId,subject:'english',stage:source.stage,
    scenes:[...scenes].sort((a,b)=>a.order-b.order).map((scene,order)=>({...scene,order}))});
  demand(audio.segments.length>0,'Original speech segments missing');
  const audit={schemaVersion:'mira.progressive-english1-saved-stage-source.v1',...FIXED,sourceSnapshotSha256,
    session:{...session,prompt:undefined,promptSha256:sha(session.prompt)},events,
    sourceDocumentSha256:sha(json(source)),audio};
  mkdirSync(OUT,{recursive:true});
  immutable('original-native-job.json',raw);
  immutable('source-document.json',json(source));
  immutable('source-snapshot.json',json(snapshot));
  immutable('source-audit.json',json(audit));
  const manifest={jobId:FIXED.jobId,sourceJobSha256:FIXED.sourceJobSha256,sessionId:FIXED.sessionId,
    stageId:FIXED.stageId,sourceSnapshotSha256,repairPath:'repair-proposal.json'};
  immutable('manifest.json',json(manifest));
  console.log(JSON.stringify({status:'exported',providerCalls:0,databaseWrites:0,directory:OUT,
    sourceSnapshotSha256,sourceDocumentSha256:audit.sourceDocumentSha256,sourceAuditSha256:sha(json(audit)),
    sceneCount:scenes.length,speechCount:audio.segments.length,manifestPath:join(OUT,'manifest.json')}));
}finally{await client.query('ROLLBACK');await client.end();}
