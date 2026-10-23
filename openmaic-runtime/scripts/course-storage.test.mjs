import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { Readable } from 'node:stream';
import { allowedSource, safePath, ROOT, run, storageIdentity } from './course-storage.mjs';

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
  await fs.writeFile(releaseIndex,JSON.stringify({schemaVersion:'mira.course-storage.releases.v1',releases:[{classroomId:backend?'stage-test_1':classroom,contentKey:backend?null:'b'.repeat(64),releaseSha256:'a'.repeat(64),media:[media]}]}));
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
