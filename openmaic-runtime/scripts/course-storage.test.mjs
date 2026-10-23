import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { Readable } from 'node:stream';
import { allowedSource, safePath, ROOT, run, storageIdentity, validNamedKey, displayName } from './course-storage.mjs';

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const classroom='tbpub_b8818f097ddcce4fe6bbd43b';
const base='openmaic-runtime/.runtime/OpenMAIC/data/classrooms/';

test('public candidates permit native/stage media and only controlled backend WAV paths',()=>{
  assert.equal(allowedSource(base+classroom+'/audio/a.mp3'),true);
  assert.equal(allowedSource(base+classroom+'/media/a.webp'),true);
  assert.equal(allowedSource(base+'stage-abc_123/media/a.png'),true);
  assert.equal(allowedSource('backend/data/learning-media/narration/catalog_build_item_abc/formal_narration_safe-'+ 'a'.repeat(64)+'.wav'),true);
  for(const value of [base+'private-original/audio/a.mp3',base+classroom+'/classroom.json',
    base+classroom+'/audio/../owner.cookies',base+classroom+'/audio/nested/a.mp3',
    'output/course/owner.cookies','backend/.env',base+classroom+'/media/a.webp/child',
    'backend/data/learning-media/narration/catalog_build_item_abc/owner.cookies',
    'backend/data/learning-media/narration/arbitrary/formal_narration_safe-'+ 'a'.repeat(64)+'.wav',
    ...['owner.cookies','.env','prepared-release.json','database-before-publication.json','source.html','archive.tar.gz'].map(n=>base+classroom+'/audio/'+n)])assert.equal(allowedSource(value),false,value);
});
test('source resolution rejects paths outside the project',()=>{
  assert.equal(safePath('output/course/a.json'),path.join(ROOT,'output/course/a.json'));
  for(const value of ['../outside','/etc/passwd','output/../a','output/./a','output/a\0','output/a\\b'])assert.throws(()=>safePath(value));
});

class MemoryS3 {
  constructor(key,bytes){this.key=key;this.bytes=Buffer.from(bytes);this.etag='"fixture-etag"';this.versionId='fixture-version';this.calls=[];}
  async send(command){
    const kind=command.constructor.name;const input=command.input;this.calls.push({kind,input});
    if(kind==='GetObjectCommand'){
      if(this.onGet)await this.onGet();
      if(input.IfMatch && input.IfMatch!==this.etag)throw Error('PreconditionFailed');
      if(input.VersionId && input.VersionId!==this.versionId)throw Error('NoSuchVersion');
      return {Body:Readable.from([this.bytes]),ETag:this.etag,VersionId:this.versionId};
    }
    if(kind==='HeadObjectCommand')return {ContentLength:this.bytes.length,Metadata:{sha256:this.expectedSha},ETag:this.etag};
    if(kind==='PutObjectCommand')throw Error('Fixture objects must never be overwritten');
    throw Error('Unexpected S3 request '+kind);
  }
}

async function fixture(t,{backend=false}={}){
  const root=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR || os.tmpdir(),'storage-test-')));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const bytes=Buffer.from('fixture published audio bytes');const checksum=sha(bytes);
  const relative=backend ? 'backend/data/learning-media/narration/catalog_build_item_test/formal_narration_fixture-'+checksum+'.wav' : base+classroom+'/audio/'+checksum+'.mp3';
  const source=path.join(root,relative);await fs.mkdir(path.dirname(source),{recursive:true});await fs.writeFile(source,bytes);
  const config={endpoint:'https://media.example.test',bucket:'study',prefix:'mira-courseware/v1',region:'us-east-1'};
  const state=path.join(root,'state');const manifest=path.join(root,'manifest.json');const releaseIndex=path.join(root,'releases.json');
  const media=backend ? {path:'/mira/runtime-audio/formal_narration_fixture',sourcePath:relative,sha256:checksum,byteSize:bytes.length,mimeType:'audio/wav'} : {path:'/api/classroom-media/'+classroom+'/audio/'+checksum+'.mp3',sha256:checksum,byteSize:bytes.length,mimeType:'audio/mpeg'};
  await fs.writeFile(releaseIndex,JSON.stringify({schemaVersion:'mira.course-storage.releases.v1',ok:true,allPublishedCourseMediaCovered:true,releases:[{classroomId:backend?'stage-test_1':classroom,courseId:'course-test',courseVersion:'1',title:'金木水火土',subjectName:'语文',gradeLabel:'一年级',volumeLabel:'上册',contentKey:backend?null:'b'.repeat(64),releaseSha256:'a'.repeat(64),media:[media]}]}));
  const client=new MemoryS3(config.prefix+'/blobs/sha256/'+checksum,bytes);client.expectedSha=checksum;
  const dependencies={root,state,config,client};await run({command:'inventory',manifest,'release-index':releaseIndex,snapshot:'fixture'},dependencies);
  const dir=path.join(state,'transfers/fixture');const fx={root,bytes,checksum,relative,source,config,state,manifest,releaseIndex,client,dependencies,dir};
  fx.verify=()=>run({command:'verify',manifest},dependencies);
  fx.accept=async(extra={})=>{
    const verification=await fs.readFile(path.join(dir,'verified-complete.json'));const file=path.join(root,'acceptance.json');
    await fs.writeFile(file,JSON.stringify({manifestSha256:sha(await fs.readFile(manifest)),verificationSha256:sha(verification),storage:storageIdentity(config),remoteReadPassed:true,restorePassed:true,studentPlaybackPassed:true,allowedPrefixes:[relative],...extra}));return file;
  };
  fx.prune=async(extra={},deps={})=>run({command:'prune',manifest,path:relative,acceptance:extra.acceptance || await fx.accept(),'services-stopped':true,...extra},{...dependencies,...deps});
  return fx;
}

test('verify binds complete bytes to endpoint, bucket, prefix, ETag and version',async t=>{
  const f=await fixture(t);await f.verify();const v=JSON.parse(await fs.readFile(path.join(f.dir,'verified-complete.json')));
  assert.equal(v.schemaVersion,'mira.course-storage.verification.v2');assert.deepEqual(v.storage,storageIdentity(f.config));
  assert.deepEqual(v.blobs[f.checksum],{objectKey:f.client.key,sha256:f.checksum,byteSize:f.bytes.length,etag:f.client.etag,versionId:f.client.versionId});
  for(const [key,value] of [['endpoint','https://other.example.test'],['bucket','other-bucket'],['prefix','different/prefix'],['region','different-region']])await assert.rejects(run({command:'activate',manifest:f.manifest},{...f.dependencies,config:{...f.config,[key]:value}}),/verification|manifest/i);
  assert.deepEqual(await fs.readFile(f.source),f.bytes);
});
test('upload never overwrites an existing blob; verify rejects misleading HEAD metadata',async t=>{
  const f=await fixture(t);f.client.bytes=Buffer.alloc(f.bytes.length,88);await run({command:'upload',manifest:f.manifest},f.dependencies);
  assert.equal(f.client.calls.filter(c=>c.kind==='PutObjectCommand').length,0);await assert.rejects(f.verify(),/Operation incomplete/);assert.deepEqual(await fs.readFile(f.source),f.bytes);
});
test('prune requires stopped services and exact playback, restore, storage and scope acceptance',async t=>{
  const f=await fixture(t);await f.verify();await assert.rejects(f.prune({'services-stopped':false}),/services-stopped/);
  for(const change of [{studentPlaybackPassed:false},{restorePassed:false},{remoteReadPassed:false},{verificationSha256:'0'.repeat(64)},{storage:{...storageIdentity(f.config),endpoint:'https://wrong.example.test'}},{allowedPrefixes:[base]}])await assert.rejects(f.prune({acceptance:await f.accept(change)}),/acceptance/);
  assert.deepEqual(await fs.readFile(f.source),f.bytes);
});
test('prune downloads full bytes with IfMatch and retains sources if remote bytes changed',async t=>{
  const f=await fixture(t);await f.verify();f.client.bytes=Buffer.alloc(f.bytes.length,90);await assert.rejects(f.prune(),/checksum/);
  const request=f.client.calls.at(-1);assert.equal(request.kind,'GetObjectCommand');assert.equal(request.input.IfMatch,f.client.etag);assert.equal(request.input.VersionId,f.client.versionId);assert.deepEqual(await fs.readFile(f.source),f.bytes);
});
test('source changed during remote GET is retained',async t=>{
  const f=await fixture(t);await f.verify();const changed=Buffer.from('new authoring content must survive');f.client.onGet=()=>fs.writeFile(f.source,changed);
  await assert.rejects(f.prune(),/Changed source retained/);assert.deepEqual(await fs.readFile(f.source),changed);
});
test('changed quarantined bytes are recovered to the absent source path',async t=>{
  const f=await fixture(t);await f.verify();const changed=Buffer.from('changed after rename');
  const operations={...fs,rename:async(a,b)=>{await fs.rename(a,b);await fs.writeFile(b,changed);}};
  await assert.rejects(f.prune({}, {quarantineOperations:operations}),/restored/);assert.deepEqual(await fs.readFile(f.source),changed);
});
test('quarantine recovery never overwrites a concurrent source replacement',async t=>{
  const f=await fixture(t);await f.verify();const replacement=Buffer.from('concurrent replacement'),retained=Buffer.from('quarantine changed bytes');let quarantined;
  const operations={...fs,rename:async(a,b)=>{await fs.rename(a,b);quarantined=b;await fs.writeFile(b,retained);await fs.writeFile(a,replacement);}};
  await assert.rejects(f.prune({}, {quarantineOperations:operations}),/private quarantine/);assert.deepEqual(await fs.readFile(f.source),replacement);assert.deepEqual(await fs.readFile(quarantined),retained);
});
test('successful prune removes only exact published media and keeps raw/cookie fixtures',async t=>{
  const f=await fixture(t);await f.verify();const raw=path.join(f.root,base,'stage-original/audio/raw.wav'),cookie=path.join(f.root,'output/lesson/owner.cookies');
  await fs.mkdir(path.dirname(raw),{recursive:true});await fs.mkdir(path.dirname(cookie),{recursive:true});await fs.writeFile(raw,'original');await fs.writeFile(cookie,'fake fixture cookie');
  await f.prune();await assert.rejects(fs.stat(f.source),{code:'ENOENT'});assert.equal(await fs.readFile(raw,'utf8'),'original');assert.equal(await fs.readFile(cookie,'utf8'),'fake fixture cookie');
  const records=(await fs.readFile(path.join(f.dir,'pruned.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);assert.deepEqual(records.map(r=>r.status),['quarantine-intent','pruned']);
});
test('inventory rejects symlinked ancestors',async t=>{
  const f=await fixture(t);const audio=path.dirname(f.source);await fs.rename(audio,audio+'-real');await fs.symlink(audio+'-real',audio);
  await assert.rejects(run({command:'inventory',manifest:f.manifest,'release-index':f.releaseIndex},f.dependencies),/Symlink/);
});
test('restore validates immutable bytes, refuses changed files and rejects destination links',async t=>{
  const f=await fixture(t);await f.verify();const destination=path.join(f.root,'restored');await run({command:'restore',manifest:f.manifest,path:f.relative,destination},f.dependencies);
  const restored=path.join(destination,f.relative);assert.deepEqual(await fs.readFile(restored),f.bytes);await fs.writeFile(restored,'retain changed local file');
  await assert.rejects(run({command:'restore',manifest:f.manifest,path:f.relative,destination},f.dependencies),/Operation incomplete/);assert.equal(await fs.readFile(restored,'utf8'),'retain changed local file');
  const bad=path.join(f.root,'symlink-restore'),outside=path.join(f.root,'outside');await fs.mkdir(bad);await fs.mkdir(outside);await fs.symlink(outside,path.join(bad,'openmaic-runtime'));
  await assert.rejects(run({command:'restore',manifest:f.manifest,path:f.relative,destination:bad},f.dependencies),/Operation incomplete/);assert.deepEqual(await fs.readdir(outside),[]);
});
test('validated legacy stage receipts permit only the controlled backend sourcePath',async t=>{
  const f=await fixture(t,{backend:true});await f.verify();await f.prune();await assert.rejects(fs.stat(f.source),{code:'ENOENT'});
  const index=JSON.parse(await fs.readFile(f.releaseIndex));index.releases[0].media[0].sourcePath='backend/.env';await fs.writeFile(f.releaseIndex,JSON.stringify(index));
  await assert.rejects(run({command:'inventory',manifest:f.manifest,'release-index':f.releaseIndex},f.dependencies),/backend audio source/);
});

test('temporary restore checks re-read disk bytes and preserve the original source',async t=>{
  const f=await fixture(t);await f.verify();
  const destination=await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR || os.tmpdir(),'restore-check-'));
  t.after(()=>fs.rm(destination,{recursive:true,force:true}));
  await run({command:'restore',manifest:f.manifest,path:f.relative,destination,'discard-after-check':true},f.dependencies);
  await assert.rejects(fs.stat(path.join(destination,f.relative)),{code:'ENOENT'});
  assert.deepEqual(await fs.readFile(f.source),f.bytes);
  await assert.rejects(run({command:'restore',manifest:f.manifest,path:f.relative,destination:f.root,'discard-after-check':true},f.dependencies),/isolated destination/);
});

test('an exact retained published original is excluded from accepted pruning',async t=>{
  const f=await fixture(t);await f.verify();
  await assert.rejects(f.prune({acceptance:await f.accept({retainedPaths:[f.relative]})}),/No files selected/);
  assert.deepEqual(await fs.readFile(f.source),f.bytes);
});

test('verification resumes only unchanged objects from the same storage identity',async t=>{
  const f=await fixture(t);f.client.versionId=undefined;await f.verify();
  const gets=()=>f.client.calls.filter(c=>c.kind==='GetObjectCommand').length;
  assert.equal(gets(),1);
  await run({command:'verify',manifest:f.manifest,resume:true},f.dependencies);
  assert.equal(gets(),1);
  const record=JSON.parse(await fs.readFile(path.join(f.dir,'verified-complete.json')));
  assert.equal(record.resumedObjects,1);
  const config={...f.config,endpoint:'https://different-storage.example.test'};
  await run({command:'verify',manifest:f.manifest,resume:true},{...f.dependencies,config});
  assert.equal(gets(),2);
});

class NamedBucket {
  constructor(f){this.key=f.client.key;this.etag=f.client.etag;this.objects=new Map([[f.client.key,{bytes:f.bytes,etag:f.client.etag,versionId:f.client.versionId}]]);this.calls=[];}
  async send(command){
    const kind=command.constructor.name,input=command.input;this.calls.push({kind,input});const object=this.objects.get(input.Key);
    if(kind==='HeadObjectCommand'){
      if(!object)throw Object.assign(Error('NotFound'),{$metadata:{httpStatusCode:404}});
      return {ContentLength:object.bytes.length,ETag:object.etag,VersionId:object.versionId};
    }
    if(kind==='GetObjectCommand'){
      if(!object)throw Error('NoSuchKey');
      if((input.IfMatch && input.IfMatch!==object.etag) || (input.VersionId && input.VersionId!==object.versionId))throw Error('PreconditionFailed');
      return {Body:Readable.from([object.bytes]),ETag:object.etag,VersionId:object.versionId};
    }
    if(kind==='PutObjectCommand'){
      assert.equal(input.IfNoneMatch,'*');if(object)throw Error('PreconditionFailed');
      const bytes=Buffer.from(input.Body);assert.equal(sha(bytes),input.Metadata.sha256);
      this.objects.set(input.Key,{bytes,etag:'"named-'+this.objects.size+'"'});return {ETag:this.objects.get(input.Key).etag};
    }
    if(kind==='DeleteObjectCommand'){
      if(object && input.IfMatch!==object.etag)throw Error('PreconditionFailed');
      this.objects.delete(input.Key);return {};
    }
    throw Error('Unexpected request '+kind);
  }
}

async function namedFixture(t){
  const f=await fixture(t);const index=JSON.parse(await fs.readFile(f.releaseIndex));
  const second=structuredClone(index.releases[0]);second.classroomId='tbpub_'+'c'.repeat(24);second.courseId='course-test-2';
  second.media[0].path=second.media[0].path.replace(classroom,second.classroomId);index.releases.push(second);
  await fs.writeFile(f.releaseIndex,JSON.stringify(index));
  const secondRelative=f.relative.replace(classroom,second.classroomId);const secondSource=path.join(f.root,secondRelative);
  await fs.mkdir(path.dirname(secondSource),{recursive:true});await fs.writeFile(secondSource,f.bytes);
  await run({command:'inventory',manifest:f.manifest,'release-index':f.releaseIndex,snapshot:'fixture'},f.dependencies);await f.verify();
  // Existing verified remote objects remain usable after local copy pruning.
  await fs.unlink(f.source);await fs.unlink(secondSource);
  const config={...f.config,prefix:'2026-10-23'},client=new NamedBucket(f),dependencies={...f.dependencies,config,client};
  const manifest=path.join(f.root,'named-manifest.json');
  const sourceOptions={'source-manifest':f.manifest,'source-prefix':f.config.prefix};
  await run({command:'layout',manifest,'release-index':f.releaseIndex,date:config.prefix,snapshot:'named',...sourceOptions},dependencies);
  return {...f,config,client,dependencies,namedManifest:manifest,sourceOptions};
}

test('readable names reject unsafe layout keys and normalize titles',()=>{
  const key='2026-10-23/语文/一年级上册-金木水火土/金木水火土-音频-001.mp3';
  assert.equal(validNamedKey(key,'2026-10-23','audio/mpeg'),true);
  for(const bad of [key.replace('语文/','../'),key+'/x',key.replace('语文/',' /'),key.replace('语文/','语\\文/'),key.replace('.mp3','.json'),key.replace('语文/','语\u0085文/')])assert.equal(validNamedKey(bad,'2026-10-23','audio/mpeg'),false,bad);
  assert.equal(displayName(' ../金木:水火土? '),'金木-水火土');
});

test('named layout freezes readable collision-free keys without local sources',async t=>{
  const f=await namedFixture(t),m=JSON.parse(await fs.readFile(f.namedManifest));
  assert.equal(m.schemaVersion,'mira.course-storage.manifest.v2');assert.equal(m.files.length,2);
  assert.equal(new Set(m.files.map(e=>e.objectKey)).size,2);assert.equal(new Set(m.files.map(e=>e.sha256)).size,1);
  assert(m.files.every(e=>e.objectKey.startsWith('2026-10-23/语文/一年级-上册-金木水火土')));
  assert(m.files.every(e=>!e.objectKey.includes(e.sha256)));assert(m.files[1].objectKey.includes('版本2'));
  await assert.rejects(run({command:'layout',manifest:f.namedManifest,'release-index':f.releaseIndex,date:f.config.prefix,...f.sourceOptions},f.dependencies),/overwrite/);
});

test('named relocation and verification cover every key even when SHA is shared',async t=>{
  const f=await namedFixture(t);await run({command:'relocate',manifest:f.namedManifest,...f.sourceOptions},f.dependencies);
  const m=JSON.parse(await fs.readFile(f.namedManifest));
  assert.equal(f.client.calls.filter(c=>c.kind==='PutObjectCommand').length,2);
  await run({command:'verify',manifest:f.namedManifest},f.dependencies);
  const v=JSON.parse(await fs.readFile(path.join(f.state,'transfers/named/verified-complete.json')));
  assert.equal(v.schemaVersion,'mira.course-storage.verification.v3');assert.equal(v.objects,2);
  assert.deepEqual(Object.keys(v.blobs).sort(),m.files.map(e=>e.objectKey).sort());
  const gets=f.client.calls.filter(c=>c.kind==='GetObjectCommand').length;
  await run({command:'verify',manifest:f.namedManifest,resume:true},f.dependencies);
  assert.equal(f.client.calls.filter(c=>c.kind==='GetObjectCommand').length,gets);
  const destination=path.join(f.root,'restored-named');await run({command:'restore',manifest:f.namedManifest,path:base,destination},f.dependencies);
  for(const e of m.files)assert.deepEqual(await fs.readFile(path.join(destination,e.path)),f.bytes);
  f.client.objects.get(m.files[1].objectKey).bytes=Buffer.alloc(f.bytes.length,85);
  await assert.rejects(run({command:'verify',manifest:f.namedManifest},f.dependencies),/checksum/);
});

test('named relocation refuses corrupt existing targets without overwriting them',async t=>{
  const f=await namedFixture(t);const m=JSON.parse(await fs.readFile(f.namedManifest));
  const bytes=Buffer.from('retain unknown existing object');f.client.objects.set(m.files[0].objectKey,{bytes,etag:'"unknown"'});
  await assert.rejects(run({command:'relocate',manifest:f.namedManifest,...f.sourceOptions},f.dependencies),/checksum/);
  assert.deepEqual(f.client.objects.get(m.files[0].objectKey).bytes,bytes);
});

test('old objects retire only after complete active named-layout acceptance',async t=>{
  const f=await namedFixture(t);await run({command:'relocate',manifest:f.namedManifest,...f.sourceOptions},f.dependencies);
  await run({command:'verify',manifest:f.namedManifest},f.dependencies);
  const m=JSON.parse(await fs.readFile(f.namedManifest));const verified=await fs.readFile(path.join(f.state,'transfers/named/verified-complete.json'));
  const acceptance=path.join(f.root,'retire-acceptance.json'),record={manifestSha256:sha(await fs.readFile(f.namedManifest)),verificationSha256:sha(verified),storage:storageIdentity(f.config),remoteReadPassed:true,restorePassed:true,studentPlaybackPassed:true,oldSourceConsumersDetached:true,retireSourceManifestSha256:m.sourceManifestSha256};
  const retire=()=>run({command:'retire-source',manifest:f.namedManifest,acceptance,...f.sourceOptions},f.dependencies);
  await fs.writeFile(acceptance,JSON.stringify(record));await assert.rejects(retire(),/ENOENT/);
  await run({command:'activate',manifest:f.namedManifest},f.dependencies);
  await fs.writeFile(acceptance,JSON.stringify({...record,oldSourceConsumersDetached:false}));await assert.rejects(retire(),/acceptance/);
  await fs.writeFile(acceptance,JSON.stringify(record));
  f.client.objects.set('unlisted/private.json',{bytes:Buffer.from('keep'),etag:'"private"'});
  const target=f.client.objects.get(m.files[0].objectKey),bytes=target.bytes;target.bytes=Buffer.alloc(bytes.length,90);
  await assert.rejects(retire(),/checksum/);assert(f.client.objects.has(f.client.key));
  target.bytes=bytes;await retire();assert(!f.client.objects.has(f.client.key));
  assert(f.client.objects.has('unlisted/private.json'));for(const e of m.files)assert(f.client.objects.has(e.objectKey));
  const deletes=f.client.calls.filter(c=>c.kind==='DeleteObjectCommand');assert.equal(deletes.length,1);assert.equal(deletes[0].input.IfMatch,f.client.etag);
  await retire();assert.equal(f.client.calls.filter(c=>c.kind==='DeleteObjectCommand').length,1);
});

test('retirement aborts pending workers after the first old-object deletion fails',{timeout:5000},async t=>{
  const f=await fixture(t),index=JSON.parse(await fs.readFile(f.releaseIndex)),client=new NamedBucket(f);
  for(let i=1;i<=2;i++){
    const bytes=Buffer.from('distinct published narration '+i),checksum=sha(bytes);
    const relative=path.dirname(f.relative)+'/'+checksum+'.mp3';
    await fs.writeFile(path.join(f.root,relative),bytes);
    index.releases[0].media.push({path:'/api/classroom-media/'+classroom+'/audio/'+checksum+'.mp3',
      sha256:checksum,byteSize:bytes.length,mimeType:'audio/mpeg'});
    client.objects.set(f.config.prefix+'/blobs/sha256/'+checksum,{bytes,etag:'"old-'+i+'"'});
  }
  await fs.writeFile(f.releaseIndex,JSON.stringify(index));
  const oldDependencies={...f.dependencies,client};
  await run({command:'inventory',manifest:f.manifest,'release-index':f.releaseIndex,snapshot:'fixture'},oldDependencies);
  await run({command:'verify',manifest:f.manifest},oldDependencies);
  const old=JSON.parse(await fs.readFile(f.manifest)),oldKeys=old.files.map(e=>e.objectKey);
  assert.equal(new Set(old.files.map(e=>e.sha256)).size,3);
  for(const entry of old.files)await fs.unlink(path.join(f.root,entry.path));
  const config={...f.config,prefix:'2026-10-23'},dependencies={...oldDependencies,config};
  const manifest=path.join(f.root,'named-abort-manifest.json'),sourceOptions={'source-manifest':f.manifest,'source-prefix':f.config.prefix};
  await run({command:'layout',manifest,'release-index':f.releaseIndex,date:config.prefix,snapshot:'named-abort',...sourceOptions},dependencies);
  await run({command:'relocate',manifest,...sourceOptions},dependencies);
  await run({command:'verify',manifest},dependencies);
  await run({command:'activate',manifest},dependencies);
  const named=JSON.parse(await fs.readFile(manifest)),dir=path.join(f.state,'transfers/named-abort');
  const verification=await fs.readFile(path.join(dir,'verified-complete.json')),acceptance=path.join(f.root,'abort-acceptance.json');
  await fs.writeFile(acceptance,JSON.stringify({manifestSha256:sha(await fs.readFile(manifest)),
    verificationSha256:sha(verification),storage:storageIdentity(config),remoteReadPassed:true,
    restorePassed:true,studentPlaybackPassed:true,oldSourceConsumersDetached:true,
    retireSourceManifestSha256:named.sourceManifestSha256}));
  let releaseSecondHead,secondHeadStarted=false;
  const secondHead=new Promise(resolve=>{releaseSecondHead=resolve;}),send=client.send.bind(client);
  client.calls=[];
  client.send=async command=>{
    const kind=command.constructor.name,input=command.input;
    if(kind==='HeadObjectCommand' && input.Key===oldKeys[1]){
      secondHeadStarted=true;await secondHead;
    }
    if(kind==='DeleteObjectCommand' && input.Key===oldKeys[0]){
      client.calls.push({kind,input});
      // Resume the in-flight second worker only after the first rejection's
      // catch has set the abort flag. The third object has not started yet.
      setImmediate(releaseSecondHead);
      throw Error('simulated first old-object delete failure');
    }
    return send(command);
  };
  await assert.rejects(run({command:'retire-source',manifest,acceptance,concurrency:2,...sourceOptions},dependencies),
    /simulated first old-object delete failure/);
  assert.equal(secondHeadStarted,true);
  assert.deepEqual(client.calls.filter(c=>c.kind==='DeleteObjectCommand').map(c=>c.input.Key),[oldKeys[0]]);
  assert(!client.calls.some(c=>c.kind==='HeadObjectCommand' && c.input.Key===oldKeys[2]));
  for(const key of [...oldKeys,...named.files.map(e=>e.objectKey)])assert(client.objects.has(key),key);
  await assert.rejects(fs.stat(path.join(dir,'retired-source.jsonl')),{code:'ENOENT'});
});

test('local pruning refuses unexplained missing files',async t=>{
  const f=await fixture(t);await f.verify();await fs.unlink(f.source);
  await assert.rejects(f.prune(),/no matching pruning receipt/);
});

test('parallel pruning stops further deletions on a changed source',async t=>{
  const f=await fixture(t),index=JSON.parse(await fs.readFile(f.releaseIndex));
  const relatives=[];
  for(let i=0;i<8;i++){
    const relative=path.dirname(f.relative)+'/extra-'+i+'.mp3';relatives.push(relative);
    await fs.writeFile(path.join(f.root,relative),f.bytes);
    index.releases[0].media.push({...index.releases[0].media[0],path:'/api/classroom-media/'+classroom+'/audio/extra-'+i+'.mp3'});
  }
  await fs.writeFile(f.releaseIndex,JSON.stringify(index));
  await run({command:'inventory',manifest:f.manifest,'release-index':f.releaseIndex,snapshot:'fixture'},f.dependencies);await f.verify();
  await fs.writeFile(f.source,'retain changed source');
  // Other workers may reach GET while the first worker discovers the change.
  // Their completed downloads must not advance into quarantine/deletion.
  f.client.onGet=()=>new Promise(resolve=>setTimeout(resolve,20));
  await assert.rejects(f.prune({path:base,concurrency:4,acceptance:await f.accept({allowedPrefixes:[base]})}),/Changed source/);
  assert.equal(await fs.readFile(f.source,'utf8'),'retain changed source');
  for(const relative of relatives)assert.deepEqual(await fs.readFile(path.join(f.root,relative)),f.bytes);
  await assert.rejects(fs.stat(path.join(f.dir,'pruned.jsonl')),{code:'ENOENT'});
});

test('previous pruning receipts are exact, hash-bound and needed for missing sources',async t=>{
  const f=await fixture(t);await f.verify();const previous=path.join(f.state,'previous-pruned.jsonl');
  const record={status:'pruned',path:f.relative,sha256:f.checksum,byteSize:f.bytes.length};
  await fs.writeFile(previous,JSON.stringify(record)+'\n');const priorSha=sha(await fs.readFile(previous));await fs.unlink(f.source);
  const acceptance=await f.accept({previousPruneReceipt:previous,previousPruneReceiptSha256:priorSha});
  await f.prune({acceptance});
  await fs.writeFile(previous,JSON.stringify({...record,sha256:'0'.repeat(64)})+'\n');
  await assert.rejects(f.prune({acceptance}),/receipt changed/);
  await assert.rejects(f.prune({acceptance:await f.accept({previousPruneReceipt:previous,previousPruneReceiptSha256:sha(await fs.readFile(previous))})}),/no matching pruning receipt/);
});
