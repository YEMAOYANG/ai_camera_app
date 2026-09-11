#!/usr/bin/env node
/** Pure replay of an already billed candidate-repair reply. No Provider imports. */
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {
  normalizeQuestionPhaseRequest, legacyQuestionPhaseRequest,
  freezeUnchangedQuestionAuthority, assertQuestionCandidateRepairAuthority,
  compileQuestionRepairCandidateCheckpoint, normalizeQuestionPhaseOutputCheckpoint,
  buildHostCompilationEvidence,
} from './question-contract.mjs';
import {assertFormalObjectiveCandidate} from './formal-objective-preflight.mjs';

const stable = x => Array.isArray(x) ? x.map(stable) : x && typeof x === 'object'
  ? Object.fromEntries(Object.keys(x).sort().map(k => [k,stable(x[k])])) : x;
const canonical = x => JSON.stringify(stable(x));
const sha = x => createHash('sha256').update(x).digest('hex');
const exact = (x,keys) => x && !Array.isArray(x) && typeof x === 'object'
  && Object.keys(x).sort().join(',') === [...keys].sort().join(',');

export function replayQuestionPhaseReply(input) {
  if (!exact(input,['request','archive'])) throw Error('replay input fields mismatch');
  const request=normalizeQuestionPhaseRequest(input.request);
  if (request.mode!=='live' || !['candidate_repair','candidate_repair_retry'].includes(request.phase)
    || !/^primary_[2-6]$/.test(request.gradeCode)) throw Error('replay phase authority invalid');
  const archive=input.archive;
  if (!exact(archive,['schemaVersion','requestId','phase','phaseOrdinal','gradeCode','subject','skillId','difficultyCode','inputSha256','providerProfileSha256','createdAt','completedAt','receipt','content','contentSha256'])
    || archive.schemaVersion!=='mira.openmaic.question-phase-reply-archive.v1'
    || !Number.isSafeInteger(archive.createdAt) || !Number.isSafeInteger(archive.completedAt)
    || archive.completedAt<archive.createdAt || typeof archive.content!=='string'
    || Buffer.byteLength(archive.content)>2_000_000) throw Error('replay archive fields invalid');
  const inputSha256=sha(canonical(request));
  const providerProfileSha256=sha(canonical(request.provider));
  const identity={requestId:request.requestId,phase:request.phase,phaseOrdinal:request.phaseOrdinal,
    gradeCode:request.gradeCode,subject:request.subject,skillId:request.skillBoundary.skillId,
    difficultyCode:request.objectivePolicy.difficultyCode,inputSha256,providerProfileSha256};
  if (Object.entries(identity).some(([k,v]) => archive[k]!==v)
    || sha(archive.content)!==archive.contentSha256) throw Error('replay archive identity or content hash mismatch');
  const receipt=archive.receipt;
  if (!exact(receipt,['providerRequestIdHash','inputTokens','outputTokens','billingEvidence'])
    || (receipt.providerRequestIdHash!==null && !/^[0-9a-f]{64}$/.test(receipt.providerRequestIdHash))
    || ['inputTokens','outputTokens'].some(k=>receipt[k]!==null && (!Number.isSafeInteger(receipt[k]) || receipt[k]<0))
    || !['reported','unknown'].includes(receipt.billingEvidence)) throw Error('replay archive receipt invalid');
  const parsed=JSON.parse(archive.content);
  let questions=parsed?.questions;
  if (exact(questions,['q1','q2','q3','q4','q5'])) questions=['q1','q2','q3','q4','q5'].map(k=>questions[k]);
  if (!Array.isArray(questions) || questions.length!==5) throw Error('replay requires five original response slots');
  const raw={...parsed,questions};
  const frozen=freezeUnchangedQuestionAuthority(request.checkpoint.rawCandidate,raw);
  assertQuestionCandidateRepairAuthority(request.checkpoint.rawCandidate,frozen);
  const candidate=assertFormalObjectiveCandidate(request,compileQuestionRepairCandidateCheckpoint(
    frozen,legacyQuestionPhaseRequest(request),request.checkpoint.existingFingerprints,
  ));
  const checkpoint=normalizeQuestionPhaseOutputCheckpoint(request,{
    phaseStatus:'accepted',candidate,
    ...(request.phase==='candidate_repair' ? {hostCompilation:buildHostCompilationEvidence('candidate_repair_output')} : {}),
  });
  return {schemaVersion:'mira.openmaic.archived-candidate-host-replay.v1',
    implementationRepair:'fraction-activity-label-and-percent-precision.v1',inputSha256,providerProfileSha256,
    archiveContentSha256:archive.contentSha256,checkpointSha256:sha(canonical(checkpoint)),checkpoint};
}

if (process.argv[1]===fileURLToPath(import.meta.url)) {
  try {
    const input=readFileSync(0,'utf8');
    if (Buffer.byteLength(input)>3_000_000) throw Error('replay input too large');
    process.stdout.write(JSON.stringify(replayQuestionPhaseReply(JSON.parse(input))));
  } catch (error) {
    process.stderr.write(`Archived reply replay rejected: ${String(error.message).slice(0,240)}\n`);
    process.exitCode=1;
  }
}
