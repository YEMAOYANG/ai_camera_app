import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {uploadCourseStorageFile,readInput} from './course-storage-file.mjs';

const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function fixture(){
  const bytes=Buffer.from('{"draft":"原稿"}'),config={endpoint:'http://storage.invalid:9000',bucket:'study',region:'us-east-1',
    accessKeyId:'fixture-only',secretAccessKey:'fixture-only'};
  const input={objectKey:'语文/统编版/一年级上册/2026-10-23/天地人/天地人-工作记录-20261023-unique.json',
    sha256:digest(bytes),byteSize:bytes.length,mimeType:'application/json',bodyBase64:bytes.toString('base64'),
    storage:{endpoint:config.endpoint,bucket:config.bucket,region:config.region}};
  const calls=[],responses={etag:'"fixture-etag"',version:'fixture-version',bytes};
  const client={async send(command){
    calls.push(command);
    if(command.constructor.name==='PutObjectCommand')return {ETag:responses.etag,VersionId:responses.version};
    return {ETag:responses.remoteEtag??responses.etag,VersionId:responses.remoteVersion??responses.version,
      ContentLength:responses.size??bytes.length,ContentType:responses.mime??input.mimeType,
      Metadata:{sha256:responses.sha??input.sha256},Body:Readable.from([responses.bytes])};
  }};
  return {bytes,input,config,client,calls,responses};
}

test('new immutable work record is put exclusively then GET pinned and fully hashed',async()=>{
  const f=fixture(),result=await uploadCourseStorageFile(f.input,f);
  assert.deepEqual(result,{objectKey:f.input.objectKey,etag:'"fixture-etag"',versionId:'fixture-version',
    sha256:f.input.sha256,byteSize:f.bytes.length,storage:f.input.storage});
  assert.equal(f.calls.length,2);const put=f.calls[0].input,get=f.calls[1].input;
  assert.equal(put.IfNoneMatch,'*');assert.equal(put.Metadata.sha256,f.input.sha256);
  assert.equal(get.IfMatch,result.etag);assert.equal(get.VersionId,result.versionId);
  assert(!JSON.stringify(result).includes('fixture-only'));
});

test('storage owner, byte hash, JSON, MIME, paths and exact input reject before any remote operation',async()=>{
  const cases=[{storage:{endpoint:'http://other.invalid',bucket:'study',region:'us-east-1'}},
    {sha256:'f'.repeat(64)},{byteSize:1},{bodyBase64:'%%%='},{objectKey:'../secret.json'},
    {objectKey:'语文/统编版/一年级上册/2026-02-30/天地人/record.json'},
    {objectKey:'语文/统编版/一年级上册/2026-10-23/天地人/.env.json'},
    {mimeType:'text/html'},{secretAccessKey:'must-not-pass'}];
  for(const change of cases){const f=fixture();await assert.rejects(uploadCourseStorageFile({...f.input,...change},f));assert.equal(f.calls.length,0);}
  const f=fixture(),bytes=Buffer.from('not JSON');
  await assert.rejects(uploadCourseStorageFile({...f.input,bodyBase64:bytes.toString('base64'),byteSize:bytes.length,sha256:digest(bytes)},f));
  assert.equal(f.calls.length,0);
});

test('remote identity, metadata, size and actual full bytes must all match before descriptor',async()=>{
  for(const change of [{remoteEtag:'"different"'},{remoteVersion:'different'},{size:1},{mime:'text/plain'},
    {sha:'f'.repeat(64)},{bytes:Buffer.from('same-length-wrong')},{bytes:Buffer.alloc(100)}]){
    const f=fixture();Object.assign(f.responses,change);await assert.rejects(uploadCourseStorageFile(f.input,f));
    assert.equal(f.calls.length,2);
  }
});

test('conditional PUT failure never proceeds to GET or deletes an object',async()=>{
  const f=fixture();f.client.send=async command=>{f.calls.push(command);throw Error('PreconditionFailed');};
  await assert.rejects(uploadCourseStorageFile(f.input,f));
  assert.deepEqual(f.calls.map(c=>c.constructor.name),['PutObjectCommand']);
});

test('stdin accepts bounded JSON chunks and rejects malformed input',async()=>{
  const f=fixture();assert.deepEqual(await readInput(Readable.from([JSON.stringify(f.input)])),f.input);
  await assert.rejects(readInput(Readable.from(['{bad}'])));
});

test('strict UTF-8 JSON and larger canonical base64 are validated before upload',async()=>{
  const f=fixture(),bad=Buffer.from([0x22,0xff,0x22]);
  await assert.rejects(uploadCourseStorageFile({...f.input,bodyBase64:bad.toString('base64'),byteSize:bad.length,sha256:digest(bad)},f));
  assert.equal(f.calls.length,0);
  const valid=Buffer.from(JSON.stringify({draft:'课件'.repeat(30_000)}));
  f.responses.bytes=valid;f.responses.size=valid.length;f.responses.sha=digest(valid);
  const result=await uploadCourseStorageFile({...f.input,bodyBase64:valid.toString('base64'),byteSize:valid.length,sha256:digest(valid)},f);
  assert.equal(result.byteSize,valid.length);
});
