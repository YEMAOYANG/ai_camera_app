#!/usr/bin/env node
/** Upload and verify complete course exports; read/ack native durable snapshots. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {ROOT,readConfig,storageIdentity} from './course-storage.mjs';

const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {S3Client,HeadObjectCommand,PutObjectCommand,GetObjectCommand}=require('@aws-sdk/client-s3');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const canonical=value=>JSON.stringify(value,(key,item)=>item && !Array.isArray(item) && typeof item==='object' ? Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])) : item);
const TYPES={'.zip':'application/zip','.json':'application/json','.html':'text/html','.md':'text/markdown','.txt':'text/plain'};
const STATE=path.join(ROOT,'backend/data/course-storage');
const privateId=id=>typeof id==='string' && /^[A-Za-z0-9_-]{8,128}$/.test(id);
const storage=c=>{const {prefix,...identity}=storageIdentity(c);return identity;};

async function atomicJson(filename,value){
  await fsp.mkdir(path.dirname(filename),{recursive:true,mode:0o700});
  const temporary=filename+'.new-'+process.pid;
  const fd=await fsp.open(temporary,'wx',0o600);
  try{await fd.writeFile(JSON.stringify(value)+'\n');await fd.sync();}finally{await fd.close();}
  await fsp.rename(temporary,filename);
  const directory=await fsp.open(path.dirname(filename),'r');try{await directory.sync();}finally{await directory.close();}
}
export function archiveKey(key){
  if(typeof key!=='string')return false;
  const p=key.split('/');
  if(p.length!==6 || !/^\d{4}-\d{2}-\d{2}$/.test(p[3]))return false;
  const date=new Date(p[3]);if(!Number.isFinite(date.valueOf()) || date.toISOString().slice(0,10)!==p[3])return false;
  return p.every(s=>s.trim() && !['.','..'].includes(s) && !/[\\\x00-\x1f\x7f-\x9f]/.test(s) && Buffer.byteLength(s)<=255)
    && Object.hasOwn(TYPES,path.extname(p.at(-1)).toLowerCase())
    && !p.some(s=>/^(?:\.env(?:\..*)?|owner\.cookies|.*\.pem|.*\.key)$/i.test(s));
}
async function realFile(filename,roots){
  const absolute=path.resolve(filename),canonical=await fsp.realpath(absolute);
  if(canonical!==absolute || !roots.some(r=>canonical.startsWith(r+path.sep)))throw Error('Archive file escapes its private export workspace');
  let current=absolute;
  while(!roots.includes(current)){
    const stat=await fsp.lstat(current);if(stat.isSymbolicLink())throw Error('Archive source contains a symlink');
    current=path.dirname(current);
  }
  const fd=await fsp.open(absolute,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try{const stat=await fd.stat({bigint:true});if(!stat.isFile())throw Error('Archive source is not a regular file');return {fd,stat};}catch(e){await fd.close();throw e;}
}
async function sourceHash(opened){
  const h=crypto.createHash('sha256');let size=0;
  for await(const b of opened.fd.createReadStream({start:0,autoClose:false})){h.update(b);size+=b.length;}
  return {sha256:h.digest('hex'),byteSize:size};
}
const sameStat=(a,b)=>['dev','ino','size','mtimeNs','ctimeNs'].every(k=>a[k]===b[k]);
async function fullRemote(client,c,e,expected){
  const r=await client.send(new GetObjectCommand({Bucket:c.bucket,Key:e.relativePath,...(expected?{IfMatch:expected.etag,...(expected.versionId?{VersionId:expected.versionId}:{})}:{})}));
  let size=0;const h=crypto.createHash('sha256');
  for await(const b of r.Body){size+=b.length;if(size>e.byteSize){r.Body.destroy?.();throw Error('Remote complete-course bytes or identity differ');}h.update(b);}
  if(size!==e.byteSize || h.digest('hex')!==e.sha256 || !r.ETag || (expected && r.ETag!==expected.etag) || (expected?.versionId && r.VersionId!==expected.versionId))throw Error('Remote complete-course bytes or identity differ');
  return {objectKey:e.relativePath,sha256:e.sha256,byteSize:size,etag:r.ETag,...(r.VersionId?{versionId:r.VersionId}:{})};
}
export async function uploadArchive(indexFilename,dependencies={}){
  const c=dependencies.config || readConfig(),state=dependencies.state || STATE;
  const client=dependencies.client || new S3Client({endpoint:c.endpoint,region:c.region,forcePathStyle:true,credentials:{accessKeyId:c.accessKeyId,secretAccessKey:c.secretAccessKey},maxAttempts:3,requestChecksumCalculation:'WHEN_REQUIRED',responseChecksumValidation:'WHEN_REQUIRED'});
  const allowed=dependencies.allowedRoots || [path.join(state,'archives'),...(process.env.MIRA_TASK_TMPDIR?[await fsp.realpath(process.env.MIRA_TASK_TMPDIR)]:[])];
  const indexRaw=await fsp.readFile(indexFilename),index=JSON.parse(indexRaw);
  if(index.schemaVersion!=='mira.course-archive.export.v1' || index.complete!==true || !privateId(index.archiveId) || (index.missingSources || []).length || !Array.isArray(index.generatedPublicFiles) || !index.generatedPublicFiles.length)throw Error('A complete validated course export is required');
  const entries=index.generatedPublicFiles,keys=new Set();
  for(const e of entries){
    if(!archiveKey(e.relativePath) || keys.has(e.relativePath) || !/^[a-f0-9]{64}$/.test(e.sha256) || !Number.isSafeInteger(e.byteSize) || e.byteSize<1 || e.byteSize>5*1024**3 || e.mimeType!==TYPES[path.extname(e.relativePath).toLowerCase()])throw Error('Invalid complete-course export entry');
    keys.add(e.relativePath);
  }
  if(!entries.some(e=>e.mimeType==='application/zip') || !entries.some(e=>e.mimeType==='application/json'))throw Error('Complete course ZIP and structure JSON are both required');
  const destination=path.join(state,'archive-transfers',index.archiveId);await fsp.mkdir(destination,{recursive:true,mode:0o700});
  const verified=[];let total=0;
  for(const e of entries){
    const opened=await realFile(e.localPath,allowed);
    try{
      const checksum=await sourceHash(opened);
      if(checksum.sha256!==e.sha256 || checksum.byteSize!==e.byteSize || !sameStat(opened.stat,await opened.fd.stat({bigint:true})))throw Error('Complete-course source changed');
      let head;try{head=await client.send(new HeadObjectCommand({Bucket:c.bucket,Key:e.relativePath}));}catch(err){if(err.$metadata?.httpStatusCode!==404)throw err;}
      if(!head){
        await client.send(new PutObjectCommand({Bucket:c.bucket,Key:e.relativePath,Body:opened.fd.createReadStream({start:0,autoClose:false}),ContentLength:e.byteSize,ContentType:e.mimeType,Metadata:{sha256:e.sha256},ChecksumSHA256:Buffer.from(e.sha256,'hex').toString('base64'),IfNoneMatch:'*'}));
      }
      if(!sameStat(opened.stat,await opened.fd.stat({bigint:true})))throw Error('Complete-course source changed during upload');
      verified.push(await fullRemote(client,c,e));total+=e.byteSize;
      process.stderr.write(JSON.stringify({archiveId:index.archiveId,verifiedFiles:verified.length,totalFiles:entries.length,verifiedBytes:total})+'\n');
    }finally{await opened.fd.close();}
  }
  let result={schemaVersion:'mira.course-archive.verification.v1',archiveId:index.archiveId,courseId:index.courseId || null,courseVersion:index.courseVersion || null,sourceDigest:index.sourceDigest || null,indexSha256:hash(indexRaw),storage:storage(c),verifiedAt:new Date().toISOString(),objects:verified,byteSize:total,complete:true};
  const verificationPath=path.join(destination,'verifications',hash(canonical(result.storage)),result.indexSha256+'.json');
  try{
    const previous=JSON.parse(await fsp.readFile(verificationPath));
    const withoutTime=({verifiedAt,...value})=>value;
    if(canonical(withoutTime(previous))!==canonical(withoutTime(result)))throw Error('Immutable course verification conflicts');
    result=previous;
  }catch(error){if(error.code!=='ENOENT')throw error;await atomicJson(verificationPath,result);}
  await atomicJson(path.join(destination,'verified-complete.json'),result);return result;
}

function dotenv(filename,key){
  if(!fs.existsSync(filename))return '';
  for(const line of fs.readFileSync(filename,'utf8').split(/\r?\n/)){
    const m=line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);if(m?.[1]===key)return m[2].replace(/^(['"])(.*)\1$/,'$2');
  }return '';
}
async function nativeClient(){
  const {Client}=require('pg');
  const envfile=path.join(ROOT,'backend/.env');
  const url=process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL || dotenv(envfile,'MIRA_OPENMAIC_AGENT_DATABASE_URL');
  if(!url || !['postgres:','postgresql:'].includes(new URL(url).protocol))throw Error('Native archive database configuration unavailable');
  const client=new Client({connectionString:url,statement_timeout:30000,connectionTimeoutMillis:10000});await client.connect();return client;
}
export async function archiveEvents({limit=10,ackId,sourceDigest,afterId=0}={}){
  if(!Number.isInteger(limit)||limit<1||limit>100)throw Error('Invalid event limit');
  const db=await nativeClient();
  try{
    if(ackId!==undefined){
      if(!/^\d+$/.test(String(ackId)) || !/^[a-f0-9]{64}$/.test(sourceDigest || ''))throw Error('Exact event identity required');
      const r=await db.query('UPDATE mira_course_archive_events SET acknowledged_at=coalesce(acknowledged_at,now()) WHERE id=$1 AND source_digest=$2 RETURNING id',[ackId,sourceDigest]);
      return {acknowledged:r.rows.length===1};
    }
    if(!/^\d+$/.test(String(afterId)))throw Error('Invalid archive cursor');
    const r=await db.query('SELECT id,source_kind,session_id,stage_id,stage_revision,source_digest,snapshot_json,created_at FROM mira_course_archive_events WHERE acknowledged_at IS NULL AND id>$2 ORDER BY id LIMIT $1',[limit,afterId]);
    return {events:r.rows};
  }finally{await db.end();}
}
export async function savedStages({limit=25,afterStageId='',client}={}){
  if(!Number.isInteger(limit)||limit<1||limit>100 || typeof afterStageId!=='string' || (afterStageId && !/^[A-Za-z0-9_.:-]+$/.test(afterStageId)))throw Error('Invalid saved-stage cursor');
  const db=client || await nativeClient();
  try{
    await db.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
    const result=await db.query(`SELECT stage.id,stage.data,stage.updated_at,revision.rev AS revision,outline.data AS outline,
      COALESCE((SELECT jsonb_agg(scene.data ORDER BY scene.scene_order,scene.id)
        FROM document_scenes scene WHERE scene.stage_id=stage.id),'[]'::jsonb) AS scenes
      FROM document_stages stage JOIN document_stage_revision revision ON revision.stage_id=stage.id
      LEFT JOIN document_outlines outline ON outline.stage_id=stage.id
      WHERE stage.id>$1 AND EXISTS(SELECT 1 FROM document_scenes scene WHERE scene.stage_id=stage.id)
      ORDER BY stage.id LIMIT $2`,[afterStageId,limit]);
    const stages=result.rows.map(row=>{
      if(row.data?.id!==row.id || !Array.isArray(row.scenes) || !row.scenes.length || row.scenes.some(s=>s.stageId!==row.id))throw Error('Saved-stage identity mismatch');
      const {dslVersion,...stage}=row.data;
      const outline=row.outline && typeof row.outline==='object' && !Array.isArray(row.outline)?Object.fromEntries(Object.entries(row.outline).filter(([k])=>k!=='producerRef')):row.outline;
      const snapshot={id:row.id,stage,scenes:row.scenes,...(dslVersion===undefined?{}:{dslVersion}),...(outline==null?{}:{outline})};
      const date=new Date(Number(row.updated_at));
      return {stage_id:row.id,stage_revision:String(row.revision),source_digest:hash(canonical(snapshot)),snapshot_json:snapshot,created_at:Number.isFinite(date.valueOf())?date.toISOString():new Date().toISOString()};
    });
    await db.query('ROLLBACK');return {stages};
  }finally{if(!client)await db.end();}
}
function options(argv){const command=argv.shift(),o={command};while(argv.length){const key=argv.shift();if(!key.startsWith('--') || !argv.length)throw Error('Expected named option');o[key.slice(2)]=argv.shift();}return o;}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const o=options(process.argv.slice(2));
  Promise.resolve().then(async()=>{
    if(o.command==='upload')return uploadArchive(o.index);
    if(o.command==='events')return archiveEvents({limit:Number(o.limit || 10),afterId:o['after-id'] || 0});
    if(o.command==='ack')return archiveEvents({ackId:o.id,sourceDigest:o.digest});
    if(o.command==='saved-stages')return savedStages({limit:Number(o.limit || 25),afterStageId:o['after-stage-id'] || ''});
    throw Error('Unknown course archive operation');
  }).then(result=>console.log(JSON.stringify(result))).catch(()=>{console.error(JSON.stringify({error:'course_archive_operation_failed'}));process.exitCode=1;});
}
