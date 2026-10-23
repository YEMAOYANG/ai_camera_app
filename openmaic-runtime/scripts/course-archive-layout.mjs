#!/usr/bin/env node
/** Relocate verified complete archives without rebuilding or deleting their original objects. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {ROOT,readConfig,storageIdentity} from './course-storage.mjs';
import {archiveKey} from './course-archive.mjs';

const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {S3Client,HeadObjectCommand,GetObjectCommand,CopyObjectCommand,PutObjectCommand}=require('@aws-sdk/client-s3');
const STATE=path.join(ROOT,'backend/data/course-storage');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const canonical=value=>JSON.stringify(value,(key,item)=>item&&!Array.isArray(item)&&typeof item==='object'?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const storage=config=>{const {prefix,...identity}=storageIdentity(config);return identity;};
const identityKeys=['courseId','courseVersion','classroomId','contentKey','releaseSha256'];
const absent=error=>error.$metadata?.httpStatusCode===404||['NotFound','NoSuchKey','NoSuchVersion'].includes(error.name);
const conditionFailed=error=>error.$metadata?.httpStatusCode===412;
const within=(filename,root)=>filename.startsWith(root+path.sep);
const directoryValid=value=>typeof value==='string'&&value.split('/').length===5&&archiveKey(value+'/archive.json');

async function privateDirectory(directory){
 const absolute=path.resolve(directory);let current=path.parse(absolute).root;
 for(const segment of absolute.slice(current.length).split(path.sep).filter(Boolean)){
  current=path.join(current,segment);
  try{const stat=await fsp.lstat(current);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('Archive relocation state contains a symlink');}
  catch(error){if(error.code!=='ENOENT')throw error;await fsp.mkdir(current,{mode:0o700});}
 }
 return absolute;
}
async function readPrivate(filename,roots){
 const absolute=path.resolve(filename);
 if(!roots.some(root=>within(absolute,root)))throw Error('Archive relocation input escapes its private roots');
 let current=absolute;
 while(current!==path.dirname(current)){if((await fsp.lstat(current)).isSymbolicLink())throw Error('Archive relocation input contains a symlink');current=path.dirname(current);}
 const handle=await fsp.open(absolute,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{const stat=await handle.stat();if(!stat.isFile()||stat.size>128*1024**2)throw Error('Archive relocation input is not a bounded regular file');return await handle.readFile();}finally{await handle.close();}
}
async function atomic(filename,value){
 await privateDirectory(path.dirname(filename));const temporary=filename+'.new-'+crypto.randomUUID();
 const handle=await fsp.open(temporary,'wx',0o600);
 try{await handle.writeFile(Buffer.isBuffer(value)?value:canonical(value)+'\n');await handle.sync();}finally{await handle.close();}
 await fsp.rename(temporary,filename);const directory=await fsp.open(path.dirname(filename),'r');try{await directory.sync();}finally{await directory.close();}
}
async function immutable(filename,bytes,roots){
 try{if(!bytes.equals(await readPrivate(filename,roots)))throw Error('Archive relocation immutable input conflicts');}
 catch(error){if(error.code!=='ENOENT')throw error;await atomic(filename,bytes);}
}
function validateIndex(index){
 if(index.schemaVersion!=='mira.course-archive.export.v1'||index.complete!==true||(index.missingSources||[]).length||!/^[A-Za-z0-9_-]{8,128}$/.test(index.archiveId)||!directoryValid(index.objectDirectory)||!/^[a-f0-9]{64}$/.test(index.sourceDigest||'')||!Array.isArray(index.generatedPublicFiles)||index.generatedPublicFiles.length!==4)throw Error('Exactly four verified complete archive objects are required');
 if(['courseId','courseVersion','classroomId'].some(k=>typeof index[k]!=='string'||!index[k]))throw Error('Archive course identity is required');
 const roles=new Map(),keys=new Set();
 for(const entry of index.generatedPublicFiles){
  const basename=entry.relativePath?.slice(index.objectDirectory.length+1),match=basename?.match(/-(课堂结构|归档清单|课程资料|完整课件)(?:-\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}(?:\.\d{1,6})?)?\.(json|zip)$/);
  if(!archiveKey(entry.relativePath)||!entry.relativePath.startsWith(index.objectDirectory+'/')||basename.includes('/')||!match||roles.has(match[1])||keys.has(entry.relativePath)||!/^[a-f0-9]{64}$/.test(entry.sha256)||!Number.isSafeInteger(entry.byteSize)||entry.byteSize<1||entry.byteSize>5*1024**3||(match[1]==='完整课件'?(entry.mimeType!=='application/zip'||match[2]!=='zip'):(entry.mimeType!=='application/json'||match[2]!=='json')))throw Error('Invalid complete archive object identity');
  roles.set(match[1],entry);keys.add(entry.relativePath);
 }
 return roles;
}
async function capture(indexFilename,state,config,roots){
 const filename=path.resolve(indexFilename),raw=await readPrivate(filename,roots),index=JSON.parse(raw),roles=validateIndex(index),parent=path.dirname(filename);
 if(index.indexPath!==filename||path.resolve(index.stagingDirectory)!==parent)throw Error('Archive private staging identity differs');
 for(const entry of index.generatedPublicFiles)if(typeof entry.localPath!=='string'||!within(path.resolve(entry.localPath),parent))throw Error('Archive local paths escape staging');
 if(roles.get('归档清单').localPath!==index.manifestPath||roles.get('完整课件').localPath!==index.zip?.path||roles.get('完整课件').sha256!==index.zip?.sha256||roles.get('完整课件').byteSize!==index.zip?.byteSize)throw Error('Archive manifest or ZIP identity differs');
 let manifestRaw;
 try{manifestRaw=await readPrivate(index.manifestPath,roots);}catch(error){if(error.code!=='ENOENT')throw error;manifestRaw=await readPrivate(path.join(parent,'manifest.json'),roots);}
 const manifest=JSON.parse(manifestRaw),entry=roles.get('归档清单');
 if(sha(manifestRaw)!==entry.sha256||manifestRaw.length!==entry.byteSize||manifest.schemaVersion!==index.schemaVersion||manifest.archiveId!==index.archiveId||manifest.complete!==true||(manifest.missingSources||[]).length||!Array.isArray(manifest.files)||identityKeys.some(k=>(manifest.identity?.[k]??null)!==(index[k]??null)))throw Error('Retained archive manifest identity or bytes differ');
 const indexSha256=sha(raw),id=storage(config),receiptPath=path.join(state,'archive-transfers',index.archiveId,'verifications',sha(canonical(id)),indexSha256+'.json');
 const receiptRaw=await readPrivate(receiptPath,[state]),receipt=JSON.parse(receiptRaw),expected=new Map(index.generatedPublicFiles.map(e=>[e.relativePath,e]));
 if(receipt.schemaVersion!=='mira.course-archive.verification.v1'||receipt.complete!==true||receipt.archiveId!==index.archiveId||receipt.indexSha256!==indexSha256||canonical(receipt.storage)!==canonical(id)||['courseId','courseVersion','sourceDigest'].some(k=>(receipt[k]??null)!==(index[k]??null))||!Array.isArray(receipt.objects)||receipt.objects.length!==4||receipt.byteSize!==index.generatedPublicFiles.reduce((n,e)=>n+e.byteSize,0))throw Error('Exact immutable archive verification identity or storage differs');
 const objects=new Map();
 for(const object of receipt.objects){const e=expected.get(object.objectKey);if(!e||objects.has(object.objectKey)||object.sha256!==e.sha256||object.byteSize!==e.byteSize||typeof object.etag!=='string'||!object.etag||('versionId'in object&&(typeof object.versionId!=='string'||!object.versionId)))throw Error('Archive verification object identity differs');objects.set(object.objectKey,object);}
 return {filename,raw,index,indexSha256,manifestRaw,receiptRaw,receipt,objects};
}
async function headSource(client,config,entry,verified){
 const response=await client.send(new HeadObjectCommand({Bucket:config.bucket,Key:entry.relativePath,...(verified.versionId?{VersionId:verified.versionId}:{})}));
 if(response.ETag!==verified.etag||response.ContentLength!==entry.byteSize||(verified.versionId&&response.VersionId!==verified.versionId))throw Error('Archive source ETag, size or version changed');
}
async function destination(client,config,entry){
 let head;try{head=await client.send(new HeadObjectCommand({Bucket:config.bucket,Key:entry.relativePath}));}catch(error){if(absent(error))return null;throw error;}
 if(head.ContentLength!==entry.byteSize||typeof head.ETag!=='string'||!head.ETag)throw Error('Archive destination identity or bytes differ');
 const response=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:entry.relativePath,IfMatch:head.ETag,...(head.VersionId?{VersionId:head.VersionId}:{})}));
 let size=0;const digest=crypto.createHash('sha256');
 for await(const bytes of response.Body){size+=bytes.length;if(size>entry.byteSize){response.Body.destroy?.();throw Error('Archive destination bytes differ');}digest.update(bytes);}
 if(size!==entry.byteSize||digest.digest('hex')!==entry.sha256||response.ETag!==head.ETag||(head.VersionId&&response.VersionId!==head.VersionId))throw Error('Archive destination identity or bytes differ');
 return {objectKey:entry.relativePath,sha256:entry.sha256,byteSize:size,etag:response.ETag,...(response.VersionId?{versionId:response.VersionId}:{})};
}
function copyInput(config,source,target,verified){
 const encoded=[config.bucket,...source.relativePath.split('/')].map(encodeURIComponent).join('/');
 return {Bucket:config.bucket,Key:target.relativePath,CopySource:encoded+(verified.versionId?'?versionId='+encodeURIComponent(verified.versionId):''),CopySourceIfMatch:verified.etag,IfNoneMatch:'*',MetadataDirective:'COPY'};
}
const sameStat=(a,b)=>['dev','ino','size','mtimeNs','ctimeNs'].every(key=>a[key]===b[key]);
async function openCache(filename,entry){
 await privateDirectory(path.dirname(filename));
 const stat=await fsp.lstat(filename);if(stat.isSymbolicLink()||!stat.isFile())throw Error('Archive transfer cache contains a symlink or non-file');
 const handle=await fsp.open(filename,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{
  const before=await handle.stat({bigint:true}),digest=crypto.createHash('sha256');let size=0;
  for await(const chunk of handle.createReadStream({start:0,autoClose:false})){size+=chunk.length;if(size>entry.byteSize)throw Error('Archive transfer cache bytes differ');digest.update(chunk);}
  if(size!==entry.byteSize||digest.digest('hex')!==entry.sha256||!sameStat(before,await handle.stat({bigint:true})))throw Error('Archive transfer cache bytes differ');
  return {handle,stat:before};
 }catch(error){await handle.close();throw error;}
}
async function verifiedPut(client,config,source,target,verified,journalDirectory){
 const directory=await privateDirectory(path.join(journalDirectory,'transfer-cache')),filename=path.join(directory,sha(source.relativePath)+'.bin'),recordPath=filename+'.json';
 const binding={source:verified,targetKey:target.relativePath,transport:'verified-put'};let previous;
 try{previous=JSON.parse(await readPrivate(recordPath,[journalDirectory]));if(canonical(previous.binding)!==canonical(binding))throw Error('Archive transfer cache binding differs');}
 catch(error){if(error.code!=='ENOENT')throw error;}
 let exists=false;try{const stat=await fsp.lstat(filename);if(stat.isSymbolicLink()||!stat.isFile())throw Error('Archive transfer cache contains a symlink or non-file');exists=true;}catch(error){if(error.code!=='ENOENT')throw error;}
 if(exists&&previous?.status!=='downloaded'){
  if(previous?.status!=='download-intent')throw Error('Archive transfer cache has no durable download owner');
  // Only this bound, exporter-owned partial download can be restarted.
  await fsp.unlink(filename);exists=false;
 }
 if(!exists){
  await atomic(recordPath,{binding,status:'download-intent'});
  const handle=await fsp.open(filename,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
  try{
   const response=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:source.relativePath,IfMatch:verified.etag,...(verified.versionId?{VersionId:verified.versionId}:{})}));
   if(response.ETag!==verified.etag||(verified.versionId&&response.VersionId!==verified.versionId)||(response.ContentLength!==undefined&&response.ContentLength!==source.byteSize)){response.Body?.destroy?.();throw Error('Archive source download identity or bytes differ');}
   let size=0;const digest=crypto.createHash('sha256');
   for await(const chunk of response.Body){size+=chunk.length;if(size>source.byteSize){response.Body.destroy?.();throw Error('Archive source download bytes differ');}digest.update(chunk);await handle.writeFile(chunk);}
   if(size!==source.byteSize||digest.digest('hex')!==source.sha256)throw Error('Archive source download bytes differ');
   await handle.sync();
  }finally{await handle.close();}
  await atomic(recordPath,{binding,status:'downloaded'});
 }
 const opened=await openCache(filename,source);
 try{
  await headSource(client,config,source,verified);
  try{await client.send(new PutObjectCommand({Bucket:config.bucket,Key:target.relativePath,Body:opened.handle.createReadStream({start:0,autoClose:false}),ContentLength:target.byteSize,ContentType:target.mimeType,Metadata:{sha256:target.sha256},ChecksumSHA256:Buffer.from(target.sha256,'hex').toString('base64'),IfNoneMatch:'*'}));}
  catch(error){if(!conditionFailed(error))throw error;}
  if(!sameStat(opened.stat,await opened.handle.stat({bigint:true})))throw Error('Archive transfer cache changed during upload');
 }finally{await opened.handle.close();}
 const object=await destination(client,config,target);if(!object)throw Error('Uploaded archive destination is missing');
 return object;
}
async function pruneCache(journalDirectory,source,target){
 const filename=path.join(journalDirectory,'transfer-cache',sha(source.relativePath)+'.bin'),recordPath=filename+'.json';let record;
 try{record=JSON.parse(await readPrivate(recordPath,[journalDirectory]));}catch(error){if(error.code==='ENOENT')return;throw error;}
 if(record.binding?.source?.objectKey!==source.relativePath||record.binding.targetKey!==target.relativePath||record.binding.transport!=='verified-put')throw Error('Archive transfer cache cleanup binding differs');
 try{
  // Recheck the private path and regular-file boundary before removing derived bytes.
  await privateDirectory(path.dirname(filename));const stat=await fsp.lstat(filename);if(stat.isSymbolicLink()||!stat.isFile())throw Error('Archive transfer cache cleanup contains a symlink');
  await fsp.unlink(filename);const parent=await fsp.open(path.dirname(filename),'r');try{await parent.sync();}finally{await parent.close();}
 }catch(error){if(error.code!=='ENOENT')throw error;}
 await atomic(recordPath,{...record,status:'destination-verified-cache-pruned'});
}

/** Explicit conditional transfers and full destination GETs; source objects are never removed. */
export async function relocateArchive(indexPath,{targetDirectory,transport='conditional-copy',dependencies={}}={}){
 if(!directoryValid(targetDirectory))throw Error('A safe five-segment archive target directory is required');
 if(!['conditional-copy','verified-put'].includes(transport))throw Error('Expected conditional-copy or explicit verified-put transport');
 const config=dependencies.config||readConfig(),state=await privateDirectory(dependencies.state||STATE);
 const roots=(dependencies.allowedRoots||[path.join(state,'archives'),...(process.env.MIRA_TASK_TMPDIR?[await fsp.realpath(process.env.MIRA_TASK_TMPDIR)]:[])]).map(root=>path.resolve(root));
 const source=await capture(indexPath,state,config,roots);
 if(source.index.objectDirectory===targetDirectory)throw Error('Archive relocation requires a different target directory');
 const binding={schemaVersion:'mira.course-archive.relocation.v1',sourceIndexSha256:source.indexSha256,sourceReceiptSha256:sha(source.receiptRaw),manifestSha256:sha(source.manifestRaw),storage:storage(config),targetDirectory};
 const planId=sha(canonical(binding)),journalDirectory=await privateDirectory(path.join(state,'archive-relocations',planId)),journalRoots=[state];
 const lockPath=path.join(journalDirectory,'execute.lock'),lock=await fsp.open(lockPath,'wx',0o600);
 try{
  await lock.writeFile(canonical({pid:process.pid,createdAt:new Date().toISOString()})+'\n');await lock.sync();
  const planPath=path.join(journalDirectory,'plan.json');let plan;
  try{plan=JSON.parse(await readPrivate(planPath,journalRoots));if(canonical(plan.binding)!==canonical(binding)||!within(plan.stagingDirectory,path.join(state,'archives'))||!new RegExp('^'+source.index.archiveId+'-[a-f0-9]{8}$').test(path.basename(plan.stagingDirectory)))throw Error('Archive relocation journal binding differs');}
  catch(error){if(error.code!=='ENOENT')throw error;plan={binding,stagingDirectory:path.join(state,'archives',source.index.archiveId+'-'+crypto.randomBytes(4).toString('hex'))};await atomic(planPath,plan);}
  const staging=await privateDirectory(plan.stagingDirectory),newIndexPath=path.join(staging,'index.json');
  const remap=filename=>path.join(staging,path.relative(source.index.stagingDirectory,filename));
  const index={...source.index,stagingDirectory:staging,indexPath:newIndexPath,manifestPath:remap(source.index.manifestPath),objectDirectory:targetDirectory,zip:{...source.index.zip,path:remap(source.index.zip.path)},generatedPublicFiles:source.index.generatedPublicFiles.map(e=>({...e,relativePath:targetDirectory+'/'+path.posix.basename(e.relativePath),localPath:remap(e.localPath)}))};
  const indexRaw=Buffer.from(canonical(index)+'\n');
  for(const [name,raw]of [['source-index.json',source.raw],['source-verification.json',source.receiptRaw],['source-manifest.json',source.manifestRaw]])await immutable(path.join(journalDirectory,name),raw,journalRoots);
  await immutable(newIndexPath,indexRaw,journalRoots);await immutable(path.join(staging,'manifest.json'),source.manifestRaw,journalRoots);
  const client=dependencies.client||new S3Client({endpoint:config.endpoint,region:config.region,forcePathStyle:true,credentials:{accessKeyId:config.accessKeyId,secretAccessKey:config.secretAccessKey},maxAttempts:1,requestChecksumCalculation:'WHEN_REQUIRED',responseChecksumValidation:'WHEN_REQUIRED'});
  const conditionPath=path.join(journalDirectory,'destination-condition.json');
  try{const previous=JSON.parse(await readPrivate(conditionPath,journalRoots));if(previous.status==='unsupported'&&transport==='conditional-copy')throw Error('Archive server does not enforce destination IfNoneMatch; further copies refused');}
  catch(error){if(error.code!=='ENOENT')throw error;}
  await atomic(path.join(journalDirectory,'transport.json'),{transport,at:new Date().toISOString()});
  // Fail before any copy if any frozen source identity has changed.
  for(const entry of source.index.generatedPublicFiles)await headSource(client,config,entry,source.objects.get(entry.relativePath));
  const destinations=[];for(const entry of index.generatedPublicFiles)destinations.push(await destination(client,config,entry));
  const copyingRequired=destinations.some(object=>!object);
  const verified=[];let conditionProven=false;
  for(let i=0;i<index.generatedPublicFiles.length;i++){
   const entry=index.generatedPublicFiles[i],old=source.index.generatedPublicFiles[i],receipt=source.objects.get(old.relativePath),stepPath=path.join(journalDirectory,sha(entry.relativePath)+'.json');
   let object=destinations[i];
   if(!object){
    await headSource(client,config,old,receipt);
    await atomic(stepPath,{objectKey:entry.relativePath,status:transport==='verified-put'?'put-intent':'copy-intent',transport,source:receipt});
    if(transport==='verified-put')object=await verifiedPut(client,config,old,entry,receipt,journalDirectory);
    else{
     const input=copyInput(config,old,entry,receipt);
     try{await client.send(new CopyObjectCommand(input));}catch(error){if(!conditionFailed(error))throw error;await headSource(client,config,old,receipt);}
     object=await destination(client,config,entry);if(!object)throw Error('Copied archive destination is missing');
    }
    await atomic(stepPath,{...object,transport,status:'transferred-and-verified'});
   }
   // On recovery probe the first already-copied target before creating another.
   if(transport==='conditional-copy'&&copyingRequired&&!conditionProven){
     await headSource(client,config,old,receipt);
     await atomic(conditionPath,{objectKey:entry.relativePath,status:'probe-intent'});
     let rejected=false;
     try{await client.send(new CopyObjectCommand(copyInput(config,old,entry,receipt)));}catch(error){if(!conditionFailed(error))throw error;rejected=true;}
     // A source precondition failure must never masquerade as destination support.
     await headSource(client,config,old,receipt);
     // Even an unsupported server only sees a second copy of already verified identical bytes.
     const after=await destination(client,config,entry);if(!after)throw Error('Archive condition probe removed its destination');object=after;
     await atomic(conditionPath,{objectKey:entry.relativePath,status:rejected?'supported':'unsupported',expectedStatus:412});
     if(!rejected)throw Error('Archive server does not enforce destination IfNoneMatch; further copies refused');
     conditionProven=true;
   }
   await pruneCache(journalDirectory,old,entry);
   await atomic(stepPath,{...object,transport,status:'verified'});verified.push(object);
  }
  let result={schemaVersion:'mira.course-archive.verification.v1',archiveId:index.archiveId,courseId:index.courseId||null,courseVersion:index.courseVersion||null,sourceDigest:index.sourceDigest||null,indexSha256:sha(indexRaw),storage:storage(config),verifiedAt:new Date().toISOString(),objects:verified,byteSize:verified.reduce((n,e)=>n+e.byteSize,0),complete:true};
  const receiptPath=path.join(state,'archive-transfers',index.archiveId,'verifications',sha(canonical(result.storage)),result.indexSha256+'.json');
  try{const previous=JSON.parse(await readPrivate(receiptPath,journalRoots));const stable=({verifiedAt,...rest})=>rest;if(canonical(stable(previous))!==canonical(stable(result)))throw Error('Immutable relocated archive verification conflicts');result=previous;}
  catch(error){if(error.code!=='ENOENT')throw error;await atomic(receiptPath,result);}
  await atomic(path.join(state,'archive-transfers',index.archiveId,'verified-complete.json'),result);
  const complete={schemaVersion:'mira.course-archive.relocated.v1',planId,indexPath:newIndexPath,receiptPath,journalDirectory,archiveId:index.archiveId,transport,objects:verified.length,byteSize:result.byteSize,complete:true,sourceObjectsRetained:true};
  await atomic(path.join(journalDirectory,'relocated-complete.json'),complete);return complete;
 }finally{await lock.close();await fsp.unlink(lockPath);}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const args=process.argv.slice(2),options={};
 try{while(args.length){const key=args.shift();if(!['--index','--target-directory','--transport'].includes(key)||!args.length)throw Error('Expected --index, --target-directory and optional --transport');options[key]=args.shift();}if(!options['--index']||!options['--target-directory'])throw Error('Exact archive index and target directory are required');console.log(JSON.stringify(await relocateArchive(options['--index'],{targetDirectory:options['--target-directory'],transport:options['--transport']||'conditional-copy'})));}
 catch(error){console.error(JSON.stringify({error:'course_archive_relocation_failed',reason:error.message}));process.exitCode=1;}
}
