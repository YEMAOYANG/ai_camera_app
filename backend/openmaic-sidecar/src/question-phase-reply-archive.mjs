import {createHash} from 'node:crypto';
import {mkdir,open,rename,stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const QUESTION_PHASE_REPLY_ARCHIVE_SCHEMA = 'mira.openmaic.question-phase-reply-archive.v1';
const DEFAULT_ROOT = fileURLToPath(new URL('../../data/learning-provider-replies/', import.meta.url));
const sha = value => createHash('sha256').update(value).digest('hex');
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key,stable(value[key])])) : value;
const canonical = value => JSON.stringify(stable(value));

async function exclusiveWrite(file, value) {
  const handle = await open(file,'wx',0o600);
  try { await handle.writeFile(JSON.stringify(value)); await handle.sync(); }
  finally { await handle.close(); }
}

/** Only a normalized live request may create an intent, before any paid call.
 * The file is independent of successful/failed checkpoint receipts and is never
 * consumed as a passed review. Duplicate intents block another non-idempotent call.
 */
export async function prepareQuestionPhaseReplyArchive(request, {root,now = Date.now} = {}) {
  if (request.mode !== 'live') return null;
  if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/.test(request.requestId)
    || !/^[a-z_]{1,64}$/.test(request.phase)
    || !Number.isInteger(request.phaseOrdinal)) throw new TypeError('reply archive request identity is invalid');
  const directory=path.resolve(root || process.env.OPENMAIC_QUESTION_PHASE_REPLY_ARCHIVE_DIR || DEFAULT_ROOT);
  await mkdir(directory,{recursive:true,mode:0o700});
  const inputSha256=sha(canonical(request));
  const metadata={
    requestId:request.requestId,phase:request.phase,phaseOrdinal:request.phaseOrdinal,
    gradeCode:request.gradeCode,subject:request.subject,skillId:request.skillBoundary.skillId,
    difficultyCode:request.objectivePolicy?.difficultyCode ?? null,
    inputSha256,providerProfileSha256:sha(canonical(request.provider)),createdAt:now(),
  };
  const basename=`${request.phase}.${inputSha256}`;
  const finalPath=path.join(directory,`${basename}.json`);
  try {await stat(finalPath); throw new Error('a response for this exact paid request already exists');}
  catch (error) {if(error.code!=='ENOENT') throw error;}
  // Exclusive intent is a pre-payment storage check and concurrent-call fence.
  await exclusiveWrite(path.join(directory,`${basename}.intent.json`),{
    schemaVersion:'mira.openmaic.question-phase-reply-intent.v1',...metadata,
  });
  let saved=false;
  return {inputSha256,finalPath,async save(response) {
    if(saved) throw new Error('paid response archive cannot be overwritten');
    if(typeof response.content!=='string' || !response.content || Buffer.byteLength(response.content,'utf8')>2_000_000) throw new TypeError('reply archive content is invalid');
    const receipt={
      providerRequestIdHash:response.providerRequestIdHash ?? null,
      inputTokens:response.inputTokens ?? null,outputTokens:response.outputTokens ?? null,
      billingEvidence:response.billingEvidence,
    };
    if(receipt.providerRequestIdHash!==null && !/^[0-9a-f]{64}$/.test(receipt.providerRequestIdHash)) throw new TypeError('reply archive receipt hash is invalid');
    for(const key of ['inputTokens','outputTokens']) if(receipt[key]!==null && (!Number.isSafeInteger(receipt[key]) || receipt[key]<0)) throw new TypeError('reply archive usage is invalid');
    if(!['reported','unknown'].includes(receipt.billingEvidence)) throw new TypeError('reply archive billing evidence is invalid');
    const payload={schemaVersion:QUESTION_PHASE_REPLY_ARCHIVE_SCHEMA,...metadata,completedAt:now(),receipt,content:response.content,contentSha256:sha(response.content)};
    const tempPath=path.join(directory,`${basename}.reply.tmp`);
    await exclusiveWrite(tempPath,payload);
    await rename(tempPath,finalPath);
    saved=true;
    return {path:finalPath,inputSha256,contentSha256:payload.contentSha256};
  }};
}
