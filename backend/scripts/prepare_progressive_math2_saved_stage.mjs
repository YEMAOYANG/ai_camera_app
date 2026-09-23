/** Exact attempt-two terminal document export. No stores, writes to databases,
 * HTTP, Provider calls or Native recovery operations are invoked here. */
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {parseEnv} from 'node:util';
import {readFileSync,writeFileSync,existsSync,mkdirSync,readdirSync,renameSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,join} from 'node:path';

const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const NATIVE=join(ROOT,'openmaic-runtime/.runtime/OpenMAIC');
const OUT=join(ROOT,'output/progressive-preview/saved-stage-math-slot2-attempt2');
const FIXED={jobId:'omformal_6cddfc21f47d63291444dfab',
  runtimeId:'omfc_QpzBHjJGUFhjAOYID7WAW7MNmD3lfDejGJuPv31Ku90',
  runtimeRequestId:'mira-formal-runtime-catalog_build_item_c38581679912c102b1d91061-attempt-2',
  buildItemId:'catalog_build_item_c38581679912c102b1d91061',
  courseId:'progressive_8f3566ae3da1bee0718067b9',
  packageId:'formal_runtime_package_f33d57932799cd5903ca18133e4ba7f5ad18f763a674ad22',
  sourceJobSha256:'ca3f4481cc7a50f0b232216dbf432688344f2bd1c455c82e35438677d2a3bd4a',
  formalInputSha256:'6e5b4d06023f3ca30d997d6efb088f19d31e446ae05a5fb6985a322b40551dcb',
  sessionId:'miraformal_0669fb604cef3bcc29a0605e5da607f49a8c4fb3e51b8506ab33242e5a7cb3ff',
  ownerId:'mira-formal-professional:0669fb604cef3bcc29a0605e5da607f49a8c4fb3e51b8506ab33242e5a7cb3ff',
  stageId:'stage-NjgpUvNeOs'};
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
  &&job.error==='FORMAL_AUDIO_ASR_INCOMPLETE:17:succeeded'&&job.runtimeRequestId===FIXED.runtimeRequestId
  &&job.formalInputSha256===FIXED.formalInputSha256&&qualitySha(job.formalInput)===FIXED.formalInputSha256
  &&spec.buildItemId===FIXED.buildItemId&&spec.course.id===FIXED.courseId&&spec.course.packageId===FIXED.packageId,
  'Exact failed attempt-two Native source changed');

const [mode,...args]=process.argv.slice(2);
demand((mode==='export'&&args.length===0)||(mode==='proposal'&&args.length===1),
  'Usage: node prepare_progressive_math2_saved_stage.mjs export | proposal REPAIRED_P4_HTML');
if(mode==='proposal'){
  const audit=JSON.parse(readFileSync(join(OUT,'source-audit.json')));
  const sourceBytes=readFileSync(join(OUT,'source-document.json')),source=JSON.parse(sourceBytes);
  demand(sha(sourceBytes)===audit.sourceDocumentSha256
    &&qualitySha(qualitySnapshot(source.stage,source.scenes))===audit.sourceSnapshotSha256,'Original document changed');
  const htmlPath=resolve(ROOT,args[0]),html=readFileSync(htmlPath,'utf8'),htmlSha256=sha(html);
  const scenes=structuredClone(source.scenes),p4=scenes.find(s=>s.id==='scene-p4');
  demand(p4&&typeof p4.content.html==='string'&&html.includes('<html'),'Exact p4 HTML required');
  p4.content.html=html;
  const widgetMatch=html.match(/<script\b[^>]*\bid=["']widget-config["'][^>]*>([\s\S]*?)<\/script>/i);
  demand(widgetMatch,'Repaired HTML widget configuration missing');
  const widgetConfig=JSON.parse(widgetMatch[1]);
  demand(widgetConfig&&typeof widgetConfig==='object'&&!Array.isArray(widgetConfig),'Invalid repaired widget configuration');
  p4.content.widgetConfig=widgetConfig;
  const target=scenes.find(s=>s.id==='scene-p5')?.actions.find(a=>a.id==='action_KkoZf9rU');
  demand(target?.type==='speech','Exact rejected p5 narration required');
  const oldText=target.text;
  target.text='先看每一份有多少，再数一共有多少份，最后把这两个量相乘，求出总量。';
  const mappings=[];
  function occurrences(value,text){
    if(value===text)return 1;
    if(Array.isArray(value))return value.reduce((n,v)=>n+occurrences(v,text),0);
    if(value&&typeof value==='object')return Object.values(value).reduce((n,v)=>n+occurrences(v,text),0);
    // Reject embedded references too, rather than silently changing JS/text.
    return typeof value==='string'&&value.includes(text)?1:0;
  }
  for(const scene of scenes)for(const action of scene.actions||[])if(action.type==='speech'){
    const originalId=action.id;
    demand(occurrences(source,originalId)===1&&occurrences({scenes},originalId)===1,
      'Speech action has a non-definition reference: '+originalId);
    const revisedId='action_'+qualitySha({sourceSnapshotSha256:audit.sourceSnapshotSha256,
      htmlSha256,originalId,text:action.text}).slice(0,40);
    action.id=revisedId;
    mappings.push({sceneId:scene.id,originalId,revisedId});
  }
  demand(mappings.length===23&&new Set(mappings.map(m=>m.revisedId)).size===23,'Expected 23 unique revised speech IDs');
  const ordered=value=>[...value].sort((a,b)=>a.order-b.order).map((scene,order)=>({...scene,order}));
  const oldAudio=buildLifecycleSegments({buildItemId:FIXED.buildItemId,subject:'math',stage:source.stage,scenes:ordered(source.scenes)});
  const newAudio=buildLifecycleSegments({buildItemId:FIXED.buildItemId,subject:'math',stage:source.stage,scenes:ordered(scenes)});
  const oldIds=new Set(oldAudio.segments.flatMap(s=>[s.ttsRequestId,s.asrRequestId]));
  demand(newAudio.segments.every(s=>!oldIds.has(s.ttsRequestId)&&!oldIds.has(s.asrRequestId)),
    'Revised audio would reuse an original request');
  for(let i=0;i<mappings.length;i++)Object.assign(mappings[i],{
    originalTtsRequestId:oldAudio.segments[i].ttsRequestId,originalAsrRequestId:oldAudio.segments[i].asrRequestId,
    revisedTtsRequestId:newAudio.segments[i].ttsRequestId,revisedAsrRequestId:newAudio.segments[i].asrRequestId});
  const proposal={scenes},proposalBytes=json(proposal);
  // Revert only the declared edits and require complete canonical equality.
  const restored=structuredClone(proposal);
  restored.scenes.find(s=>s.id==='scene-p4').content.html=source.scenes.find(s=>s.id==='scene-p4').content.html;
  restored.scenes.find(s=>s.id==='scene-p4').content.widgetConfig=source.scenes.find(s=>s.id==='scene-p4').content.widgetConfig;
  for(const scene of restored.scenes)for(const action of scene.actions||[]){
    const mapping=mappings.find(m=>m.revisedId===action.id);
    if(mapping)action.id=mapping.originalId;
    if(action.id==='action_KkoZf9rU')action.text=oldText;
  }
  demand(qualitySha(restored.scenes)===qualitySha(source.scenes),'Unapproved proposal change');
  const revisionAudit={schemaVersion:'mira.progressive-math2-saved-stage-proposal.v1',...FIXED,
    sourceSnapshotSha256:audit.sourceSnapshotSha256,sourceDocumentSha256:audit.sourceDocumentSha256,
    htmlPath,htmlSha256,widgetConfigSha256:qualitySha(widgetConfig),proposalSha256:sha(proposalBytes),
    narrationChange:{sceneId:'scene-p5',originalId:'action_KkoZf9rU',oldText,newText:target.text},
    speechIdMappings:mappings,originalAudioPreserved:true,newAudioRequired:true,
    preservedQuizContent:true,preservedFormalInput:true};
  immutable('repair-proposal-'+sha(proposalBytes)+'.json',proposalBytes);
  immutable('repair-audit-'+sha(json(revisionAudit))+'.json',json(revisionAudit));
  const recoveryDir=join(NATIVE,'data/formal-saved-stage-recoveries',FIXED.jobId);
  demand(!existsSync(recoveryDir)||!readdirSync(recoveryDir).some(name=>name==='completion.json'||/^complete.*\.claim$/.test(name)),
    'A completion was already attempted; do not replace its proposal');
  for(const [name,bytes] of [['repair-proposal.json',proposalBytes],['repair-audit.json',json(revisionAudit)]]){
    if(existsSync(join(OUT,name))){
      const previous=readFileSync(join(OUT,name));
      immutable(name.replace('.json','-'+sha(previous)+'.json'),previous);
    }
    const temp=join(OUT,name+'.tmp-'+process.pid);
    writeFileSync(temp,bytes,{flag:'wx',mode:0o600});renameSync(temp,join(OUT,name));
  }
  console.log(JSON.stringify({status:'proposal_prepared',providerCalls:0,databaseWrites:0,
    proposalPath:join(OUT,'repair-proposal.json'),proposalSha256:revisionAudit.proposalSha256,
    auditSha256:sha(json(revisionAudit)),speechIdCount:mappings.length}));
  process.exit(0);
}
const env=parseEnv(readFileSync(process.env.MIRA_OPENMAIC_PROVIDER_ENV_FILE||join(ROOT,'backend/.env'),'utf8'));
const {Client}=require('pg');
const client=new Client({connectionString:process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL||env.MIRA_OPENMAIC_AGENT_DATABASE_URL});
await client.connect();
try{
  await client.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const session=(await client.query('SELECT id,owner_id,prompt,status,attempt,stage_id,active_stage_id,lease_worker_id,deleted_at,cancel_requested_at FROM agent_sessions WHERE id=$1',[FIXED.sessionId])).rows[0];
  demand(session&&session.owner_id===FIXED.ownerId&&session.status==='succeeded'&&!session.lease_worker_id
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
  const audio=buildLifecycleSegments({buildItemId:FIXED.buildItemId,subject:'math',stage:source.stage,
    scenes:[...scenes].sort((a,b)=>a.order-b.order).map((scene,order)=>({...scene,order}))});
  demand(audio.segments.length===23,'Expected 23 original speech segments');
  const audit={schemaVersion:'mira.progressive-math2-saved-stage-source.v1',...FIXED,sourceSnapshotSha256,
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
