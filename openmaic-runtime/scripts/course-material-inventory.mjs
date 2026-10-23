#!/usr/bin/env node
/** Enumerate fixed material dependencies of one verified course producer; never write. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const NATIVE=path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC');
const require=createRequire(path.join(NATIVE,'package.json'));
const PREFIX='openmaic-runtime/.runtime/OpenMAIC/data/';
const ID=/^[A-Za-z0-9_.:-]{1,255}$/;
const SHA=/^[a-f0-9]{64}$/;
const MAX_MATERIALS=4096;
const MIME=/^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/;
const canonical=value=>JSON.stringify(value,(_key,item)=>item&&!Array.isArray(item)&&typeof item==='object'
  ? Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const fail=()=>{throw Error('course_material_inventory_invalid');};

function safeKey(key,prefix){
  if(typeof key!=='string'||!key.startsWith(prefix)||Buffer.byteLength(key)>3072||
    /[\\\x00-\x1f\x7f-\x9f]/.test(key)||key.split('/').some(part=>!part||part==='.'||part==='..'))fail();
  return key;
}
function materialMime(key){
  if(key.endsWith('/text.md'))return 'text/markdown';
  const encoded=key.split('/').at(-1)?.match(/^raw\.([A-Za-z0-9_-]+)$/)?.[1];
  if(!encoded)fail();
  const bytes=Buffer.from(encoded,'base64url');
  if(bytes.toString('base64url')!==encoded)fail();
  const mime=bytes.toString('utf8');
  if(!MIME.test(mime)||mime.length>128)fail();
  return mime.toLowerCase();
}
function displayName(value,fallback){
  const text=typeof value==='string'?value.trim():'';
  return (text||fallback).slice(0,500);
}

/** Explicit frozen bindings come from the already-verified Backend request.
 * Stage discovery uses Native producer/save/create receipts; matching an owner
 * alone never discovers another session's materials.
 */
export async function inventoryCourseMaterials(input,{client}={}){
  if(!input||typeof input!=='object'||Array.isArray(input)||
    Object.keys(input).some(key=>!['sessionId','stageId','sourceDigest','bindingKind'].includes(key))||
    (input.sessionId!==undefined&&!ID.test(input.sessionId))||!ID.test(input.stageId??'')||
    (input.bindingKind!==undefined&&!['frozen_authoring','native_event'].includes(input.bindingKind))||
    (input.sourceDigest!==undefined&&!SHA.test(input.sourceDigest)))fail();
  if(!client)fail();
  await client.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  try{
    const relations=await client.query(`SELECT to_regclass('agent_sessions') AS sessions,
      to_regclass('agent_session_materials') AS materials,to_regclass('owner_material') AS owners,
      to_regclass('mira_course_archive_events') AS events,to_regclass('agent_session_events') AS session_events`);
    if(!relations.rows[0]?.sessions){
      if(input.sessionId)fail();
      return {schemaVersion:'mira.course-material-inventory.v1',boundSessions:[],materials:[],dependencySha256:sha(canonical([]))};
    }
    const stages=await client.query(`SELECT stage.owner_id,outline.data->>'producerRef' AS producer_ref
      FROM document_stages stage LEFT JOIN document_outlines outline ON outline.stage_id=stage.id
      WHERE stage.id=$1 AND stage.data->>'id'=stage.id`,[input.stageId]);
    if(stages.rows.length>1)fail();
    const candidates=await client.query(`SELECT id,owner_id,stage_id,active_stage_id FROM agent_sessions
      WHERE ($2::text IS NULL OR id=$2) AND ($4::text IS NULL OR length($4::text)=64) AND (
        stage_id=$1 OR active_stage_id=$1 OR id=$3 OR ($6::text='frozen_authoring' AND id=$2)
        ${relations.rows[0]?.events?`OR EXISTS(SELECT 1 FROM mira_course_archive_events event
          WHERE event.session_id=agent_sessions.id AND event.stage_id=$1
            AND ($4::text IS NULL OR event.source_digest=$4))`:''}
        ${relations.rows[0]?.session_events?`OR EXISTS(SELECT 1 FROM agent_session_events event
          WHERE event.session_id=agent_sessions.id AND event.type='library_changed'
            AND event.data->>'change'='stage_created' AND event.data->>'stageId'=$1)`:''}
      ) ORDER BY id LIMIT $5`,[input.stageId,input.sessionId??null,stages.rows[0]?.producer_ref??null,
        input.sourceDigest??null,MAX_MATERIALS+1,input.bindingKind??null]);
    if(candidates.rows.length>MAX_MATERIALS||(input.sessionId&&candidates.rows.length!==1))fail();
    const materials=[];
    const boundSessions=[];
    for(const session of candidates.rows){
      if(!ID.test(session.id??'')||typeof session.owner_id!=='string'||!session.owner_id)fail();
      // A material edit session cannot acquire another owner's course by
      // naming its id. Missing historic stages require an exact saved event.
      if(stages.rows.length&&stages.rows[0].owner_id!==session.owner_id){
        if(input.sessionId)fail();
        continue;
      }
      if(!stages.rows.length){
        if(!relations.rows[0]?.events){if(input.sessionId)fail();continue;}
        const event=await client.query(`SELECT 1 FROM mira_course_archive_events WHERE session_id=$1
          AND stage_id=$2 AND ($3::text IS NULL OR source_digest=$3) LIMIT 1`,
        [session.id,input.stageId,input.sourceDigest??null]);
        if(event.rows.length!==1){if(input.sessionId)fail();continue;}
      }
      const owner=session.owner_id;
      boundSessions.push(session.id);
      if(!relations.rows[0]?.materials)continue;
      const result=await client.query(`SELECT id,session_id,kind,title,text_asset_id,raw_asset_id,derived_from
        FROM agent_session_materials WHERE session_id=$1 ORDER BY id LIMIT $2`,[session.id,MAX_MATERIALS+1]);
      if(result.rows.length>MAX_MATERIALS)fail();
      const ids=new Set(result.rows.map(row=>row.id));
      for(const row of result.rows){
        if(!ID.test(row.id??'')||row.session_id!==session.id||
          (row.derived_from&&!ids.has(row.derived_from)))fail();
        for(const [field,kind]of [['raw_asset_id','raw'],['text_asset_id','text']]){
          if(!row[field])continue;
          const key=safeKey(row[field],`materials/${session.id}/`);
          materials.push({sourcePath:PREFIX+key,mimeType:materialMime(key),
            displayName:displayName(row.title,kind==='text'?'提取文本':'原始材料'),
            materialId:row.id,kind:row.kind,role:kind});
        }
      }
      if(ids.size&&relations.rows[0]?.owners){
        const owners=await client.query(`SELECT id,mime,bytes,original_name,oss_key,sha256 FROM owner_material
          WHERE owner_id=$1 AND id=ANY($2::text[]) AND status='ready' AND deleted_at IS NULL ORDER BY id`,[owner,[...ids]]);
        for(const row of owners.rows){
          const bytes=Number(row.bytes);
          if(!ID.test(row.id??'')||!ids.has(row.id)||!MIME.test(row.mime??'')||
            !SHA.test(row.sha256??'')||!Number.isSafeInteger(bytes)||bytes<1)fail();
          const key=safeKey(row.oss_key,`materials/${owner}/`);
          materials.push({sourcePath:PREFIX+key,mimeType:row.mime.toLowerCase(),
            displayName:displayName(row.original_name,'原始上传材料'),originalName:displayName(row.original_name,'原始上传材料'),
            materialId:row.id,kind:'source',role:'owner',byteSize:bytes,sha256:row.sha256});
        }
      }
      if(materials.length>MAX_MATERIALS*3)fail();
    }
    const unique=new Map();
    for(const record of materials){
      const previous=unique.get(record.sourcePath);
      if(previous&&(previous.mimeType!==record.mimeType||previous.materialId!==record.materialId))fail();
      unique.set(record.sourcePath,record);
    }
    const entries=[...unique.values()].sort((a,b)=>a.sourcePath<b.sourcePath?-1:a.sourcePath>b.sourcePath?1:0);
    return {schemaVersion:'mira.course-material-inventory.v1',boundSessions,materials:entries,
      dependencySha256:sha(canonical(entries))};
  }finally{await client.query('ROLLBACK');}
}

async function configuration(){
  let text='';try{text=await fs.readFile(path.join(ROOT,'backend/.env'),'utf8');}catch(error){if(error.code!=='ENOENT')throw error;}
  const line=text.split(/\r?\n/).find(value=>/^\s*MIRA_OPENMAIC_AGENT_DATABASE_URL\s*=/.test(value));
  const stored=line?.replace(/^\s*MIRA_OPENMAIC_AGENT_DATABASE_URL\s*=\s*/,'').replace(/^(['"])(.*)\1$/,'$2');
  const url=process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL||stored;
  if(!url||!['postgres:','postgresql:'].includes(new URL(url).protocol))fail();
  return url;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  Promise.resolve().then(async()=>{
    if(process.argv.length!==2)fail();
    const chunks=[];let bytes=0;
    for await(const chunk of process.stdin){bytes+=chunk.length;if(bytes>4096)fail();chunks.push(chunk);}
    const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const {Client}=require('pg');
    const client=new Client({connectionString:await configuration(),statement_timeout:30000,connectionTimeoutMillis:10000});
    try{await client.connect();return await inventoryCourseMaterials(input,{client});}finally{await client.end();}
  }).then(result=>process.stdout.write(JSON.stringify(result)+'\n')).catch(()=>{
    process.stderr.write(JSON.stringify({error:'course_material_inventory_failed'})+'\n');process.exitCode=1;
  });
}
