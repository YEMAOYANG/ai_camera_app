import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';

import {ROOT,clientFor,readConfig} from './course-storage.mjs';


async function fixture(lines){
  const directory=await fs.mkdtemp(path.join(os.tmpdir(),'course-storage-config-'));
  const filename=path.join(directory,'.env');
  await fs.writeFile(filename,lines.join('\n')+'\n',{mode:0o600});
  return {filename,cleanup:()=>fs.rm(directory,{recursive:true,force:true})};
}

test('active MinIO and shadow Tencent COS keep independent addressing modes',async t=>{
  const f=await fixture([
    'COURSE_STORAGE_ENDPOINT=http://storage.invalid:9000',
    'COURSE_STORAGE_BUCKET=study',
    'COURSE_STORAGE_REGION=us-east-1',
    'COURSE_STORAGE_ACCESS_KEY=source-id',
    'COURSE_STORAGE_SECRET_KEY=source-secret',
    'COS_TARGET_PROVIDER=tencent-cos',
    'COS_TARGET_ENDPOINT=https://cos.ap-guangzhou.myqcloud.com',
    'COS_TARGET_BUCKET=study-1350855375',
    'COS_TARGET_REGION=ap-guangzhou',
    'COS_TARGET_ADDRESSING_STYLE=virtual',
    'COS_TARGET_ACCESS_KEY=target-id',
    'COS_TARGET_SECRET_KEY=target-secret',
  ]);t.after(f.cleanup);
  const source=readConfig(f.filename),target=readConfig(f.filename,'COS_TARGET');
  assert.equal(source.provider,'s3-compatible');assert.equal(source.addressingStyle,'path');
  assert.equal(target.provider,'tencent-cos');assert.equal(target.addressingStyle,'virtual');
  const sourceClient=clientFor(source),targetClient=clientFor(target);
  t.after(()=>sourceClient.destroy());t.after(()=>targetClient.destroy());
  assert.equal(sourceClient.config.forcePathStyle,true);
  assert.equal(targetClient.config.forcePathStyle,false);
});

test('Tencent COS rejects path style, insecure or bucket-specific endpoints',async t=>{
  const base=[
    'COS_TARGET_PROVIDER=tencent-cos','COS_TARGET_BUCKET=study-1350855375',
    'COS_TARGET_REGION=ap-guangzhou','COS_TARGET_ACCESS_KEY=id','COS_TARGET_SECRET_KEY=secret',
  ];
  for(const endpoint of ['http://cos.ap-guangzhou.myqcloud.com','https://study-1350855375.cos.ap-guangzhou.myqcloud.com']){
    const f=await fixture([...base,`COS_TARGET_ENDPOINT=${endpoint}`]);t.after(f.cleanup);
    assert.throws(()=>readConfig(f.filename,'COS_TARGET'),/Tencent COS/);
  }
  const f=await fixture([...base,'COS_TARGET_ENDPOINT=https://cos.ap-guangzhou.myqcloud.com','COS_TARGET_ADDRESSING_STYLE=path']);t.after(f.cleanup);
  assert.throws(()=>readConfig(f.filename,'COS_TARGET'),/Tencent COS/);
});

test('native launcher forwards active provider settings but excludes shadow credentials',async t=>{
  const f=await fixture([
    'COURSE_STORAGE_PROVIDER=tencent-cos',
    'COURSE_STORAGE_ADDRESSING_STYLE=virtual',
    'COS_TARGET_SECRET_KEY=shadow-must-not-forward',
  ]);t.after(f.cleanup);
  const forwarded=execFileSync('bash',['-c',
    'MIRA_BACKEND_ENV_FILE="$2"; source "$1"; load_course_storage_env; printf "%s\\n" "${OPENMAIC_COURSE_STORAGE_ENV[@]}"',
    'storage-fixture',path.join(ROOT,'openmaic-runtime/scripts/native-runtime.sh'),f.filename],{encoding:'utf8'});
  assert(forwarded.includes('COURSE_STORAGE_PROVIDER=tencent-cos\n'));
  assert(forwarded.includes('COURSE_STORAGE_ADDRESSING_STYLE=virtual\n'));
  assert(!forwarded.includes('COS_TARGET'));
  assert(!forwarded.includes('shadow-must-not-forward'));
});
