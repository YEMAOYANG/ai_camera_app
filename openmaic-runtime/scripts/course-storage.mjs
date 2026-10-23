#!/usr/bin/env node
/** Immutable course-file migration, verification, exact restore and guarded pruning. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const { S3Client, HeadBucketCommand, ListObjectsV2Command, GetBucketPolicyCommand,
  HeadObjectCommand, PutObjectCommand, GetObjectCommand } = require('@aws-sdk/client-s3');
const NATIVE = 'openmaic-runtime/.runtime/OpenMAIC/data/';
const MIME = { '.mp3':'audio/mpeg','.wav':'audio/wav','.ogg':'audio/ogg','.aac':'audio/aac',
  '.flac':'audio/flac','.mp4':'video/mp4','.webm':'video/webm','.webp':'image/webp',
  '.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif',
  '.json':'application/json','.jsonl':'application/x-ndjson','.html':'text/html',
  '.txt':'text/plain','.md':'text/markdown','.gz':'application/gzip','.glb':'model/gltf-binary' };
const PUBLISHED_MEDIA = /^openmaic-runtime\/\.runtime\/OpenMAIC\/data\/classrooms\/(?:tbpub_[a-f0-9]{24}|stage-[A-Za-z0-9_-]+)\/(?:audio|media)\/[A-Za-z0-9_.-]+$/;
const BACKEND_PUBLISHED_AUDIO = /^backend\/data\/learning-media\/narration\/catalog_build_item_[A-Za-z0-9_-]+\/formal_narration_[A-Za-z0-9_-]+-[a-f0-9]{64}\.wav$/;

function args(argv) {
  const result = { command: argv.shift(), include: [] };
  while (argv.length) {
    const key = argv.shift();
    if (!key.startsWith('--')) throw Error('Expected a named option');
    const name = key.slice(2);
    const value = argv[0] && !argv[0].startsWith('--') ? argv.shift() : true;
    if (name === 'include') result.include.push(value); else result[name] = value;
  }
  return result;
}
export function readConfig(filename = path.join(ROOT, 'backend/.env')) {
  const values = {};
  for (const line of fs.readFileSync(filename, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*(COURSE_STORAGE_[A-Z_]+)\s*=\s*(.*?)\s*$/);
    if (m) values[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
  const value = name => process.env[name] ?? values[name];
  const config = { endpoint:value('COURSE_STORAGE_ENDPOINT'), bucket:value('COURSE_STORAGE_BUCKET'),
    prefix:value('COURSE_STORAGE_PREFIX') || 'mira-courseware/v1', region:value('COURSE_STORAGE_REGION') || 'us-east-1',
    accessKeyId:value('COURSE_STORAGE_ACCESS_KEY'), secretAccessKey:value('COURSE_STORAGE_SECRET_KEY') };
  if (Object.values(config).some(v => typeof v !== 'string' || !v)) throw Error('Course storage configuration is incomplete');
  const endpoint = new URL(config.endpoint);
  if (!['http:','https:'].includes(endpoint.protocol) || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.pathname !== '/') throw Error('Invalid endpoint');
  if (!/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(config.bucket) || !/^[a-zA-Z0-9][a-zA-Z0-9/_-]*$/.test(config.prefix)) throw Error('Invalid bucket or prefix');
  return config;
}
function clientFor(c) {
  return new S3Client({ endpoint:c.endpoint,region:c.region,forcePathStyle:true,
    credentials:{accessKeyId:c.accessKeyId,secretAccessKey:c.secretAccessKey},maxAttempts:3,
    requestChecksumCalculation:'WHEN_REQUIRED',responseChecksumValidation:'WHEN_REQUIRED' });
}
export function safePath(relative) {
  if (typeof relative !== 'string' || !relative || relative.includes('\\') || relative.includes('\0') || path.posix.isAbsolute(relative) || relative.split('/').some(x => x === '..' || x === '.')) throw Error('Invalid source path');
  const resolved = path.resolve(ROOT, relative);
  if (!resolved.startsWith(ROOT + path.sep)) throw Error('Source path escapes project');
  return resolved;
}
export function allowedSource(relative) {
  const mime = MIME[path.extname(relative).toLowerCase()];
  return (PUBLISHED_MEDIA.test(relative) || BACKEND_PUBLISHED_AUDIO.test(relative)) && /^(audio|image|video)\//.test(mime || '');
}
export async function digestFile(filename) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(filename)) hash.update(chunk);
  return hash.digest('hex');
}
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
async function atomicJson(filename, data) {
  await fsp.mkdir(path.dirname(filename), {recursive:true,mode:0o700});
  const tmp = filename + '.new-' + process.pid;
  const h = await fsp.open(tmp, 'wx', 0o600);
  try { await h.writeFile(JSON.stringify(data) + '\n'); await h.sync(); } finally { await h.close(); }
  await fsp.rename(tmp, filename);
}
function identity(s) { return {size:Number(s.size),mtimeNs:s.mtimeNs.toString(),ctimeNs:s.ctimeNs.toString(),ino:s.ino.toString(),dev:s.dev.toString()}; }
const IDENTITY_KEYS = ['size','mtimeNs','ctimeNs','ino','dev'];
const validIdentity = a => a && Object.keys(a).length === IDENTITY_KEYS.length &&
  IDENTITY_KEYS.every(k => k === 'size' ? Number.isSafeInteger(a[k]) && a[k] >= 0 : typeof a[k] === 'string' && /^\d+$/.test(a[k]));
const sameIdentity = (a,b) => validIdentity(a) && validIdentity(b) && IDENTITY_KEYS.every(k => a[k] === b[k]);
const sameMovedIdentity = (a,b) => validIdentity(a) && validIdentity(b) &&
  IDENTITY_KEYS.filter(k => k !== 'ctimeNs').every(k => a[k] === b[k]);
export function storageIdentity(c) {
  return { endpoint:new URL(c.endpoint).origin, bucket:c.bucket, prefix:c.prefix, region:c.region };
}
const sameStorage = (a,b) => a && b && ['endpoint','bucket','prefix','region'].every(k => a[k] === b[k]);
function sourcePath(relative, root) {
  safePath(relative);
  return path.resolve(root,relative);
}
async function noSymlinkPath(root, target, missing = false) {
  const relative = path.relative(root,target);
  if (relative.startsWith('..' + path.sep) || relative === '..' || path.isAbsolute(relative)) throw Error('Path escapes trusted root');
  let current=root;
  const rootStat=await fsp.lstat(root);
  if(rootStat.isSymbolicLink() || !rootStat.isDirectory())throw Error('Trusted root must be a real directory');
  for(const component of relative.split(path.sep).filter(Boolean)) {
    current=path.join(current,component);
    let s;
    try{s=await fsp.lstat(current);}catch(e){if(missing && e.code==='ENOENT')return;throw e;}
    if(s.isSymbolicLink())throw Error('Symlink component is not allowed');
  }
}
async function safeDirectory(root,target) {
  const relative=path.relative(root,target);
  if(relative==='..' || relative.startsWith('..'+path.sep) || path.isAbsolute(relative))throw Error('Directory escapes trusted root');
  await noSymlinkPath(root,root);
  let current=root;
  for(const component of relative.split(path.sep).filter(Boolean)) {
    current=path.join(current,component);
    try{await fsp.mkdir(current,{mode:0o700});}catch(e){if(e.code!=='EEXIST')throw e;}
    const s=await fsp.lstat(current);
    if(s.isSymbolicLink() || !s.isDirectory())throw Error('Directory contains a symlink or non-directory');
  }
}
async function destinationRoot(directory) {
  const absolute=path.resolve(directory);
  // Resolve the explicitly selected root's existing parent, then reject links
  // below it. This permits macOS /tmp aliases without following a link inside
  // the selected restoration tree.
  let ancestor=absolute;
  const missing=[];
  for(;;){
    try{
      const s=await fsp.lstat(ancestor);
      if(s.isSymbolicLink() || !s.isDirectory())throw Error('Restore root must not be a symlink');
      break;
    }catch(e){if(e.code!=='ENOENT')throw e;missing.unshift(path.basename(ancestor));ancestor=path.dirname(ancestor);}
  }
  const canonical=await fsp.realpath(ancestor);
  const target=path.join(canonical,...missing);
  await safeDirectory(canonical,target);
  return target;
}
async function stableRead(filename,root) {
  await noSymlinkPath(root,filename);
  const before=await fsp.lstat(filename,{bigint:true});
  if(!before.isFile())throw Error('Source is not a regular file');
  const handle=await fsp.open(filename,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try{
    const opened=await handle.stat({bigint:true});
    if(!sameIdentity(identity(before),identity(opened)))throw Error('Source changed while opening');
    const hash=crypto.createHash('sha256');
    for await(const chunk of handle.createReadStream({start:0,autoClose:false}))hash.update(chunk);
    await noSymlinkPath(root,filename);
    if(!sameIdentity(identity(opened),identity(await handle.stat({bigint:true}))) ||
       !sameIdentity(identity(opened),identity(await fsp.lstat(filename,{bigint:true}))))throw Error('Source changed during read');
    return {handle,sourceIdentity:identity(opened),sha256:hash.digest('hex')};
  }catch(e){await handle.close();throw e;}
}
async function loadManifest(filename,c) {
  const raw = await fsp.readFile(filename); const m = JSON.parse(raw);
  if (m.schemaVersion !== 'mira.course-storage.manifest.v1' || !/^[A-Za-z0-9_-]+$/.test(m.snapshotId) || !Array.isArray(m.files) || !m.files.length) throw Error('Invalid manifest');
  const seen = new Set();
  for (const e of m.files) {
    safePath(e.path);
    if (!allowedSource(e.path) || seen.has(e.path) || !/^[a-f0-9]{64}$/.test(e.sha256) || !Number.isSafeInteger(e.byteSize) || e.byteSize <= 0 || !validIdentity(e.sourceIdentity) || e.sourceIdentity.size!==e.byteSize || e.mimeType!==MIME[path.extname(e.path).toLowerCase()] || e.objectKey !== `${c.prefix}/blobs/sha256/${e.sha256}`) throw Error('Invalid manifest entry');
    seen.add(e.path);
  }
  return {m,manifestSha256:digest(raw)};
}
async function parallel(items, limit, fn) {
  let next=0,done=0,bytes=0;const errors=[];const started=Date.now();let last=started;
  await Promise.all(Array.from({length:Math.min(limit,items.length)},async()=>{
    for (;;) {
      const i=next++;if(i>=items.length)break;
      try { await fn(items[i]);bytes+=items[i].byteSize || 0; } catch(e) { errors.push({path:items[i].path,code:e.Code || e.name || 'Error',message:String(e.message).slice(0,160)}); }
      done++;
      if(Date.now()-last>10000){last=Date.now();process.stdout.write(JSON.stringify({done,total:items.length,bytes,errors:errors.length,seconds:Math.round((last-started)/1000)})+'\n');}
    }
  }));
  if(errors.length) { process.stderr.write(JSON.stringify({errors:errors.slice(0,20),errorCount:errors.length})+'\n'); throw Error('Operation incomplete; sources retained'); }
  return {objects:done,bytes,elapsedSeconds:Math.round((Date.now()-started)/1000)};
}
function unique(m) { return [...new Map(m.files.map(e=>[e.sha256,e])).values()]; }
async function remoteHash(client,c,e,expected) {
  const response=await client.send(new GetObjectCommand({Bucket:c.bucket,Key:e.objectKey,
    ...(expected ? {IfMatch:expected.etag,...(expected.versionId ? {VersionId:expected.versionId} : {})} : {})}));
  const hash=crypto.createHash('sha256');let size=0;
  for await(const chunk of response.Body){size+=chunk.length;hash.update(chunk);}
  if(size!==e.byteSize || hash.digest('hex')!==e.sha256)throw Error('Remote byte checksum mismatch');
  if(typeof response.ETag!=='string' || !response.ETag)throw Error('Remote immutable object identity is missing');
  if(expected && (response.ETag!==expected.etag || (expected.versionId && response.VersionId!==expected.versionId)))throw Error('Remote object identity changed');
  return {objectKey:e.objectKey,sha256:e.sha256,byteSize:size,etag:response.ETag,
    ...(response.VersionId ? {versionId:response.VersionId} : {})};
}
async function appendReceipt(filename,record) {
  const h=await fsp.open(filename,'a',0o600);
  try{await h.writeFile(JSON.stringify(record)+'\n');await h.sync();}finally{await h.close();}
}
export async function quarantineAndPrune({source,entry,root,quarantineRoot,receipt},operations=fsp) {
  await noSymlinkPath(root,source);
  if(!sameIdentity(entry.sourceIdentity,identity(await operations.lstat(source,{bigint:true}))))throw Error('Changed source retained before quarantine');
  await safeDirectory(root,quarantineRoot);
  const folder=await operations.mkdtemp(path.join(quarantineRoot,'entry-'));
  const quarantined=path.join(folder,'media');
  await appendReceipt(receipt,{status:'quarantine-intent',path:entry.path,quarantined,sha256:entry.sha256,at:new Date().toISOString()});
  await operations.rename(source,quarantined);
  try{
    const read=await stableRead(quarantined,root);
    try{
      if(!sameMovedIdentity(entry.sourceIdentity,read.sourceIdentity) || read.sha256!==entry.sha256)throw Error('Quarantined source changed; it will not be deleted');
    }finally{await read.handle.close();}
    await operations.unlink(quarantined);
  }catch(error){
    let restored=false;
    try{
      await noSymlinkPath(root,path.dirname(source));
      // link is an exclusive no-overwrite publication. The quarantine link is
      // removed only after the original path has been recovered successfully.
      await operations.link(quarantined,source);
      await operations.unlink(quarantined);await operations.rmdir(folder);restored=true;
    }catch{}
    await appendReceipt(receipt,{status:restored?'retained-restored':'retained-in-quarantine',path:entry.path,quarantined:restored?null:quarantined,at:new Date().toISOString()});
    throw Error(restored?'Changed source restored; nothing deleted':'Source retained in private quarantine; original path was not overwritten');
  }
  await operations.rmdir(folder).catch(()=>{});
  await appendReceipt(receipt,{status:'pruned',path:entry.path,sha256:entry.sha256,byteSize:entry.byteSize,at:new Date().toISOString()});
}
export async function run(options,dependencies={}) {
  const root=await fsp.realpath(dependencies.root || ROOT);
  const state=dependencies.state || path.join(root,'backend/data/course-storage');
  const c=dependencies.config || readConfig(options.config);const client=dependencies.client || clientFor(c);
  const storage=storageIdentity(c);
  await safeDirectory(root,state);
  if(options.command==='probe') {
    await client.send(new HeadBucketCommand({Bucket:c.bucket}));
    const listed=await client.send(new ListObjectsV2Command({Bucket:c.bucket,MaxKeys:1}));
    let policy;
    try { policy=(await client.send(new GetBucketPolicyCommand({Bucket:c.bucket}))).Policy; }
    catch(e){if(e.name!=='NoSuchBucketPolicy')throw e;}
    console.log(JSON.stringify({bucket:c.bucket,apiHealthy:true,empty:!listed.KeyCount,anonymousPolicyPresent:Boolean(policy)}));return;
  }
  if(options.command==='inventory') {
    if(!options.manifest || !options['release-index'])throw Error('inventory requires --manifest and a validated --release-index');
    const files=[];const skipped=[];let total=0;const visited=new Set();
    async function walk(relative) {
      if(visited.has(relative))return;visited.add(relative);
      const full=sourcePath(relative,root);await noSymlinkPath(root,full);const s=await fsp.lstat(full,{bigint:true});
      if(s.isSymbolicLink() || !allowedSource(relative)){skipped.push({path:relative,reason:s.isSymbolicLink()?'symlink':'not-allowlisted'});return;}
      if(s.isDirectory()) { for(const n of (await fsp.readdir(full)).sort())await walk(relative+'/'+n);return; }
      if(!s.isFile()){skipped.push({path:relative,reason:'not-regular'});return;}
      const read=await stableRead(full,root);await read.handle.close();const sha256=read.sha256;
      files.push({path:relative,objectKey:`${c.prefix}/blobs/sha256/${sha256}`,sha256,byteSize:Number(s.size),mimeType:MIME[path.extname(relative).toLowerCase()],sourceIdentity:read.sourceIdentity});
      total+=Number(s.size);
      if(files.length%5000===0)console.log(JSON.stringify({inventoried:files.length,bytes:total}));
    }
    const index=JSON.parse(await fsp.readFile(options['release-index'],'utf8'));
    if(index.schemaVersion!=='mira.course-storage.releases.v1' || !Array.isArray(index.releases) || !index.releases.length)throw Error('Validated release index required');
    const releases=index.releases.filter(r=>!options.classroom || r.classroomId===options.classroom);
    if(!releases.length)throw Error('No matching published releases');
    const expected=new Map();
    for(const release of releases){
      if(!/^(?:tbpub_[a-f0-9]{24}|stage-[A-Za-z0-9_-]+)$/.test(release.classroomId)||!Array.isArray(release.media)||!/^[a-f0-9]{64}$/.test(release.releaseSha256))throw Error('Invalid published release identity');
      for(const media of release.media){
        const prefix=`/api/classroom-media/${release.classroomId}/`;
        let relative;
        if(typeof media.sourcePath==='string' && media.sourcePath.startsWith('backend/')){
          if(typeof media.sourcePath!=='string' || !BACKEND_PUBLISHED_AUDIO.test(media.sourcePath) || typeof media.path!=='string' || !/^\/mira\/runtime-audio\/[A-Za-z0-9_-]+$/.test(media.path))throw Error('Invalid published backend audio source');
          relative=media.sourcePath;
        }else{
          if(!media.path.startsWith(prefix))throw Error('Media belongs to another classroom');
          relative=NATIVE+'classrooms/'+media.path.slice('/api/classroom-media/'.length);
          if(media.sourcePath!==undefined && media.sourcePath!==relative)throw Error('Published native source does not match the frozen URL');
        }
        if(!allowedSource(relative))throw Error('Only published media may be uploaded');
        const previous=expected.get(relative);
        if(previous && JSON.stringify(previous)!==JSON.stringify(media))throw Error('Conflicting release media inventory');
        expected.set(relative,media);await walk(relative);
      }
    }
    if(files.length!==expected.size)throw Error('Published media cannot be a symlink or a non-regular file');
    for(const e of files){const media=expected.get(e.path);if(e.sha256!==media.sha256 || e.byteSize!==media.byteSize || e.mimeType!==media.mimeType)throw Error('Local media differs from frozen published release: '+e.path);}
    const m={schemaVersion:'mira.course-storage.manifest.v1',snapshotId:options.snapshot || 'snapshot-'+Date.now(),createdAt:new Date().toISOString(),releases:releases.map(({media,...r})=>r),files,skipped};
    await atomicJson(options.manifest,m);
    console.log(JSON.stringify({manifest:options.manifest,files:files.length,uniqueObjects:unique(m).length,bytes:total,skipped:skipped.length}));return;
  }
  if(!options.manifest)throw Error('--manifest is required');
  const {m,manifestSha256}=await loadManifest(options.manifest,c);const dir=path.join(state,'transfers',m.snapshotId);
  await safeDirectory(root,dir);const concurrency=Number(options.concurrency || 12);
  if(!Number.isInteger(concurrency)||concurrency<1||concurrency>32)throw Error('Invalid concurrency');
  if(options.command==='upload') {
    const result=await parallel(unique(m),concurrency,async e=>{
      let existing;
      try {existing=await client.send(new HeadObjectCommand({Bucket:c.bucket,Key:e.objectKey}));}
      catch(error){if(error.$metadata?.httpStatusCode!==404)throw error;}
      if(existing){if(existing.ContentLength!==e.byteSize || existing.Metadata?.sha256!==e.sha256)throw Error('Existing immutable object metadata mismatch');return;}
      const source=sourcePath(e.path,root);const read=await stableRead(source,root);
      try{
        if(!sameIdentity(e.sourceIdentity,read.sourceIdentity) || read.sha256!==e.sha256)throw Error('Source changed after inventory');
        const response=await client.send(new PutObjectCommand({Bucket:c.bucket,Key:e.objectKey,Body:read.handle.createReadStream({start:0,autoClose:false}),ContentLength:e.byteSize,
          ContentType:e.mimeType,Metadata:{sha256:e.sha256},ChecksumSHA256:Buffer.from(e.sha256,'hex').toString('base64'),IfNoneMatch:'*'}));
        await noSymlinkPath(root,source);
        if(!sameIdentity(read.sourceIdentity,identity(await read.handle.stat({bigint:true}))) || !sameIdentity(read.sourceIdentity,identity(await fsp.lstat(source,{bigint:true}))))throw Error('Source changed during upload');
        await appendReceipt(path.join(dir,'upload.jsonl'),{sha256:e.sha256,byteSize:e.byteSize,etag:response.ETag,storage,at:new Date().toISOString()});
      }finally{await read.handle.close();}
    });
    await atomicJson(path.join(dir,'upload-complete.json'),{manifestSha256,...result});console.log(JSON.stringify({uploaded:true,...result}));return;
  }
  if(options.command==='verify') {
    const blobs={};const previous=new Map();let resumedObjects=0;
    if(options.resume && fs.existsSync(path.join(dir,'verified.jsonl'))){
      for(const line of (await fsp.readFile(path.join(dir,'verified.jsonl'),'utf8')).split('\n')){
        if(!line)continue;let record;try{record=JSON.parse(line);}catch{continue;}
        if(sameStorage(record.storage,storage) && /^[a-f0-9]{64}$/.test(record.sha256 || '') && record.objectKey===`${c.prefix}/blobs/sha256/${record.sha256}` && typeof record.etag==='string' && record.etag)previous.set(record.sha256,record);
      }
    }
    const result=await parallel(unique(m),concurrency,async e=>{
      const prior=previous.get(e.sha256);
      if(prior && prior.byteSize===e.byteSize){
        const head=await client.send(new HeadObjectCommand({Bucket:c.bucket,Key:e.objectKey,...(prior.versionId?{VersionId:prior.versionId}:{})}));
        if(head.ContentLength===e.byteSize && head.ETag===prior.etag && (!prior.versionId || head.VersionId===prior.versionId)){
          blobs[e.sha256]={objectKey:e.objectKey,sha256:e.sha256,byteSize:e.byteSize,etag:prior.etag,...(prior.versionId?{versionId:prior.versionId}:{})};resumedObjects++;return;
        }
      }
      const blob=await remoteHash(client,c,e);blobs[e.sha256]=blob;await appendReceipt(path.join(dir,'verified.jsonl'),{...blob,storage,at:new Date().toISOString()});
    });
    const verification={schemaVersion:'mira.course-storage.verification.v2',manifestSha256,storage,blobs,verifiedAt:new Date().toISOString(),resumedObjects,...result};
    await atomicJson(path.join(dir,'verified-complete.json'),verification);
    // Migration and course metadata remain private on this machine. Only media blobs are uploaded.
    console.log(JSON.stringify({verified:true,files:m.files.length,resumedObjects,...result}));return;
  }
  const verifiedRaw=await fsp.readFile(path.join(dir,'verified-complete.json'));const verified=JSON.parse(verifiedRaw);
  if(verified.schemaVersion!=='mira.course-storage.verification.v2' || verified.manifestSha256!==manifestSha256 || verified.objects!==unique(m).length || !sameStorage(verified.storage,storage))throw Error('Complete remote verification for this endpoint, bucket and prefix is required');
  for(const e of unique(m)){
    const b=verified.blobs?.[e.sha256];
    if(!b || b.sha256!==e.sha256 || b.byteSize!==e.byteSize || b.objectKey!==e.objectKey || typeof b.etag!=='string' || !b.etag)throw Error('Verified immutable blob identity required');
  }
  if(options.command==='activate') {
    await atomicJson(path.join(state,'active-manifest.json'),m);
    await atomicJson(path.join(state,'active-verification.json'),{manifestSha256,verificationSha256:digest(verifiedRaw),storage});
    console.log(JSON.stringify({activated:true,snapshotId:m.snapshotId,files:m.files.length}));return;
  }
  if(options.command==='restore') {
    if(!options.path)throw Error('restore requires an exact --path or --path directory prefix');
    const selected=m.files.filter(e=>e.path===options.path || e.path.startsWith(options.path.replace(/\/$/,'')+'/'));
    if(!selected.length)throw Error('No manifest files match');
    const restoreRoot=options.destination ? await destinationRoot(options.destination) : root;
    if(options['discard-after-check'] && (!options.destination || restoreRoot===root || restoreRoot.startsWith(root+path.sep)))throw Error('Discarded restore checks require an isolated destination outside the project');
    const result=await parallel(selected,concurrency,async e=>{
      const dest=sourcePath(e.path,restoreRoot);await noSymlinkPath(restoreRoot,dest,true);
      if(fs.existsSync(dest)){const read=await stableRead(dest,restoreRoot);try{if(read.sha256!==e.sha256)throw Error('Refusing to overwrite a changed local file');}finally{await read.handle.close();}return;}
      await safeDirectory(restoreRoot,path.dirname(dest));
      const tmp=dest+'.mira-restore-'+process.pid;const handle=await fsp.open(tmp,'wx',0o600);
      try{
        const b=verified.blobs[e.sha256];const r=await client.send(new GetObjectCommand({Bucket:c.bucket,Key:e.objectKey,IfMatch:b.etag,...(b.versionId?{VersionId:b.versionId}:{})}));const hash=crypto.createHash('sha256');let size=0;
        for await(const chunk of r.Body){let offset=0;while(offset<chunk.length){const written=await handle.write(chunk,offset,chunk.length-offset);if(!written.bytesWritten)throw Error('Restore write made no progress');offset+=written.bytesWritten;}hash.update(chunk);size+=chunk.length;}
        if(size!==e.byteSize || hash.digest('hex')!==e.sha256 || r.ETag!==b.etag || (b.versionId && r.VersionId!==b.versionId))throw Error('Restore checksum or immutable identity mismatch');
        await handle.sync();await handle.close();
        await noSymlinkPath(restoreRoot,path.dirname(dest));
        await fsp.link(tmp,dest);await fsp.unlink(tmp);
        if(options['discard-after-check']){
          const restored=await stableRead(dest,restoreRoot);
          try{if(restored.sha256!==e.sha256 || restored.sourceIdentity.size!==e.byteSize)throw Error('Restored file checksum mismatch');}finally{await restored.handle.close();}
          await fsp.unlink(dest);
        }
      }catch(error){await handle.close().catch(()=>{});await fsp.unlink(tmp).catch(()=>{});throw error;}
    });console.log(JSON.stringify({restored:true,...result}));return;
  }
  if(options.command==='prune') {
    if(options['services-stopped']!==true)throw Error('prune requires --services-stopped after stopping every managed app service');
    if(!options.path || !options.acceptance)throw Error('prune requires --path and reviewed --acceptance receipt');
    const acceptance=JSON.parse(await fsp.readFile(options.acceptance,'utf8'));
    if(acceptance.manifestSha256!==manifestSha256 || acceptance.verificationSha256!==digest(verifiedRaw) || !sameStorage(acceptance.storage,storage) || acceptance.remoteReadPassed!==true || acceptance.restorePassed!==true || acceptance.studentPlaybackPassed!==true || !Array.isArray(acceptance.allowedPrefixes) || !acceptance.allowedPrefixes.includes(options.path))throw Error('Exact storage-bound student playback, remote-read, restore and scope acceptance required');
    const retained=new Set(acceptance.retainedPaths || []);
    if([...retained].some(p=>!m.files.some(e=>e.path===p)))throw Error('Retained paths must be exact manifest files');
    const selected=m.files.filter(e=>(e.path===options.path || e.path.startsWith(options.path.replace(/\/$/,'')+'/')) && !retained.has(e.path));
    if(!selected.length)throw Error('No files selected');
    let removed=0,bytes=0;
    for(const e of selected){
      const source=sourcePath(e.path,root);await noSymlinkPath(root,source,true);if(!fs.existsSync(source))continue;
      const read=await stableRead(source,root);
      try{if(!sameIdentity(e.sourceIdentity,read.sourceIdentity) || read.sha256!==e.sha256)throw Error('Changed source retained: '+e.path);}finally{await read.handle.close();}
      await remoteHash(client,c,e,verified.blobs[e.sha256]);
      await quarantineAndPrune({source,entry:e,root,quarantineRoot:path.join(dir,'quarantine'),receipt:path.join(dir,'pruned.jsonl')},dependencies.quarantineOperations || fsp);
      removed++;bytes+=e.byteSize;
    }
    console.log(JSON.stringify({pruned:true,files:removed,bytes}));return;
  }
  throw Error('Unknown command');
}
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  run(args(process.argv.slice(2))).catch(e=>{console.error(JSON.stringify({error:e.name,message:String(e.message).slice(0,300)}));process.exitCode=1;});
}
