#!/usr/bin/env node
/** Upload one immutable JSON work record, then verify its complete remote bytes. */
import crypto from 'node:crypto';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {ROOT,readConfig} from './course-storage.mjs';

const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {S3Client,PutObjectCommand,GetObjectCommand}=require('@aws-sdk/client-s3');
export const MAX_FILE_BYTES=64*1024*1024;
const MAX_INPUT_BYTES=Math.ceil(MAX_FILE_BYTES/3)*4+32*1024;
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const fail=()=>{throw Error('course_storage_file_upload_failed');};

function storageIdentity(value){
  if(!value || typeof value!=='object' || Array.isArray(value))fail();
  const {endpoint,bucket,region}=value;
  let url;try{url=new URL(endpoint);}catch{fail();}
  if(typeof endpoint!=='string' || !['http:','https:'].includes(url.protocol) || url.username || url.password ||
     url.pathname!=='/' || url.search || url.hash || typeof bucket!=='string' ||
     !/^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(bucket) || bucket.includes('..') ||
     typeof region!=='string' || !/^[A-Za-z0-9_-]+$/.test(region))fail();
  return {endpoint:url.origin,bucket,region};
}

function workRecordKey(key){
  if(typeof key!=='string' || Buffer.byteLength(key)>1024)return false;
  const parts=key.split('/');
  if(parts.length!==6 || !/^\d{4}-\d{2}-\d{2}$/.test(parts[3]) || !parts[5].endsWith('.json'))return false;
  const date=new Date(parts[3]);
  return Number.isFinite(date.valueOf()) && date.toISOString().slice(0,10)===parts[3] &&
    parts.every(p=>p.trim()===p && p && p!=='.' && p!=='..' && Buffer.byteLength(p)<=255 &&
      !/[\\\x00-\x1f\x7f-\x9f]/.test(p) && !/^(?:\.env(?:\..*)?|owner\.cookies|.*\.pem|.*\.key)$/i.test(p));
}

export async function uploadCourseStorageFile(input,dependencies={}){
  if(!input || typeof input!=='object' || Array.isArray(input) ||
     Object.keys(input).sort().join(',')!=='bodyBase64,byteSize,mimeType,objectKey,sha256,storage' ||
     !workRecordKey(input.objectKey) || !/^[a-f0-9]{64}$/.test(input.sha256??'') ||
     !Number.isSafeInteger(input.byteSize) || input.byteSize<1 || input.byteSize>MAX_FILE_BYTES ||
     input.mimeType!=='application/json' || typeof input.bodyBase64!=='string' ||
     input.bodyBase64.length>Math.ceil(MAX_FILE_BYTES/3)*4 ||
     Object.keys(input.storage??{}).sort().join(',')!=='bucket,endpoint,region')fail();
  const bytes=Buffer.from(input.bodyBase64,'base64');
  if(bytes.length!==input.byteSize || bytes.toString('base64')!==input.bodyBase64 || hash(bytes)!==input.sha256)fail();
  try{JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));}catch{fail();}
  const config=dependencies.config??readConfig();
  const owner=storageIdentity(config),requested=storageIdentity(input.storage);
  if(JSON.stringify(owner)!==JSON.stringify(requested))fail();
  const client=dependencies.client??new S3Client({endpoint:config.endpoint,region:config.region,forcePathStyle:true,
    credentials:{accessKeyId:config.accessKeyId,secretAccessKey:config.secretAccessKey},maxAttempts:1,
    requestChecksumCalculation:'WHEN_REQUIRED',responseChecksumValidation:'WHEN_REQUIRED'});
  const put=await client.send(new PutObjectCommand({Bucket:config.bucket,Key:input.objectKey,Body:bytes,
    ContentLength:bytes.length,ContentType:input.mimeType,Metadata:{sha256:input.sha256},
    ChecksumSHA256:Buffer.from(input.sha256,'hex').toString('base64'),IfNoneMatch:'*'}));
  if(typeof put.ETag!=='string' || !/^"[A-Za-z0-9._-]+"$|^[A-Za-z0-9._-]+$/.test(put.ETag) ||
     (put.VersionId!==undefined && (typeof put.VersionId!=='string' || !put.VersionId || /[\r\n]/.test(put.VersionId))))fail();
  const remote=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:input.objectKey,IfMatch:put.ETag,
    ...(put.VersionId?{VersionId:put.VersionId}:{})}));
  if(remote.ETag!==put.ETag || (put.VersionId && remote.VersionId!==put.VersionId) ||
     remote.ContentLength!==bytes.length || remote.ContentType!==input.mimeType || remote.Metadata?.sha256!==input.sha256 ||
     !remote.Body?.[Symbol.asyncIterator]){remote.Body?.destroy?.();fail();}
  let count=0;const checksum=crypto.createHash('sha256');
  try{
    for await(const part of remote.Body){count+=part.length;if(count>bytes.length)fail();checksum.update(part);}
    if(count!==bytes.length || checksum.digest('hex')!==input.sha256)fail();
  }catch(error){remote.Body.destroy?.();throw error;}
  return {objectKey:input.objectKey,etag:put.ETag,...(put.VersionId?{versionId:put.VersionId}:{}),
    sha256:input.sha256,byteSize:bytes.length,storage:owner};
}

export async function readInput(stream){
  const parts=[];let count=0;
  for await(const part of stream){const b=Buffer.from(part);count+=b.length;if(count>MAX_INPUT_BYTES)fail();parts.push(b);}
  return JSON.parse(Buffer.concat(parts,count).toString('utf8'));
}

if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  Promise.resolve().then(async()=>{
    if(process.argv.length!==2)fail();
    return uploadCourseStorageFile(await readInput(process.stdin));
  }).then(result=>process.stdout.write(JSON.stringify(result)+'\n')).catch(()=>{
    process.stderr.write(JSON.stringify({error:'course_storage_file_upload_failed'})+'\n');process.exitCode=1;
  });
}
