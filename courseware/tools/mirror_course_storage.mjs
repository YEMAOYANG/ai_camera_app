#!/usr/bin/env node
/** Resumable, no-delete mirror from active course storage to a shadow bucket. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

import {ROOT,clientFor,readConfig,storageIdentity} from '../../openmaic-runtime/scripts/course-storage.mjs';
import {archiveKey} from '../../openmaic-runtime/scripts/course-archive.mjs';
import {validateReceipt as validateBackupReceipt} from './store_backup.mjs';

const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {GetBucketVersioningCommand,GetObjectCommand,HeadBucketCommand,HeadObjectCommand,
  ListObjectsV2Command,PutObjectCommand}=require('@aws-sdk/client-s3');
const STATE=path.join(ROOT,'backend/data/course-storage/cos-migration');
const MAX_SINGLE_PUT=5*1024**3;
const BUFFER_LIMIT=8*1024*1024;
const SPOOL_RESERVE=2n*1024n**3n;
const RANGE_BYTES=64*1024;
// Verify is read-only, so a transient read failure can safely be repeated; writes keep maxAttempts 1.
const VERIFY_RETRY={attempts:5,baseMs:1000,capMs:30000,idleMs:60000};
const TRANSIENT_NAMES=new Set(['TimeoutError','RequestTimeout','RequestTimeoutException','SlowDown','Throttling','ThrottlingException']);
const TRANSIENT_CODES=new Set(['ECONNRESET','ECONNREFUSED','ECONNABORTED','ETIMEDOUT','EPIPE','EAI_AGAIN','ENOTFOUND',
  'ENETUNREACH','ENETDOWN','EHOSTUNREACH','ERR_STREAM_PREMATURE_CLOSE']);
const absent=error=>error?.$metadata?.httpStatusCode===404||['NotFound','NoSuchKey','NoSuchVersion'].includes(error?.name);
const transientRead=error=>Boolean(error)&&(TRANSIENT_NAMES.has(error.name)||TRANSIENT_CODES.has(error.code)
  ||Boolean(error.$retryable)||[408,429].includes(error.$metadata?.httpStatusCode)||error.$metadata?.httpStatusCode>=500);
const stalled=ms=>Object.assign(Error(`Read made no progress for ${ms} ms`),{name:'TimeoutError',code:'ETIMEDOUT'});
const canonical=value=>JSON.stringify(value,(key,item)=>item&&!Array.isArray(item)&&typeof item==='object'
  ?Object.fromEntries(Object.keys(item).sort().map(name=>[name,item[name]])):item);
const digest=value=>crypto.createHash('sha256').update(value).digest('hex');

function parse(argv){
  const options={command:argv.shift(),concurrency:4,deferBackupReceipts:[]};
  while(argv.length){
    const option=argv.shift();
    if(option==='--resume'){options.resume=true;continue;}
    const value=argv.shift();
    if(!option?.startsWith('--')||value===undefined)throw Error('Expected named mirror option and value');
    const name=option.slice(2);
    if(name==='concurrency'||name==='limit'||name==='max-bytes')options[name]=Number(value);
    else if(name==='config'||name==='state'||name==='prefix'||name==='archive-receipt')options[name]=value;
    else if(name==='defer-backup-receipt')options.deferBackupReceipts.push(value);
    else throw Error('Unknown mirror option');
  }
  if(!['pilot','mirror','verify'].includes(options.command)||!Number.isInteger(options.concurrency)
      ||options.concurrency<1||options.concurrency>32
      ||(options.limit!==undefined&&(!Number.isInteger(options.limit)||options.limit<1||options.limit>100000))
      ||(options['max-bytes']!==undefined&&(!Number.isSafeInteger(options['max-bytes'])||options['max-bytes']<1))
      ||(options.resume&&options.command!=='verify'))
    throw Error('Invalid mirror arguments');
  if(options.command==='pilot'){
    options.limit=options.limit??1;options['max-bytes']=options['max-bytes']??16*1024*1024;options.concurrency=1;
  }
  return options;
}

async function privateDirectory(directory){
  const absolute=path.resolve(directory);let current=path.parse(absolute).root;
  for(const segment of absolute.slice(current.length).split(path.sep).filter(Boolean)){
    current=path.join(current,segment);
    try{const stat=await fsp.lstat(current);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('Mirror state contains a symlink');}
    catch(error){if(error.code!=='ENOENT')throw error;await fsp.mkdir(current,{mode:0o700});}
  }
  return absolute;
}

async function append(filename,record){
  const handle=await fsp.open(filename,'a',0o600);
  try{await handle.writeFile(JSON.stringify(record)+'\n');await handle.sync();}finally{await handle.close();}
}

// Without idleMs this is exactly client.send(command). With it, a request that never answers becomes a timeout.
async function send(client,command,idleMs){
  if(!idleMs)return client.send(command);
  const controller=new AbortController();let timer,expiredFirst=false;
  const pending=Promise.resolve(client.send(command,{abortSignal:controller.signal}));
  const expired=new Promise((_,reject)=>{timer=setTimeout(()=>{expiredFirst=true;controller.abort();reject(stalled(idleMs));},idleMs);});
  try{return await Promise.race([pending,expired]);}
  catch(error){throw expiredFirst?stalled(idleMs):error;}
  finally{clearTimeout(timer);if(expiredFirst)pending.then(response=>response?.Body?.destroy?.(),()=>{});}
}

async function retryRead(operation,policy,label){
  for(let attempt=1;;attempt++){
    try{return await operation();}
    catch(error){
      if(attempt>=policy.attempts||!transientRead(error))throw error;
      const delayMs=Math.min(policy.capMs,policy.baseMs*2**(attempt-1));policy.retried++;
      process.stderr.write(JSON.stringify({retry:attempt,of:policy.attempts-1,...label,code:error?.name||'Error',
        errno:typeof error?.code==='string'?error.code:null,httpStatus:error?.$metadata?.httpStatusCode||null,delayMs})+'\n');
      await policy.sleep(delayMs/2+Math.random()*delayMs/2);
    }
  }
}

async function verifiedJournal(filename){
  const records=new Map();let stat;
  try{stat=await fsp.lstat(filename);}catch(error){if(error.code==='ENOENT')return records;throw error;}
  if(stat.isSymbolicLink()||!stat.isFile()||stat.size>256*1024*1024)throw Error('Mirror journal is unsafe');
  const input=fs.createReadStream(filename,{encoding:'utf8'});
  const lines=readline.createInterface({input,crlfDelay:Infinity});
  try{
    for await(const line of lines){
      if(!line)continue;const value=JSON.parse(line);
      if(value.schemaVersion==='mira.course-storage.bucket-mirror.v1'&&value.status==='verified'
          &&typeof value.key==='string'&&value.key&&Number.isSafeInteger(value.byteSize)
          &&typeof value.sha256==='string'&&/^[a-f0-9]{64}$/.test(value.sha256)
          &&typeof value.sourceEtag==='string'&&typeof value.targetEtag==='string'
          &&typeof value.targetVersionId==='string'&&value.serverSideEncryption==='AES256')records.set(value.key,value);
    }
  }finally{lines.close();input.destroy();}
  return records;
}

async function inventory(client,config,read=(label,operation)=>operation(),idleMs,prefix){
  const objects=[];let token;
  do{
    const command=new ListObjectsV2Command({Bucket:config.bucket,ContinuationToken:token,MaxKeys:1000,
      ...(prefix?{Prefix:prefix}:{})});
    const response=await read({operation:'inventory',bucket:config.bucket},()=>send(client,command,idleMs));
    for(const item of response.Contents||[]){
      if(typeof item.Key!=='string'||!item.Key||!Number.isSafeInteger(Number(item.Size))||Number(item.Size)<0
          ||typeof item.ETag!=='string'||!item.ETag)throw Error('Source inventory is incomplete');
      if(prefix&&!item.Key.startsWith(prefix))throw Error('Object inventory is outside its declared scope');
      objects.push({key:item.Key,size:Number(item.Size),etag:item.ETag});
    }
    token=response.IsTruncated?response.NextContinuationToken:undefined;
    if(response.IsTruncated&&!token)throw Error('Source inventory pagination is incomplete');
  }while(token);
  objects.sort((a,b)=>a.key.localeCompare(b.key));
  return objects;
}

function identity(config){
  const value=storageIdentity(config);return {endpoint:value.endpoint,bucket:value.bucket,region:value.region};
}

async function archiveScope(filename,source){
  const stat=await fsp.lstat(filename);
  if(!stat.isFile()||stat.size>1024*1024)throw Error('Invalid course archive receipt file');
  let receipt;
  try{receipt=JSON.parse(await fsp.readFile(filename,'utf8'));}
  catch{throw Error('Invalid course archive receipt JSON');}
  if(receipt?.schemaVersion!=='mira.course-archive.verification.v1'||receipt.complete!==true
      ||canonical(receipt.storage)!==canonical(identity(source))||typeof receipt.archiveId!=='string'
      ||!/^[A-Za-z0-9_-]{8,128}$/.test(receipt.archiveId)
      ||!Array.isArray(receipt.objects)||!receipt.objects.length)throw Error('A verified course archive in the source bucket is required');
  const files=new Map();
  for(const item of receipt.objects){
    if(!archiveKey(item?.objectKey)||files.has(item.objectKey)||!Number.isSafeInteger(item.byteSize)||item.byteSize<1
        ||!/^[a-f0-9]{64}$/.test(item.sha256||'')||typeof item.etag!=='string'||!item.etag)
      throw Error('Invalid course archive receipt object');
    files.set(item.objectKey,item);
  }
  const directories=new Set([...files.keys()].map(key=>path.posix.dirname(key)+'/'));
  if(directories.size!==1)throw Error('A course archive receipt must identify one directory');
  return {archiveId:receipt.archiveId,prefix:[...directories][0],files};
}

function scopedArchiveInventory(inventory,scope){
  const selected=inventory.filter(item=>scope.files.has(item.key));
  if(selected.length!==scope.files.size||new Set(selected.map(item=>item.key)).size!==scope.files.size)
    throw Error('Course archive source inventory is incomplete');
  return selected.map(item=>{
    const expected=scope.files.get(item.key);
    if(item.size!==expected.byteSize||item.etag!==expected.etag)throw Error('Course archive source identity changed');
    return {...item,expectedSha256:expected.sha256};
  });
}

async function deferredKeys(filenames,source,inventory){
  const keys=new Set();
  const byKey=new Map(inventory.map(item=>[item.key,item]));
  for(const filename of filenames){
    const receipt=validateBackupReceipt(JSON.parse(await fsp.readFile(filename,'utf8')));
    if(receipt.complete!==true||canonical(receipt.storage)!==canonical(identity(source)))throw Error('Deferred backup does not belong to the source bucket');
    for(const file of receipt.files){
      const item=byKey.get(file.objectKey);
      if(!item||item.size!==file.byteSize||item.etag!==file.etag)throw Error('Deferred backup identity differs from source inventory');
      keys.add(item.key);
    }
  }
  return keys;
}

async function preflight(sourceClient,targetClient,source,target,read=(label,operation)=>operation(),idleMs){
  if(canonical(identity(source))===canonical(identity(target)))throw Error('Mirror source and target must differ');
  const request=(client,command)=>read({operation:'preflight',bucket:command.input.Bucket},()=>send(client,command,idleMs));
  await request(sourceClient,new HeadBucketCommand({Bucket:source.bucket}));
  await request(targetClient,new HeadBucketCommand({Bucket:target.bucket}));
  const versioning=await request(targetClient,new GetBucketVersioningCommand({Bucket:target.bucket}));
  if(versioning.Status!=='Enabled')throw Error('Target bucket versioning must be enabled');
}

async function head(client,config,key,idleMs){
  const command=new HeadObjectCommand({Bucket:config.bucket,Key:key});
  try{
    return await send(client,command,idleMs).catch(error=>{
      if(error?.name!=='TimeoutError')throw error;
      return send(client,command,idleMs);
    });
  }
  catch(error){if(absent(error))return null;throw error;}
}

function capture(){return {bytes:0,hash:crypto.createHash('sha256'),prefix:Buffer.alloc(0),tail:Buffer.alloc(0)};}
function consume(result,part,limit){
  const bytes=Buffer.from(part);result.bytes+=bytes.length;
  if(result.bytes>limit)throw Error('Remote object exceeds its immutable size');
  result.hash.update(bytes);
  if(result.prefix.length<RANGE_BYTES)result.prefix=Buffer.concat([result.prefix,bytes]).subarray(0,RANGE_BYTES);
  result.tail=Buffer.concat([result.tail,bytes]).subarray(-RANGE_BYTES);
}
function finish(result,expected){
  if(result.bytes!==expected)throw Error('Remote object size changed');
  return {byteSize:result.bytes,sha256:result.hash.digest('hex'),prefix:result.prefix,tail:result.tail};
}

async function fullRead(client,config,key,expected,{etag,versionId,requireEncryption=false,idleMs}={}){
  const response=await send(client,new GetObjectCommand({Bucket:config.bucket,Key:key,
    ...(etag?{IfMatch:etag}:{}),...(versionId?{VersionId:versionId}:{})}),idleMs);
  if(etag&&response.ETag!==etag){response.Body?.destroy?.();throw Error('Remote object identity changed');}
  if(versionId&&response.VersionId!==versionId){response.Body?.destroy?.();throw Error('Remote object version changed');}
  if(requireEncryption&&response.ServerSideEncryption!=='AES256'){
    response.Body?.destroy?.();throw Error('Target server-side encryption is missing');
  }
  const result=capture();
  // A body that stops sending without closing would otherwise hold this read open forever.
  const watchdog=idleMs?setTimeout(()=>response.Body?.destroy?.(stalled(idleMs)),idleMs):null;
  try{for await(const part of response.Body){watchdog?.refresh();consume(result,part,expected);}return finish(result,expected);}
  catch(error){response.Body?.destroy?.();throw error;}
  finally{if(watchdog)clearTimeout(watchdog);}
}

async function putFromSource(sourceClient,targetClient,source,target,item,spool){
  const response=await sourceClient.send(new GetObjectCommand({Bucket:source.bucket,Key:item.key,IfMatch:item.etag}));
  if(response.ETag!==item.etag||response.ContentLength!==item.size){response.Body?.destroy?.();throw Error('Source object identity changed');}
  const measured=capture();let completed;
  async function* parts(){
    try{for await(const part of response.Body){consume(measured,part,item.size);yield part;}completed=finish(measured,item.size);}
    finally{response.Body?.destroy?.();}
  }
  let body,staged,reserved=0n;
  const sourceMd5=item.etag.match(/^"([a-fA-F0-9]{32})"$/)?.[1]?.toLowerCase();
  try{
    if(item.size<=BUFFER_LIMIT){
      const chunks=[];for await(const part of parts())chunks.push(Buffer.from(part));
      body=Buffer.concat(chunks,item.size);
    }else{
      // Let a slow source finish before opening the COS upload connection.
      const disk=await fsp.statfs(spool.directory,{bigint:true});
      const size=BigInt(item.size);
      if(disk.bavail*disk.bsize<SPOOL_RESERVE+spool.reserved+size)throw Error('Insufficient local space for mirror staging');
      spool.reserved+=size;reserved=size;
      staged=await fsp.mkdtemp(path.join(spool.directory,'object-'));
      const filename=path.join(staged,'payload');
      await pipeline(Readable.from(parts(),{objectMode:false}),fs.createWriteStream(filename,{flags:'wx',mode:0o600}));
      body=fs.createReadStream(filename);
    }
    if(item.expectedSha256&&completed?.sha256!==item.expectedSha256)throw Error('Course archive source SHA-256 changed');
    const uploaded=await targetClient.send(new PutObjectCommand({Bucket:target.bucket,Key:item.key,Body:body,
      ContentLength:item.size,IfNoneMatch:'*',ServerSideEncryption:'AES256',
      ...(sourceMd5?{ContentMD5:Buffer.from(sourceMd5,'hex').toString('base64')}:{}),
      ...(response.ContentType?{ContentType:response.ContentType}:{}),
      ...(response.CacheControl?{CacheControl:response.CacheControl}:{}),
      ...(response.ContentDisposition?{ContentDisposition:response.ContentDisposition}:{}),
      ...(response.ContentEncoding?{ContentEncoding:response.ContentEncoding}:{}),
      ...(response.ContentLanguage?{ContentLanguage:response.ContentLanguage}:{}),
      ...(response.Metadata?{Metadata:response.Metadata}:{})}));
    if(!completed||typeof uploaded.ETag!=='string'||!uploaded.ETag||typeof uploaded.VersionId!=='string'||!uploaded.VersionId)
      throw Error('Target immutable version identity is missing');
    return {uploaded,sourceBytes:completed,sourceMd5};
  }finally{
    body?.destroy?.();response.Body?.destroy?.();
    try{if(staged)await fsp.rm(staged,{recursive:true,force:true});}
    finally{if(reserved)spool.reserved-=reserved;}
  }
}

async function rangeCheck(client,config,key,expected,remote){
  if(expected.byteSize<1)return;
  const end=Math.min(expected.byteSize,RANGE_BYTES)-1;
  const response=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:key,Range:`bytes=0-${end}`,
    IfMatch:remote.etag,...(remote.versionId?{VersionId:remote.versionId}:{})}));
  const chunks=[];let count=0;
  try{for await(const part of response.Body){count+=part.length;if(count>end+1)throw Error('Target range is oversized');chunks.push(Buffer.from(part));}}
  catch(error){response.Body?.destroy?.();throw error;}
  if(response.ETag!==remote.etag||(remote.versionId&&response.VersionId!==remote.versionId)
      ||response.ContentRange!==`bytes 0-${end}/${expected.byteSize}`||count!==end+1
      ||!Buffer.concat(chunks,count).equals(expected.prefix.subarray(0,end+1)))throw Error('Target range verification failed');
}

async function mirrorOne(context,item,{range=false,allowWrite=true,previous,targetListed}={}){
  const {sourceClient,targetClient,source,target,spool,idleMs}=context;
  if(item.size>MAX_SINGLE_PUT)throw Error('Source object requires multipart migration');
  let targetHead=targetListed?await head(targetClient,target,item.key,idleMs):null,sourceBytes,targetBytes,remote,
    integrityCheck='source-target-sha256';
  if(targetHead&&previous&&previous.byteSize===item.size&&previous.sourceEtag===item.etag
      &&(!item.expectedSha256||previous.sha256===item.expectedSha256)
      &&previous.targetEtag===targetHead.ETag&&previous.targetVersionId===targetHead.VersionId
      &&targetHead.ContentLength===item.size&&targetHead.ServerSideEncryption==='AES256'){
    return {receipt:previous,resumed:true};
  }
  if(targetHead){
    if(targetHead.ContentLength!==item.size||typeof targetHead.ETag!=='string'||!targetHead.ETag
        ||typeof targetHead.VersionId!=='string'||!targetHead.VersionId)throw Error('Existing target identity differs');
    sourceBytes=await fullRead(sourceClient,source,item.key,item.size,{etag:item.etag,idleMs});
    remote={etag:targetHead.ETag,versionId:targetHead.VersionId};
  }else{
    if(!allowWrite)throw Error('Target object is missing');
    const copied=await putFromSource(sourceClient,targetClient,source,target,item,spool);
    sourceBytes=copied.sourceBytes;remote={etag:copied.uploaded.ETag,versionId:copied.uploaded.VersionId};
    if(!range&&copied.sourceMd5&&remote.etag.replaceAll('"','').toLowerCase()===copied.sourceMd5
        &&copied.uploaded.ServerSideEncryption==='AES256'){
      targetBytes=sourceBytes;integrityCheck='cos-content-md5+source-sha256';
    }
  }
  if(item.expectedSha256&&sourceBytes.sha256!==item.expectedSha256)throw Error('Course archive source SHA-256 changed');
  targetBytes=targetBytes||await fullRead(targetClient,target,item.key,item.size,{...remote,requireEncryption:true,idleMs});
  if(sourceBytes.sha256!==targetBytes.sha256||!sourceBytes.prefix.equals(targetBytes.prefix)
      ||!sourceBytes.tail.equals(targetBytes.tail))throw Error('Source and target bytes differ');
  if(range)await rangeCheck(targetClient,target,item.key,targetBytes,remote);
  return {receipt:{schemaVersion:'mira.course-storage.bucket-mirror.v1',status:'verified',key:item.key,
    byteSize:item.size,sha256:sourceBytes.sha256,sourceEtag:item.etag,
    targetEtag:remote.etag,targetVersionId:remote.versionId,serverSideEncryption:'AES256',
    integrityCheck,rangeVerified:range,verifiedAt:new Date().toISOString()},resumed:false};
}

async function parallel(items,limit,operation){
  let cursor=0,objects=0,bytes=0,resumedObjects=0,resumedBytes=0,last=Date.now();const errors=[];
  await Promise.all(Array.from({length:Math.min(limit,items.length)},async()=>{
    for(;;){
      if(errors.length)return;
      const index=cursor++;if(index>=items.length)return;const item=items[index];
      try{const result=await operation(item);objects++;bytes+=item.size;if(result?.resumed){resumedObjects++;resumedBytes+=item.size;}}
      catch(error){errors.push({keySha256:digest(item.key),code:error?.name||'Error',
        httpStatus:error?.$metadata?.httpStatusCode||null});}
      if(Date.now()-last>10000){last=Date.now();process.stderr.write(JSON.stringify({objects,total:items.length,bytes,resumedObjects,errors:errors.length})+'\n');}
    }
  }));
  if(errors.length){process.stderr.write(JSON.stringify({errorCount:errors.length,errors:errors.slice(0,10)})+'\n');throw Error('Bucket mirror incomplete; source retained');}
  return {objects,bytes,resumedObjects,resumedBytes};
}

export async function runMirror(options,dependencies={}){
  if(options.resume&&options.command!=='verify')throw Error('Resume applies only to verify');
  const filename=options.config||path.join(ROOT,'backend/.env');
  const source=dependencies.source||readConfig(filename);
  const scope=options['archive-receipt']?await archiveScope(options['archive-receipt'],source):null;
  if(scope&&(options.deferBackupReceipts?.length||(options.prefix!==undefined&&options.prefix!==scope.prefix)))
    throw Error('Course archive receipt cannot be combined with a different directory or deferred backup');
  const prefix=scope?.prefix??options.prefix;
  if(prefix!==undefined&&(typeof prefix!=='string'||!prefix.endsWith('/')||prefix.startsWith('/')
      ||prefix.slice(0,-1).split('/').some(part=>!part.trim()||part==='.'||part==='..')
      ||/[\\\x00-\x1f\x7f]/.test(prefix)))throw Error('Expected a nonempty object directory prefix ending with /');
  const target=dependencies.target||readConfig(filename,'COS_TARGET');
  const sourceClient=dependencies.sourceClient||clientFor(source),targetClient=dependencies.targetClient||clientFor(target,{maxAttempts:1});
  const spool={directory:null,reserved:0n};
  const verifying=options.command==='verify';
  const policy=verifying?{...VERIFY_RETRY,...dependencies.retry,retried:0,
    sleep:dependencies.sleep||(ms=>new Promise(resolve=>setTimeout(resolve,ms)))}:null;
  const read=(label,operation)=>policy?retryRead(operation,policy,label):operation();
  const idleMs=policy?.idleMs;
  let lock,lockPath;
  try{
    await preflight(sourceClient,targetClient,source,target,read,idleMs);
    const state=await privateDirectory(options.state||dependencies.state||STATE);
    const id=digest(canonical({source:identity(source),target:identity(target)}));
    lockPath=path.join(state,id+'.lock');
    lock=await fsp.open(lockPath,'wx',0o600);
    await lock.writeFile(JSON.stringify({pid:process.pid,createdAt:new Date().toISOString()})+'\n');
    await lock.sync();
    const sourceObjects=await inventory(sourceClient,source,read,idleMs,prefix);
    const all=scope?scopedArchiveInventory(sourceObjects,scope):sourceObjects;
    const targetInventory=await inventory(targetClient,target,read,idleMs,prefix);
    const targetObjects=scope?targetInventory.filter(item=>scope.files.has(item.key)):targetInventory;
    const deferred=options.deferBackupReceipts?.length?await deferredKeys(options.deferBackupReceipts,source,all):new Set();
    const targetByKey=new Map(targetObjects.map(item=>[item.key,item]));
    let selected=deferred.size?all.filter(item=>!deferred.has(item.key)):all;
    if(options.command==='pilot')selected=selected.filter(item=>item.size>0&&item.size<=options['max-bytes']).sort((a,b)=>a.size-b.size||a.key.localeCompare(b.key));
    if(options.limit!==undefined)selected=selected.slice(0,options.limit);
    if(options['max-bytes']!==undefined&&options.command!=='pilot'){
      let total=0;selected=selected.filter(item=>total+item.size<=options['max-bytes']?(total+=item.size,true):false);
    }
    if(!selected.length)throw Error('No source objects match the mirror limits');
    if(options.command!=='verify'&&selected.some(item=>item.size>BUFFER_LIMIT&&item.size<=MAX_SINGLE_PUT)){
      const temporaryRoot=await fsp.realpath(process.env.MIRA_TASK_TMPDIR||os.tmpdir());
      spool.directory=await fsp.mkdtemp(path.join(temporaryRoot,'mira-cos-mirror-'));
    }
    const journal=path.join(state,id+'.jsonl');
    const previous=await verifiedJournal(journal);
    let journalQueue=Promise.resolve();
    const result=await parallel(selected,options.concurrency,async item=>{
      const prior=previous.get(item.key);
      // Verify resumes only from an earlier byte-for-byte read-back, never from an upload-time MD5 receipt.
      const resumable=options.command==='mirror'?prior
        :options.resume&&prior?.integrityCheck==='source-target-sha256'?prior:undefined;
      const verified=await read({keySha256:digest(item.key)},()=>mirrorOne({sourceClient,targetClient,source,target,spool,idleMs},item,
        {range:options.command==='pilot',allowWrite:!verifying,previous:resumable,targetListed:targetByKey.get(item.key)}));
      if(!verified.resumed){journalQueue=journalQueue.then(()=>append(journal,verified.receipt));await journalQueue;}
      return verified;
    });
    const summary={schemaVersion:'mira.course-storage.bucket-mirror-summary.v1',mode:options.command,
      ...(prefix?{prefix,complete:result.objects===all.length}:{}),
      ...(scope?{archiveId:scope.archiveId}:{}),
      sourceObjects:all.length,targetObjects:targetObjects.length,selectedObjects:selected.length,verifiedObjects:result.objects,
      resumedObjects:result.resumedObjects,verifiedBytes:result.bytes,
      ...(verifying?{resumedBytes:result.resumedBytes,retriedReads:policy.retried}:{}),
      source:identity(source),target:identity(target),journal,completedAt:new Date().toISOString(),
      ...(deferred.size?{deferredObjects:deferred.size}:{})};
    await append(journal,summary);return summary;
  }finally{
    if(lock){await lock.close();await fsp.unlink(lockPath);}
    if(!dependencies.sourceClient)sourceClient.destroy();
    if(!dependencies.targetClient)targetClient.destroy();
    if(spool.directory)await fsp.rm(spool.directory,{recursive:true,force:true});
  }
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  runMirror(parse(process.argv.slice(2))).then(result=>process.stdout.write(JSON.stringify({
    mode:result.mode,sourceObjects:result.sourceObjects,verifiedObjects:result.verifiedObjects,
    ...(result.prefix?{prefix:result.prefix}:{}),
    ...(result.archiveId?{archiveId:result.archiveId}:{}),
    resumedObjects:result.resumedObjects,verifiedBytes:result.verifiedBytes,
    ...(result.resumedBytes!==undefined?{resumedBytes:result.resumedBytes,retriedReads:result.retriedReads}:{}),
    ...(result.deferredObjects?{deferredObjects:result.deferredObjects}:{}),complete:result.complete??!result.deferredObjects})+'\n')).catch(error=>{
      process.stderr.write(JSON.stringify({error:String(error?.message||error).slice(0,200)})+'\n');process.exitCode=1;
    });
}
