#!/usr/bin/env node
/** Retire only a complete archive's four derived objects after proving replacement coverage. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {ROOT,readConfig,storageIdentity} from './course-storage.mjs';

const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {S3Client,GetObjectCommand,HeadObjectCommand,DeleteObjectCommand}=require('@aws-sdk/client-s3');
const STATE=path.join(ROOT,'backend/data/course-storage');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const canonical=value=>JSON.stringify(value,(key,item)=>item&&!Array.isArray(item)&&typeof item==='object'?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const storage=config=>{const {prefix,...identity}=storageIdentity(config);return identity;};
const date=value=>/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(new Date(value).valueOf())&&new Date(value).toISOString().slice(0,10)===value;
const safe=value=>typeof value==='string'&&value.split('/').every(s=>s.trim()&&!['.','..'].includes(s)&&!/[\\\x00-\x1f\x7f-\x9f]/.test(s)&&Buffer.byteLength(s)<=255);
const identityKeys=['courseId','courseVersion','classroomId','releaseSha256'];
const savedIdentityKeys=['courseId','courseVersion','classroomId','contentKey','releaseSha256','sourceKind','sourceDigest','status'];
const missing=error=>error.$metadata?.httpStatusCode===404||['NotFound','NoSuchKey','NoSuchVersion'].includes(error.name);

function archiveIdentity(index){
 if(index.status==='generated_saved'){
  if(index.sourceKind!=='textbook_preview'||typeof index.sourceDigest!=='string'||!/^[a-f0-9]{64}$/.test(index.sourceDigest)||
     ['courseId','courseVersion','classroomId'].some(k=>typeof index[k]!=='string'||!index[k].trim())||
     !Object.hasOwn(index,'contentKey')||(index.contentKey!==null&&(typeof index.contentKey!=='string'||!/^[a-f0-9]{64}$/.test(index.contentKey)))||index.releaseSha256!==null)throw Error('A bound saved archive identity is required');
  return Object.fromEntries(savedIdentityKeys.map(k=>[k,index[k]]));
 }
 if(index.status!==undefined&&index.status!=='published')throw Error('Unknown archive status');
 if(identityKeys.some(k=>typeof index[k]!=='string'||!index[k])||!/^[a-f0-9]{64}$/.test(index.releaseSha256))throw Error('Published archive identity is required');
 return Object.fromEntries(identityKeys.map(k=>[k,index[k]]));
}

async function privateDirectory(directory){
 const absolute=path.resolve(directory);let current=path.parse(absolute).root;
 for(const segment of absolute.slice(current.length).split(path.sep).filter(Boolean)){
  current=path.join(current,segment);
  try{const stat=await fs.lstat(current);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('Retirement state contains a symlink');}
  catch(error){if(error.code!=='ENOENT')throw error;await fs.mkdir(current,{mode:0o700});}
 }
 return absolute;
}
async function readPrivate(filename){
 const absolute=path.resolve(filename);let current=absolute;
 while(current!==path.dirname(current)){const stat=await fs.lstat(current);if(stat.isSymbolicLink())throw Error('Retirement input contains a symlink');current=path.dirname(current);}
 const stat=await fs.stat(absolute);if(!stat.isFile()||stat.size>128*1024**2)throw Error('Retirement input is not a bounded file');
 return fs.readFile(absolute);
}
async function atomic(filename,value){
 await privateDirectory(path.dirname(filename));const temporary=filename+'.new-'+crypto.randomUUID();
 const handle=await fs.open(temporary,'wx',0o600);
 try{await handle.writeFile(typeof value==='string'||Buffer.isBuffer(value)?value:canonical(value)+'\n');await handle.sync();}finally{await handle.close();}
 await fs.rename(temporary,filename);const directory=await fs.open(path.dirname(filename),'r');try{await directory.sync();}finally{await directory.close();}
}
function publicRoles(index){
 const entries=index.generatedPublicFiles;
 if(index.schemaVersion!=='mira.course-archive.export.v1'||index.complete!==true||(index.missingSources||[]).length||!Array.isArray(entries)||entries.length!==4)throw Error('Exactly four complete archive objects are required');
 if(!/^[a-f0-9]{24,64}$/.test(index.archiveId))throw Error('Invalid archive identity');
 archiveIdentity(index);
 if(!safe(index.objectDirectory))throw Error('Invalid archive directory');
 const directory=index.objectDirectory.split('/'),named=directory.length===5&&date(directory[3]),legacy=directory.length===3&&date(directory[0]);
 if(!named&&!legacy)throw Error('Only the documented course archive layouts can be retired');
 const roles=new Map(),keys=new Set();
 for(const entry of entries){
  if(!safe(entry.relativePath)||!entry.relativePath.startsWith(index.objectDirectory+'/')||keys.has(entry.relativePath)||!/^[a-f0-9]{64}$/.test(entry.sha256)||!Number.isSafeInteger(entry.byteSize)||entry.byteSize<1||entry.byteSize>5*1024**3)throw Error('Invalid archive object');
  const suffix=entry.relativePath.slice(index.objectDirectory.length+1).split('/');
  if(named&&suffix.length!==1||legacy&&(suffix.length!==3||suffix[0]!=='完整课件'||!/^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}(?:\.\d{1,6})?$/.test(suffix[1])))throw Error('Archive key escapes its exact course directory');
  const match=suffix.at(-1).match(/-(课堂结构|归档清单|课程资料|完整课件)(?:-\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}(?:\.\d{1,6})?)?\.(json|zip)$/);
  if(!match||roles.has(match[1])||(match[1]==='完整课件'?(match[2]!=='zip'||entry.mimeType!=='application/zip'):(match[2]!=='json'||entry.mimeType!=='application/json')))throw Error('Only derived complete-course archive files may be retired');
  roles.set(match[1],entry);keys.add(entry.relativePath);
 }
 return roles;
}
async function capture(filename){
 const raw=await readPrivate(filename),index=JSON.parse(raw),roles=publicRoles(index);
 const parent=path.dirname(path.resolve(filename)),manifestPath=path.resolve(index.manifestPath);
 let manifestRaw;
 if(manifestPath.startsWith(parent+path.sep)){
  try{manifestRaw=await readPrivate(manifestPath);}catch(error){if(error.code!=='ENOENT')throw error;}
 }
 if(!manifestRaw)manifestRaw=await readPrivate(path.join(parent,'manifest.json'));
 const manifest=JSON.parse(manifestRaw);
 const saved=index.status==='generated_saved',manifestIdentityKeys=saved?identityKeys.concat('contentKey'):identityKeys;
 if(sha(manifestRaw)!==roles.get('归档清单').sha256||manifestRaw.length!==roles.get('归档清单').byteSize||manifest.schemaVersion!==index.schemaVersion||manifest.archiveId!==index.archiveId||manifest.complete!==true||(manifest.missingSources||[]).length||!Array.isArray(manifest.files)||manifestIdentityKeys.some(k=>manifest.identity?.[k]!==index[k])||saved&&manifest.status!==index.status)throw Error('Archive original-file manifest is not bound to its public object');
 for(const file of manifest.files)if(typeof file.original!=='boolean'||typeof file.sourceIdentity!=='string'||!file.sourceIdentity||!/^[a-f0-9]{64}$/.test(file.sha256)||!Number.isSafeInteger(file.byteSize)||file.byteSize<0||saved&&(['sourceKind','mimeType'].some(k=>typeof file[k]!=='string'||!file[k])))throw Error('Original-file inventory is invalid');
 return {index,raw,indexSha256:sha(raw),manifest,manifestRaw,roles,filename:path.resolve(filename)};
}
async function receipt(capture,state,config){
 const base=path.join(state,'archive-transfers',capture.index.archiveId),id=storage(config);
 const frozen=capture.filename.startsWith(path.resolve(state,'archive-retirements')+path.sep)?[path.join(path.dirname(capture.filename),'verification.json')]:[];
 const candidates=[...frozen,path.join(base,'verifications',sha(canonical(id)),capture.indexSha256+'.json'),path.join(base,'verifications',capture.indexSha256+'.json'),path.join(base,'verified-complete.json')];
 for(const filename of candidates){
  let raw;try{raw=await readPrivate(filename);}catch(error){if(error.code==='ENOENT')continue;throw error;}
  const value=JSON.parse(raw),expected=new Map(capture.index.generatedPublicFiles.map(e=>[e.relativePath,e]));
  if(value.schemaVersion!=='mira.course-archive.verification.v1'||value.complete!==true||value.archiveId!==capture.index.archiveId||value.indexSha256!==capture.indexSha256||canonical(value.storage)!==canonical(id)||['courseId','courseVersion'].some(k=>value[k]!==capture.index[k])||(value.sourceDigest??null)!==(capture.index.sourceDigest??null)||!Array.isArray(value.objects)||value.objects.length!==4)continue;
  const objects=new Map();
  for(const object of value.objects){
   const entry=expected.get(object.objectKey);
   if(!entry||objects.has(object.objectKey)||object.sha256!==entry.sha256||object.byteSize!==entry.byteSize||typeof object.etag!=='string'||!object.etag||('versionId'in object&&(typeof object.versionId!=='string'||!object.versionId)))throw Error('Archive verification object identity is incomplete');
   objects.set(object.objectKey,object);
  }
  if(value.byteSize!==[...expected.values()].reduce((sum,e)=>sum+e.byteSize,0))throw Error('Archive verification byte total differs');
  return {raw,value,objects};
 }
 throw Error('Exact durable archive verification is required');
}
const tuple=(file,strict)=>canonical([file.sourceIdentity,file.sha256,file.byteSize,...(strict?[file.sourceKind,file.mimeType]:[])]);
export function originalCoverage(oldManifest,replacementManifest,{strict=false}={}){
 const originals=oldManifest.files.filter(f=>f.original),replacement=new Set(replacementManifest.files.filter(f=>f.original).map(f=>tuple(f,strict)));
 if(!originals.length||originals.some(file=>!replacement.has(tuple(file,strict))))throw Error('Replacement does not cover every original byte');
 return {originalFiles:originals.length,replacementOriginalFiles:replacementManifest.files.filter(f=>f.original).length};
}
async function context(options,dependencies){
 const config=dependencies.config||readConfig(),state=dependencies.state||STATE;
 const old=await capture(options.index),replacement=await capture(options.replacementIndex);
 const identity=archiveIdentity(old.index);
 if(canonical(identity)!==canonical(archiveIdentity(replacement.index)))throw Error('Replacement archive identity must match');
 const oldKeys=new Set(old.index.generatedPublicFiles.map(e=>e.relativePath));
 if(replacement.index.generatedPublicFiles.some(e=>oldKeys.has(e.relativePath)))throw Error('Replacement must use disjoint object keys');
 const coverage=originalCoverage(old.manifest,replacement.manifest,{strict:old.index.status==='generated_saved'});
 const oldReceipt=await receipt(old,state,config),replacementReceipt=await receipt(replacement,state,config);
 const id=sha(canonical({oldIndexSha256:old.indexSha256,replacementIndexSha256:replacement.indexSha256,storage:storage(config)}));
 const directory=await privateDirectory(path.join(state,'archive-retirements',id));
 const binding={schemaVersion:'mira.course-archive.retirement.v1',id,storage:storage(config),identity,oldIndexSha256:old.indexSha256,replacementIndexSha256:replacement.indexSha256,oldReceiptSha256:sha(oldReceipt.raw),replacementReceiptSha256:sha(replacementReceipt.raw),oldObjects:old.index.generatedPublicFiles.map(e=>({objectKey:e.relativePath,sha256:e.sha256,byteSize:e.byteSize})),replacementObjects:replacement.index.generatedPublicFiles.map(e=>({objectKey:e.relativePath,sha256:e.sha256,byteSize:e.byteSize})),...coverage};
 const filename=path.join(directory,'plan.json');
 try{if(canonical(JSON.parse(await readPrivate(filename)))!==canonical(binding))throw Error('Retirement journal binding changed');}catch(error){if(error.code!=='ENOENT')throw error;await atomic(filename,binding);}
 for(const [name,raw]of [['old-index.json',old.raw],['replacement-index.json',replacement.raw],['old-originals.json',old.manifestRaw],['replacement-originals.json',replacement.manifestRaw],['old-verification.json',oldReceipt.raw],['replacement-verification.json',replacementReceipt.raw]]){
  const target=path.join(directory,name);try{if(!Buffer.from(await readPrivate(target)).equals(raw))throw Error('Retirement input snapshot changed');}catch(error){if(error.code!=='ENOENT')throw error;await atomic(target,raw);}
 }
 // These byte-identical snapshots make a restart independent of disposable
 // export directories and the mutable "latest verification" pointer.
 for(const [name,captured,verified]of [['old',old,oldReceipt],['replacement',replacement,replacementReceipt]]){
  for(const [filename,raw]of [['index.json',captured.raw],['manifest.json',captured.manifestRaw],['verification.json',verified.raw]]){
   const target=path.join(directory,'inputs',name,filename);
   try{if(!Buffer.from(await readPrivate(target)).equals(raw))throw Error('Retirement frozen input changed');}catch(error){if(error.code!=='ENOENT')throw error;await atomic(target,raw);}
  }
 }
 const client=dependencies.client||new S3Client({endpoint:config.endpoint,region:config.region,forcePathStyle:true,credentials:{accessKeyId:config.accessKeyId,secretAccessKey:config.secretAccessKey},maxAttempts:2,requestChecksumCalculation:'WHEN_REQUIRED',responseChecksumValidation:'WHEN_REQUIRED'});
 return {config,state,old,replacement,oldReceipt,replacementReceipt,binding,directory,client};
}
async function fullGet(capture,verified,ctx){
 const response=await ctx.client.send(new GetObjectCommand({Bucket:ctx.config.bucket,Key:capture.relativePath,IfMatch:verified.etag,...(verified.versionId?{VersionId:verified.versionId}:{})}));
 let bytes=0;const hash=crypto.createHash('sha256');
 for await(const chunk of response.Body){bytes+=chunk.length;if(bytes>capture.byteSize){response.Body.destroy?.();throw Error('Archive remote bytes changed');}hash.update(chunk);}
 if(bytes!==capture.byteSize||hash.digest('hex')!==capture.sha256||response.ETag!==verified.etag||(verified.versionId&&response.VersionId!==verified.versionId))throw Error('Archive remote identity or bytes changed');
}
async function head(entry,verified,ctx){
 const response=await ctx.client.send(new HeadObjectCommand({Bucket:ctx.config.bucket,Key:entry.relativePath,...(verified.versionId?{VersionId:verified.versionId}:{})}));
 if(response.ContentLength!==entry.byteSize||response.ETag!==verified.etag||(verified.versionId&&response.VersionId!==verified.versionId))throw Error('Archive remote identity changed; retained');
}
async function verifyReplacement(ctx){for(const entry of ctx.replacement.index.generatedPublicFiles)await fullGet(entry,ctx.replacementReceipt.objects.get(entry.relativePath),ctx);}

export async function planArchiveRetirement(options,dependencies={}){
 const ctx=await context(options,dependencies);
 if(options.verifyRemote){
  await verifyReplacement(ctx);
  for(const entry of ctx.old.index.generatedPublicFiles)await fullGet(entry,ctx.oldReceipt.objects.get(entry.relativePath),ctx);
 }
 return {...ctx.binding,journalDirectory:ctx.directory,resumeIndex:path.join(ctx.directory,'inputs/old/index.json'),resumeReplacementIndex:path.join(ctx.directory,'inputs/replacement/index.json'),remoteVerified:options.verifyRemote===true,deleteExecuted:false,retirableBytes:ctx.old.index.generatedPublicFiles.reduce((sum,e)=>sum+e.byteSize,0)};
}
export async function retireArchive(options,dependencies={}){
 if(options.execute!==true)throw Error('Explicit retirement execution is required');
 const ctx=await context(options,dependencies),lockPath=path.join(ctx.directory,'execute.lock');
 const lock=await fs.open(lockPath,'wx',0o600);
 try{
  await lock.writeFile(canonical({pid:process.pid,createdAt:new Date().toISOString()})+'\n');await lock.sync();
  // Every replacement byte is freshly checked before the first delete, even
  // when resuming a journal. Sequential retirement stops immediately on error.
  await verifyReplacement(ctx);let removed=0,resumed=0;
  for(const entry of ctx.old.index.generatedPublicFiles){
   const verified=ctx.oldReceipt.objects.get(entry.relativePath),recordPath=path.join(ctx.directory,sha(entry.relativePath)+'.json');
   const exact={planId:ctx.binding.id,objectKey:entry.relativePath,sha256:entry.sha256,byteSize:entry.byteSize,etag:verified.etag,...(verified.versionId?{versionId:verified.versionId}:{})};
   let record;try{record=JSON.parse(await readPrivate(recordPath));}catch(error){if(error.code!=='ENOENT')throw error;}
   if(record&&Object.entries(exact).some(([k,v])=>record[k]!==v))throw Error('Retirement progress identity changed');
   try{await fullGet(entry,verified,ctx);}
   catch(error){
    if(missing(error)&&record&&['delete-intent','retired'].includes(record.status)){await atomic(recordPath,{...exact,status:'retired',at:new Date().toISOString()});resumed++;continue;}
    throw error;
   }
   for(const replacement of ctx.replacement.index.generatedPublicFiles)await head(replacement,ctx.replacementReceipt.objects.get(replacement.relativePath),ctx);
   await head(entry,verified,ctx);
   await atomic(recordPath,{...exact,status:'delete-intent',at:new Date().toISOString()});
   await ctx.client.send(new DeleteObjectCommand({Bucket:ctx.config.bucket,Key:entry.relativePath,IfMatch:verified.etag,...(verified.versionId?{VersionId:verified.versionId}:{})}));
   try{await head(entry,verified,ctx);throw Error('Retired archive object remains present');}catch(error){if(!missing(error))throw error;}
   await atomic(recordPath,{...exact,status:'retired',at:new Date().toISOString()});removed++;
  }
  const result={schemaVersion:'mira.course-archive.retired.v1',planId:ctx.binding.id,removedObjects:removed,resumedObjects:resumed,complete:true,completedAt:new Date().toISOString()};
  await atomic(path.join(ctx.directory,'retired-complete.json'),result);return result;
 }finally{await lock.close();await fs.unlink(lockPath);}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const argv=process.argv.slice(2),command=argv.shift(),options={};
 try{
  while(argv.length){const key=argv.shift();if(['--verify-remote','--execute'].includes(key)){options[key==='--execute'?'execute':'verifyRemote']=true;continue;}if(!['--index','--replacement-index'].includes(key)||!argv.length)throw Error('Invalid retirement option');options[key==='--index'?'index':'replacementIndex']=argv.shift();}
  if(!options.index||!options.replacementIndex)throw Error('Exact old and replacement indices are required');
  const result=command==='plan'?await planArchiveRetirement(options):command==='retire'?await retireArchive(options):(()=>{throw Error('Expected plan or retire');})();
  console.log(JSON.stringify(result));
 }catch(error){console.error(JSON.stringify({error:'course_archive_retirement_failed',reason:error.message}));process.exitCode=1;}
}
