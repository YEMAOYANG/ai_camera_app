#!/usr/bin/env node

import { performance } from 'node:perf_hooks';
import process from 'node:process';
import {prepareQuestionPhaseReplyArchive} from './question-phase-reply-archive.mjs';
import {assertFormalObjectiveCandidate, formalObjectiveQuestionIssues} from './formal-objective-preflight.mjs';
import {
  buildClassroomRequirement,
  classroomSchemas,
  normalizeClassroomGenerationRequest,
  normalizeClassroomReview,
} from './classroom-contract.mjs';
import {
  buildClassroomIntentCompilationPrompts,
  buildClassroomIntentRepairPrompts,
  buildClassroomIntentReviewPrompts,
  buildClassroomIntentSource,
  normalizeClassroomIntent,
} from './classroom-intent-contract.mjs';
import { buildDraft, buildRequirement, ContractError, normalizeRequest, schemas } from './contract.mjs';
import {
  createLiveAICall,
  createSingleDispatchAICall,
  QuestionPhaseDispatchError,
} from './provider.mjs';
import {
  applyQuestionConsistencyRepairCheckpoint,
  applyQuestionPhaseLanguageDirective,
  assertQuestionCandidateRepairAuthority,
  assertQuestionCandidateReconciliationAuthority,
  assertQuestionPracticeLeakRepairAuthority,
  assertQuestionSetOriginality,
  applyHostOwnedPracticeHints,
  buildAnswerBlindLessonTextPrompts,
  buildAnswerBlindLessonTextInput,
  buildChoicePromptRepairPrompts,
  buildIndependentSolution,
  buildIndependentVerificationResponseJsonSchema,
  buildIndependentVerificationPrompts,
  buildQuestionConsistencyRepairPrompts,
  buildQuestionConsistencyRepairRetryPrompts,
  buildQuestionConsistencyPhasePrompts,
  buildQuestionFingerprintCheckpoint,
  buildQuestionConsistencyRepairResult,
  buildQuestionCandidates,
  buildCanonicalLettersSoundsOutlinePlan,
  buildCanonicalLettersSoundsRawCandidateSeed,
  buildCanonicalNumberSenseRawCandidateSeed,
  buildHostCompilationEvidence,
  buildHostReconciliationEvidence,
  buildQuestionCandidateRepairPrompts,
  buildQuestionCandidateRepairRetryPrompts,
  buildQuestionGenerationPrompts,
  buildQuestionPracticeLeakRepairPrompts,
  buildQuestionReconciliationPrompts,
  buildQuestionReconciliationRetryPrompts,
  buildQuestionOutlineRequirement,
  buildQuestionValidationCheckpoint,
  choicePromptViolationIndexes,
  compileAcceptedRawCandidateCheckpoint,
  compileCanonicalLettersSoundsCandidateCheckpoint,
  compileCanonicalNumberSenseCandidateCheckpoint,
  compileAcceptedCandidateReconciliationCheckpoint,
  compileQuestionOutlinePlan,
  compileQuestionRepairCandidateCheckpoint,
  freezeQuestionReconciliation,
  freezeUnchangedQuestionAuthority,
  normalizeChoicePromptRepair,
  normalizeCompiledCandidateCheckpoint,
  normalizeCompiledReconciliationCheckpoint,
  normalizeQuestionGenerationRequest,
  normalizeQuestionPhaseOutputCheckpoint,
  legacyQuestionPhaseRequest,
  normalizeQuestionPhaseRequest,
  normalizeRawCandidateCheckpoint,
  normalizeQuestionConsistencyRepair,
  normalizeQuestionConsistencyRepairRequest,
  normalizeQuestionReconciliation,
  normalizeQuestionVerificationRequest,
  isCanonicalLettersSoundsPhase1Request,
  isCanonicalLettersSoundsPhase2Request,
  isCanonicalNumberSensePhase2Request,
  isCanonicalNumberSensePhase3Request,
  isCanonicalLettersSoundsPhase3Request,
  compileAnswerBlindLessonTextFallback,
  compileAnswerBlindLessonTextProviderOutput,
  hasSealedPrimaryOneLessonFallback,
  questionSchemas,
  teachingFlowPracticeAnswerLeakIndexes,
  providerPhase,
  PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
  PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER,
  PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
  PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER,
  primaryOneCharacterWordExpectedAnswerId,
  primaryOneSentencePattern,
  QUESTION_CONTRACT_VERSION,
  QUESTION_PHASE_INPUT_SCHEMA,
  QUESTION_PHASE_RESULT_SCHEMA,
} from './question-contract.mjs';

async function loadOpenMaic() {
  return import('@openmaic/generation');
}

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value)}\n`);
}

async function readStdin() {
  let body = '';
  for await (const chunk of process.stdin) body += chunk;
  if (!body.trim()) throw new ContractError('stdin JSON is required');
  try {
    return JSON.parse(body);
  } catch {
    throw new ContractError('stdin must contain valid JSON');
  }
}

function createFakeAICall(responses) {
  if (process.env.OPENMAIC_FAKE_MODE !== '1') {
    throw new ContractError('fake mode is disabled', 'openmaic_unavailable');
  }
  let index = 0;
  return async () => {
    if (index >= responses.length) throw new Error('fake response queue exhausted');
    return responses[index++];
  };
}

const QUESTION_PHASE_SAFE_CODES = new Set([
  'question_phase_invalid_input',
  'question_phase_contract_drift',
  'question_phase_unsupported',
  'question_phase_preflight_rejected',
  'question_phase_output_rejected',
  'question_phase_json_rejected',
  'question_phase_verification_json_rejected',
  'question_phase_verification_answers_rejected',
  'question_phase_verification_numeric_rejected',
  'question_phase_verification_review_rejected',
  'question_phase_verification_semantic_rejected',
  'question_phase_verification_checkpoint_rejected',
  'provider_unavailable',
  'provider_request_rejected',
  'provider_no_candidate',
  'provider_invalid_response',
  'provider_timeout',
  'provider_connection_interrupted',
  'provider_response_lost',
  'provider_outcome_unknown',
]);

function emptyQuestionPhaseReceipt() {
  return {
    providerRequestIdHash: null,
    inputTokens: null,
    outputTokens: null,
    billingEvidence: 'unknown',
  };
}

function createSingleDispatchFakeAICall(responses) {
  let invoked = false;
  return async () => {
    if (invoked) {
      throw new QuestionPhaseDispatchError(
        'failed_safe',
        'question_phase_preflight_rejected',
      );
    }
    invoked = true;
    if (process.env.OPENMAIC_FAKE_MODE !== '1'
      || !Array.isArray(responses)
      || responses.length !== 1
      || typeof responses[0] !== 'string') {
      throw new QuestionPhaseDispatchError(
        'failed_safe',
        'question_phase_preflight_rejected',
      );
    }
    return { content: responses[0], ...emptyQuestionPhaseReceipt() };
  };
}

function questionPhaseSafeIdentity(payload) {
  const requestId = typeof payload?.requestId === 'string'
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/.test(payload.requestId)
    ? payload.requestId
    : null;
  let phase = null;
  let phaseOrdinal = null;
  try {
    if (typeof payload?.phase === 'string' && Number.isSafeInteger(payload?.phaseOrdinal)) {
      const identity = providerPhase(payload.phase, payload.phaseOrdinal);
      phase = identity.phase;
      phaseOrdinal = identity.phaseOrdinal;
    }
  } catch {
    phase = null;
    phaseOrdinal = null;
  }
  return { requestId, phase, phaseOrdinal };
}

function questionPhaseResult({
  payload,
  request,
  outcome,
  checkpoint = null,
  receipt = emptyQuestionPhaseReceipt(),
  safeErrorCode = null,
  startedAt,
}) {
  const identity = request
    ? {
      requestId: request.requestId,
      phase: request.phase,
      phaseOrdinal: request.phaseOrdinal,
    }
    : questionPhaseSafeIdentity(payload);
  return {
    schemaVersion: QUESTION_PHASE_RESULT_SCHEMA,
    questionContractVersion: QUESTION_CONTRACT_VERSION,
    ...identity,
    outcome,
    checkpoint: outcome === 'succeeded' ? checkpoint : null,
    providerRequestIdHash: receipt.providerRequestIdHash ?? null,
    inputTokens: receipt.inputTokens ?? null,
    outputTokens: receipt.outputTokens ?? null,
    billingEvidence: receipt.billingEvidence ?? 'unknown',
    safeErrorCode: outcome === 'succeeded' ? null : safeErrorCode,
    elapsedMs: Math.max(0, performance.now() - startedAt),
  };
}

async function readRawStdin() {
  let body = '';
  for await (const chunk of process.stdin) body += chunk;
  return body;
}

function parseQuestionPhaseJson(body) {
  if (typeof body !== 'string' || !body.trim()) return { payload: null, valid: false };
  try {
    const payload = JSON.parse(body);
    return {
      payload,
      valid: Boolean(payload && typeof payload === 'object' && !Array.isArray(payload)),
    };
  } catch {
    return { payload: null, valid: false };
  }
}


function parseQuestionPhaseContent(content) {
  try {
    const trimmed = String(content).trim();
    const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
    const value = JSON.parse((fenced ? fenced[1] : trimmed).trim());
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new TypeError('phase content must be an object');
    }
    return value;
  } catch {
    throw new ContractError('question phase JSON rejected', 'question_phase_json_rejected');
  }
}

function independentVerificationSemanticSafeCode(error) {
  const message = String(error?.message || '');
  if (/teachingReview/i.test(message)) {
    return 'question_phase_verification_review_rejected';
  }
  if (/derivedExpression|verificationExpression|arithmetic|numeric/i.test(message)) {
    return 'question_phase_verification_numeric_rejected';
  }
  if (/independent answer|independent solution|public choice|scalar string|choice ids/i.test(
    message,
  )) {
    return 'question_phase_verification_answers_rejected';
  }
  return 'question_phase_verification_semantic_rejected';
}

function normalizeProviderOutline(value, request) {
  const source = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const outlines = Array.isArray(source.outlines) ? source.outlines.slice(0, 4) : [];
  return compileQuestionOutlinePlan(request, {
    courseTitle: source.courseTitle,
    languageDirective: source.languageDirective,
    outlines: outlines.map((outline, index) => ({
      order: index + 1,
      title: outline?.title,
      description: outline?.description,
      keyPoints: Array.isArray(outline?.keyPoints) ? outline.keyPoints.slice(0, 12) : [],
    })),
  });
}

function repairRejectionCode(kind, error) {
  const originality = error instanceof ContractError
    && (error.code === 'duplicate_candidate' || /original/i.test(error.code));
  if (kind === 'candidate') {
    return originality
      ? 'candidate_repair_originality_rejected'
      : 'candidate_repair_schema_rejected';
  }
  if (kind === 'reconciliation') {
    return originality
      ? 'reconciliation_originality_rejected'
      : 'reconciliation_schema_rejected';
  }
  return 'consistency_repair_schema_rejected';
}

function compileHostSealedRawCandidateCheckpoint(request, legacyRequest) {
  if (!hasSealedPrimaryOneLessonFallback(request)) {
    throw new ContractError(
      'sealed raw candidate compilation is unavailable',
      'invalid_generation',
    );
  }
  const lessonText = compileAnswerBlindLessonTextFallback(
    buildAnswerBlindLessonTextInput(request, request.checkpoint.rawCandidate),
  );
  return compileQuestionRepairCandidateCheckpoint(
    {
      ...request.checkpoint.rawCandidate,
      ...lessonText,
    },
    legacyRequest,
    request.checkpoint.existingFingerprints,
  );
}

function publicQuestionShells(candidateCourse) {
  return candidateCourse.content.questions.map((question) => ({
    id: question.id,
    type: question.type,
    prompt: question.prompt,
    ...(Array.isArray(question.choices)
      ? {
        choices: question.choices.map((choice) => ({ id: choice.id, label: choice.label })),
      }
      : {}),
  }));
}

function publicTeachingFlow(candidateCourse) {
  const flow = candidateCourse.content.teachingFlow;
  const demo = candidateCourse.content.questions[0];
  return {
    ...flow,
    workedExample: {
      questionId: demo.id,
      explanation: demo.explanation,
    },
  };
}

function independentVerificationRequest(request, candidateCourse) {
  return {
    requestId: request.requestId,
    gradeCode: request.gradeCode,
    subject: request.subject,
    skillBoundary: {
      ...request.skillBoundary,
      language: request.targetLanguageCode,
    },
    publicQuestions: publicQuestionShells(candidateCourse),
    publicTeachingFlow: publicTeachingFlow(candidateCourse),
    provider: request.provider,
  };
}

function primaryOneHostSolver(request) {
  if (request.mode !== 'live'
    || request.gradeCode !== 'primary_1') return null;
  if (request.subject === 'math') {
    return {
      addition_subtraction_20: PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
      number_sense_20: PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
    }[request.skillBoundary?.skillId] ?? null;
  }
  if (request.subject === 'chinese'
    && ['simple_sentences', 'characters_words'].includes(
      request.skillBoundary?.skillId,
    )) {
    return request.skillBoundary.skillId === 'characters_words'
      ? PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER
      : PRIMARY_ONE_SIMPLE_SENTENCE_HOST_SOLVER;
  }
  return null;
}

function visibleNumericTokens(value) {
  return (String(value).match(/\d+(?:\.\d+)?/g) || []).map((token) => {
    const numeric = Number(token);
    if (!Number.isFinite(numeric)) {
      throw new ContractError('public arithmetic operand is invalid', 'invalid_verification');
    }
    return { token: String(numeric), value: numeric };
  });
}

function choiceIdsForNumericValue(question, expected) {
  if (!Array.isArray(question.choices)) return [];
  return question.choices
    .filter((choice) => {
      const tokens = visibleNumericTokens(choice.label);
      return tokens.length === 1 && tokens[0].value === expected;
    })
    .map((choice) => choice.id);
}

function solvePrimaryOneAddSubPublicQuestion(question) {
  if (!question || !['numeric', 'single_choice'].includes(question.type)) {
    throw new ContractError(
      'host add-sub solver requires numeric or single-choice questions',
      'invalid_verification',
    );
  }
  const prompt = String(question.prompt);
  const visibleEquation = prompt.match(/(\d+(?:\.\d+)?)\s*([+\-])\s*(\d+(?:\.\d+)?)/);
  let left;
  let right;
  let operator;
  if (visibleEquation) {
    left = Number(visibleEquation[1]);
    operator = visibleEquation[2];
    right = Number(visibleEquation[3]);
  } else {
    const operands = visibleNumericTokens(prompt);
    if (operands.length !== 2) {
      throw new ContractError(
        'host add-sub solver requires exactly two public operands',
        'invalid_verification',
      );
    }
    [left, right] = operands.map((item) => item.value);
    const explicitUnfinishedRemainder = (
      /(?:已经|已)[^！？?]{0,60}(?:还有|尚有)[^！？?]{0,24}(?:没有|未)/u
    ).test(prompt);
    const subtractCue = /送给|拿走|飞走|用掉|吃掉|碰掉|减去|取走|分给|摘走|离开|少了|还剩|剩下|还留|余下|相差/.test(prompt)
      || explicitUnfinishedRemainder;
    const addCue = /一共|共有|总共|合起来|放进去|加入|增加|加上|又|来了|买了|得到|凑在一起/.test(prompt);
    if (subtractCue) {
      operator = '-';
    } else if (addCue) {
      operator = '+';
    } else if (question.type === 'single_choice') {
      const candidates = [
        { operator: '+', value: left + right },
        { operator: '-', value: left - right },
      ].filter((candidate) => choiceIdsForNumericValue(question, candidate.value).length === 1);
      if (candidates.length === 1) operator = candidates[0].operator;
    }
  }
  if (!['+', '-'].includes(operator)) {
    throw new ContractError(
      'host add-sub solver could not determine the public operation',
      'invalid_verification',
    );
  }
  const expected = operator === '+' ? left + right : left - right;
  if (!Number.isSafeInteger(expected) || expected < 0 || expected > 20) {
    throw new ContractError(
      'host add-sub result is outside the fixed whole-number boundary',
      'invalid_verification',
    );
  }
  if (question.type === 'numeric') {
    return {
      answer: String(expected),
      derivedExpression: `${left}${operator}${right}`,
      numericValue: expected,
    };
  }
  const matchingChoiceIds = choiceIdsForNumericValue(question, expected);
  if (matchingChoiceIds.length !== 1) {
    throw new ContractError(
      'host add-sub solver requires one public choice matching the result',
      'invalid_verification',
    );
  }
  return { answer: matchingChoiceIds[0], numericValue: expected };
}

function normalizedPublicChoiceLabel(value) {
  return String(value)
    .normalize('NFKC')
    .replace(/[\s，,。.!！？?：:；;]/g, '');
}

function solvePrimaryOneNumberSensePublicQuestion(question) {
  if (!question || question.type !== 'single_choice' || !Array.isArray(question.choices)) {
    throw new ContractError(
      'host number-sense solver requires single-choice questions',
      'invalid_verification',
    );
  }
  const prompt = String(question.prompt);
  const nextMatch = prompt.match(/数字\s*(\d+)\s*的后一个数/)
    || prompt.match(/从\s*(\d+)\s*往后数[^。?!]*?(?:紧接着|后一个)/);
  if (nextMatch) {
    const expected = Number(nextMatch[1]) + 1;
    const matches = choiceIdsForNumericValue(question, expected);
    if (matches.length === 1 && expected <= 20) {
      return { answer: matches[0], numericValue: expected };
    }
  }
  const compositionMatch = prompt.match(/(\d+)\s*(?:是)?由几个十和几个一组成/);
  if (compositionMatch) {
    const value = Number(compositionMatch[1]);
    const expectedLabel = `${Math.floor(value / 10)}个十和${value % 10}个一`;
    const matches = question.choices.filter(
      (choice) => normalizedPublicChoiceLabel(choice.label)
        === normalizedPublicChoiceLabel(expectedLabel),
    );
    if (matches.length === 1 && value >= 0 && value <= 20) {
      return { answer: matches[0].id, numericValue: value };
    }
  }
  if (/哪个数更大|比较/.test(prompt)) {
    const operands = visibleNumericTokens(prompt);
    if (operands.length === 2) {
      const expected = Math.max(operands[0].value, operands[1].value);
      const matches = choiceIdsForNumericValue(question, expected);
      if (matches.length === 1 && Number.isSafeInteger(expected) && expected <= 20) {
        return { answer: matches[0], numericValue: expected };
      }
    }
  }
  throw new ContractError(
    'host number-sense solver could not prove the public answer',
    'invalid_verification',
  );
}

function solvePrimaryOneSimpleSentencePublicQuestion(question) {
  if (!question || question.type !== 'single_choice' || !Array.isArray(question.choices)) {
    throw new ContractError(
      'host simple-sentence solver requires single-choice questions',
      'invalid_verification',
    );
  }
  const prompt = String(question.prompt ?? '');
  const expectedTerminal = prompt.includes('问句') || prompt.includes('询问') ? '?' : '。';
  const matches = question.choices.filter((choice) => {
    const sentence = String(choice?.label ?? '').normalize('NFKC').trim();
    if (!sentence.endsWith(expectedTerminal)) return false;
    return primaryOneSentencePattern(sentence.slice(0, -1).trim()) !== null;
  });
  if (matches.length !== 1) {
    throw new ContractError(
      'host simple-sentence solver requires exactly one sealed complete sentence',
      'invalid_verification',
    );
  }
  return { answer: matches[0].id };
}

function solvePrimaryOneCharacterWordPublicQuestion(question) {
  return { answer: primaryOneCharacterWordExpectedAnswerId(question) };
}

function compilePrimaryOneHostVerification(verificationRequest, solverIdentity) {
  const solver = solverIdentity === PRIMARY_ONE_ADD_SUB_HOST_SOLVER
    ? solvePrimaryOneAddSubPublicQuestion
    : solverIdentity === PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER
      ? solvePrimaryOneNumberSensePublicQuestion
      : solverIdentity === PRIMARY_ONE_CHARACTER_WORD_HOST_SOLVER
        ? solvePrimaryOneCharacterWordPublicQuestion
        : solvePrimaryOneSimpleSentencePublicQuestion;
  const solved = verificationRequest.publicQuestions.map(solver);
  if ([PRIMARY_ONE_ADD_SUB_HOST_SOLVER, PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER]
    .includes(solverIdentity)) {
    const workedExample = verificationRequest.publicTeachingFlow?.workedExample;
    if (workedExample?.questionId !== verificationRequest.publicQuestions[0]?.id) {
      throw new ContractError(
        'host math worked example is not bound to q1',
        'invalid_verification',
      );
    }
    const explanationNumbers = new Set(
      visibleNumericTokens(workedExample.explanation).map((item) => item.token),
    );
    if (!explanationNumbers.has(String(solved[0].numericValue))) {
      throw new ContractError(
        'host math worked example does not show the independently solved result',
        'invalid_verification',
      );
    }
  }
  const answers = Object.fromEntries(solved.map((answer, index) => {
    const { numericValue: _numericValue, ...publicAnswer } = answer;
    return [`q${index + 1}`, publicAnswer];
  }));
  return buildIndependentSolution({
    request: verificationRequest,
    generated: {
      answers,
      teachingReview: { issues: [] },
    },
    elapsedMs: 0,
    solver: solverIdentity,
  });
}

function consistencyRepairRequest(request) {
  const candidateCourse = request.checkpoint.candidateCourse;
  const publicQuestions = publicQuestionShells(candidateCourse);
  return {
    requestId: request.requestId,
    gradeCode: request.gradeCode,
    subject: request.subject,
    skillBoundary: {
      ...request.skillBoundary,
      language: request.targetLanguageCode,
    },
    publicLessonText: {
      title: candidateCourse.title,
      intro: candidateCourse.content.intro,
    },
    publicQuestions,
    publicTeachingFlow: publicTeachingFlow(candidateCourse),
    publicGuidance: candidateCourse.content.questions.map((question) => ({
      questionId: question.id,
      hint: question.hint,
      explanation: question.explanation,
    })),
    reviewIssues: request.checkpoint.reviewIssues,
    provider: request.provider,
  };
}

function compileHostSealedConsistencyRepair(request) {
  if (!hasSealedPrimaryOneLessonFallback(request)) {
    throw new ContractError(
      'sealed consistency repair is unavailable',
      'invalid_generation',
    );
  }
  const candidateCourse = request.checkpoint.candidateCourse;
  const lessonText = compileAnswerBlindLessonTextFallback(
    buildAnswerBlindLessonTextInput(request, candidateCourse.content),
  );
  const projection = consistencyRepairRequest(request);
  return normalizeQuestionConsistencyRepair({
    title: lessonText.title,
    intro: lessonText.intro,
    teach: lessonText.teachingFlow.teach,
    recap: lessonText.teachingFlow.recap,
    questionGuidance: projection.publicGuidance,
  }, projection);
}

function projectExactCandidateQuestionSlots(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new ContractError(
      'question candidate output must be one object',
      'question_phase_output_rejected',
    );
  }
  let questions;
  if (Array.isArray(raw.questions)) {
    questions = raw.questions;
  } else if (raw.questions && typeof raw.questions === 'object') {
    const expected = ['q1', 'q2', 'q3', 'q4', 'q5'];
    const keys = Object.keys(raw.questions);
    if (keys.length === expected.length && expected.every((key) => keys.includes(key))) {
      questions = expected.map((key) => raw.questions[key]);
    }
  }
  if (!Array.isArray(questions) || questions.length !== 5) {
    throw new ContractError(
      'question candidate output must contain exactly five slots',
      'question_phase_output_rejected',
    );
  }
  return { ...raw, questions };
}

async function executeQuestionPhase(request) {
  const legacyRequest = legacyQuestionPhaseRequest(request);
  let dispatchCall = null;
  let replyArchive = null;
  let receipt = emptyQuestionPhaseReceipt();
  let providerCompleted = false;
  const invoke = async (
    prompts,
    { languageWrapped = false, responseJsonSchema = null } = {},
  ) => {
    if (!dispatchCall) {
      try { replyArchive = await prepareQuestionPhaseReplyArchive(request); }
      catch { throw new ContractError('paid response archive is unavailable or this request already has an intent', 'question_phase_preflight_rejected'); }
      dispatchCall = request.mode === 'fake'
        ? createSingleDispatchFakeAICall(request.fakeResponses)
        : createSingleDispatchAICall(request.provider, {
          questionPhase: request.phase,
          requestId: request.requestId,
          responseJsonSchema,
        });
    }
    const actualPrompts = languageWrapped
      ? prompts
      : applyQuestionPhaseLanguageDirective(request, prompts);
    const response = await dispatchCall(actualPrompts.system, actualPrompts.user);
    providerCompleted = true;
    receipt = {
      providerRequestIdHash: response.providerRequestIdHash,
      inputTokens: response.inputTokens,
      outputTokens: response.outputTokens,
      billingEvidence: response.billingEvidence,
    };
    // Persist the exact returned content before JSON/semantic/checkpoint parsing.
    // The archive is evidence only, never a synthesized successful review.
    if (replyArchive) {
      try { await replyArchive.save(response); }
      catch { throw new ContractError('paid response archive write failed', 'question_phase_output_rejected'); }
    }
    return parseQuestionPhaseContent(response.content);
  };
  const invokeIndependentVerification = async (verificationRequest) => {
    const prompts = buildIndependentVerificationPrompts(verificationRequest);
    const responseJsonSchema =
      buildIndependentVerificationResponseJsonSchema(verificationRequest);
    let independentRaw;
    try {
      independentRaw = await invoke(prompts, { responseJsonSchema });
    } catch (error) {
      if (error instanceof ContractError
        && error.code === 'question_phase_json_rejected') {
        throw new ContractError(
          'independent verification JSON rejected',
          'question_phase_verification_json_rejected',
        );
      }
      throw error;
    }
    try {
      return buildIndependentSolution({
        request: verificationRequest,
        generated: independentRaw,
        elapsedMs: 0,
      });
    } catch (error) {
      if (error instanceof ContractError) {
        throw new ContractError(
          'independent verification semantic output rejected',
          independentVerificationSemanticSafeCode(error),
        );
      }
      throw error;
    }
  };

  let checkpoint;
  try {
    if (request.phase === 'outline') {
      if (isCanonicalLettersSoundsPhase1Request(request)) {
        checkpoint = {
          phaseStatus: 'accepted',
          outlinePlan: buildCanonicalLettersSoundsOutlinePlan(request),
        };
      } else if (hasSealedPrimaryOneLessonFallback(request)) {
        checkpoint = {
          phaseStatus: 'accepted',
          outlinePlan: compileQuestionOutlinePlan(request, {}),
        };
      } else {
        let openmaic;
        try {
          openmaic = await loadOpenMaic();
        } catch {
          throw new ContractError('question phase Provider unavailable', 'provider_unavailable');
        }
        if (typeof openmaic.buildOutlinePrompt !== 'function') {
          throw new ContractError('question phase Provider unavailable', 'provider_unavailable');
        }
        const requirements = {
          requirement: buildQuestionOutlineRequirement(legacyRequest),
          userBio: `Grade ${request.gradeCode}; subject ${request.subject}; fixed skill ${request.skillBoundary.skillId}`,
          interactiveMode: false,
          taskEngineMode: false,
        };
        const prompts = openmaic.buildOutlinePrompt(requirements, {
          imageGenerationEnabled: false,
          videoGenerationEnabled: false,
          visionEnabled: false,
        });
        checkpoint = {
          phaseStatus: 'accepted',
          outlinePlan: normalizeProviderOutline(await invoke(prompts), request),
        };
      }
    } else if (request.phase === 'raw_candidate') {
      let rawCandidate;
      if (isCanonicalNumberSensePhase2Request(request)) {
        rawCandidate = buildCanonicalNumberSenseRawCandidateSeed(request);
      } else if (isCanonicalLettersSoundsPhase2Request(request)) {
        rawCandidate = buildCanonicalLettersSoundsRawCandidateSeed(request);
      } else {
        const prompts = buildQuestionGenerationPrompts(
          legacyRequest,
          request.checkpoint.outlinePlan,
        );
        rawCandidate = normalizeRawCandidateCheckpoint(
          projectExactCandidateQuestionSlots(await invoke(prompts)),
        );
      }
      checkpoint = {
        phaseStatus: 'accepted',
        rawCandidate,
      };
    } else if (request.phase === 'candidate_repair'
      || request.phase === 'candidate_repair_retry') {
      const retry = request.phase === 'candidate_repair_retry';
      // Raw shape acceptance is not objective validity. An invalid raw set
      // remains eligible for this phase's one paid repair, with exact Host
      // reasons; it must never be compiled straight into paid lesson work.
      const objectiveIssues = formalObjectiveQuestionIssues(request, request.checkpoint.rawCandidate);
      if (!retry && (isCanonicalNumberSensePhase3Request(request)
        || isCanonicalLettersSoundsPhase3Request(request))) {
        checkpoint = {
          phaseStatus: 'accepted',
          candidate: isCanonicalNumberSensePhase3Request(request)
            ? compileCanonicalNumberSenseCandidateCheckpoint(request)
            : compileCanonicalLettersSoundsCandidateCheckpoint(request),
          hostCompilation: buildHostCompilationEvidence('canonical_skill_builder', request),
        };
      }
      if (!checkpoint && !retry && objectiveIssues.length === 0) {
        try {
          checkpoint = {
            phaseStatus: 'accepted',
            candidate: assertFormalObjectiveCandidate(request, compileAcceptedRawCandidateCheckpoint(request)),
            hostCompilation: buildHostCompilationEvidence('accepted_raw_candidate'),
          };
        } catch {
          checkpoint = null;
        }
      }
      if (!checkpoint && objectiveIssues.length === 0) {
        try {
          checkpoint = {
            phaseStatus: 'accepted',
            candidate: assertFormalObjectiveCandidate(request, compileHostSealedRawCandidateCheckpoint(request, legacyRequest)),
            ...(retry
              ? {}
              : { hostCompilation: buildHostCompilationEvidence('accepted_raw_candidate') }),
          };
        } catch {
          checkpoint = null;
        }
      }
      if (!checkpoint) {
        const prompts = retry
          ? buildQuestionCandidateRepairRetryPrompts(
            legacyRequest,
            request.checkpoint.rawCandidate,
          )
          : buildQuestionCandidateRepairPrompts(
            legacyRequest,
            request.checkpoint.rawCandidate,
          );
        if (objectiveIssues.length) {
          prompts.system += ' The Host objective preflight below is authoritative validation data. Regenerate each invalid complete question shell and its answer together inside the frozen objectivePolicy grammar. A different subskill, simpler question, or changed answer alone is not a repair. Preserve already valid questions when possible.';
          prompts.user += `\nHost objective preflight: ${JSON.stringify(objectiveIssues)}`;
        }
        try {
          const raw = projectExactCandidateQuestionSlots(await invoke(prompts));
          const frozen = freezeUnchangedQuestionAuthority(request.checkpoint.rawCandidate, raw);
          assertQuestionCandidateRepairAuthority(request.checkpoint.rawCandidate, frozen);
          const candidate = assertFormalObjectiveCandidate(request, compileQuestionRepairCandidateCheckpoint(
            frozen,
            legacyRequest,
            request.checkpoint.existingFingerprints,
          ));
          checkpoint = {
            phaseStatus: 'accepted',
            candidate,
            ...(retry
              ? {}
              : { hostCompilation: buildHostCompilationEvidence('candidate_repair_output') }),
          };
        } catch (error) {
          if (error instanceof QuestionPhaseDispatchError) throw error;
          const rejectionCode = repairRejectionCode('candidate', error);
          if (retry) {
            throw new ContractError(
              'question phase output rejected',
              'question_phase_output_rejected',
            );
          }
          try {
            if (objectiveIssues.length) throw error;
            checkpoint = {
              phaseStatus: 'accepted',
              candidate: assertFormalObjectiveCandidate(request, compileAcceptedRawCandidateCheckpoint(request)),
              hostCompilation: buildHostCompilationEvidence('accepted_raw_candidate'),
            };
          } catch {
            checkpoint = { phaseStatus: 'rejected', rejectionCode };
          }
        }
      }
    } else if (request.phase === 'lesson_text') {
      const answerBlindInput = buildAnswerBlindLessonTextInput(
        legacyRequest,
        request.checkpoint.candidate,
      );
      let lessonText;
      if (hasSealedPrimaryOneLessonFallback(request)) {
        // Each formal foundation lesson has a Host-owned compiler whose
        // public copy is derived only from the fixed boundary and generated q1.
        // Keep the phase deterministic instead of creating a non-idempotent
        // Provider dispatch for text that the Host can prove locally.
        lessonText = compileAnswerBlindLessonTextFallback(answerBlindInput);
      } else {
        const prompts = buildAnswerBlindLessonTextPrompts(
          legacyRequest,
          request.checkpoint.candidate,
        );
        lessonText = compileAnswerBlindLessonTextProviderOutput(
          await invoke(prompts),
          request,
        );
      }
      checkpoint = {
        phaseStatus: 'accepted',
        lessonText,
      };
    } else if (request.phase === 'reconciliation'
      || request.phase === 'reconciliation_retry') {
      const retry = request.phase === 'reconciliation_retry';
      const prompts = retry
        ? buildQuestionReconciliationRetryPrompts(
          legacyRequest,
          request.checkpoint.candidate,
          request.checkpoint.lessonText,
        )
        : buildQuestionReconciliationPrompts(
          legacyRequest,
          request.checkpoint.candidate,
          request.checkpoint.lessonText,
        );
      try {
        const raw = await invoke(prompts);
        const normalized = normalizeQuestionReconciliation(raw, legacyRequest);
        const frozen = freezeQuestionReconciliation(
          request.checkpoint.candidate,
          normalized,
        );
        assertQuestionCandidateReconciliationAuthority(
          request.checkpoint.candidate,
          frozen,
        );
        const reconciliation = normalizeCompiledReconciliationCheckpoint(
          applyHostOwnedPracticeHints(legacyRequest, frozen),
          legacyRequest,
          request.checkpoint.existingFingerprints,
        );
        checkpoint = {
          phaseStatus: 'accepted',
          reconciliation,
          hostReconciliation: buildHostReconciliationEvidence('reconciliation_output'),
        };
      } catch (error) {
        if (error instanceof QuestionPhaseDispatchError) throw error;
        const rejectionCode = repairRejectionCode('reconciliation', error);
        if (retry) {
          throw new ContractError(
            'question phase output rejected',
            'question_phase_output_rejected',
          );
        }
        try {
          checkpoint = {
            phaseStatus: 'accepted',
            reconciliation: compileAcceptedCandidateReconciliationCheckpoint(request),
            hostReconciliation: buildHostReconciliationEvidence('accepted_candidate'),
          };
        } catch {
          checkpoint = { phaseStatus: 'rejected', rejectionCode };
        }
      }
    } else if (request.phase === 'practice_leak_repair_1'
      || request.phase === 'practice_leak_repair_2') {
      const prompts = buildQuestionPracticeLeakRepairPrompts(
        legacyRequest,
        request.checkpoint.reconciliation,
        request.checkpoint.lessonText,
        request.checkpoint.leakingQuestionIndexes,
      );
      const raw = await invoke(prompts);
      const repaired = freezeQuestionReconciliation(
        request.checkpoint.reconciliation,
        normalizeQuestionReconciliation(raw, legacyRequest),
      );
      assertQuestionPracticeLeakRepairAuthority(
        request.checkpoint.reconciliation,
        repaired,
        request.checkpoint.leakingQuestionIndexes,
      );
      const reconciliation = applyHostOwnedPracticeHints(legacyRequest, repaired);
      assertQuestionSetOriginality(legacyRequest, reconciliation.questions);
      checkpoint = { phaseStatus: 'accepted', reconciliation };
    } else if (request.phase === 'choice_prompt_repair') {
      const prompts = buildChoicePromptRepairPrompts(
        legacyRequest,
        request.checkpoint.reconciliation.questions,
        request.checkpoint.violatingQuestionIndexes,
      );
      const reconciliation = normalizeChoicePromptRepair(
        await invoke(prompts),
        request.checkpoint.reconciliation,
        request.checkpoint.violatingQuestionIndexes,
      );
      assertQuestionSetOriginality(legacyRequest, reconciliation.questions);
      checkpoint = { phaseStatus: 'accepted', reconciliation };
    } else if (request.phase === 'independent_verification') {
      const generated = {
        ...request.checkpoint.candidate,
        ...request.checkpoint.lessonText,
        ...request.checkpoint.reconciliation,
        // lessonText is Host-sealed for primary-one courses and intentionally
        // uses the stable skill title. It must not erase the concrete title
        // produced for this generated candidate/variant.
        title: request.checkpoint.candidate.title,
      };
      const candidateOutput = buildQuestionCandidates({
        request: legacyRequest,
        generationPlan: request.checkpoint.outlinePlan,
        generated,
        elapsedMs: 0,
      });
      const verificationRequest = independentVerificationRequest(
        request,
        candidateOutput.candidateCourse,
      );
      const hostSolver = primaryOneHostSolver(request);
      const independentOutput = hostSolver
        ? compilePrimaryOneHostVerification(verificationRequest, hostSolver)
        : await invokeIndependentVerification(verificationRequest);
      checkpoint = {
        phaseStatus: 'accepted',
        candidateCourse: candidateOutput.candidateCourse,
        questionFingerprints: candidateOutput.questionFingerprints,
        validation: candidateOutput.validation,
        independentSolution: independentOutput.solution,
      };
    } else if (request.phase === 'consistency_repair'
      || request.phase === 'consistency_repair_retry') {
      const retry = request.phase === 'consistency_repair_retry';
      const projection = consistencyRepairRequest(request);
      if (hasSealedPrimaryOneLessonFallback(request)) {
        checkpoint = {
          phaseStatus: 'accepted',
          repair: compileHostSealedConsistencyRepair(request),
        };
      } else {
        const prompts = retry
          ? applyQuestionPhaseLanguageDirective(
            request,
            buildQuestionConsistencyRepairRetryPrompts(projection),
          )
          : buildQuestionConsistencyPhasePrompts(request);
        try {
          const repair = normalizeQuestionConsistencyRepair(
            await invoke(prompts, { languageWrapped: true }),
            projection,
          );
          checkpoint = { phaseStatus: 'accepted', repair };
        } catch (error) {
          if (error instanceof QuestionPhaseDispatchError) throw error;
          if (retry) {
            throw new ContractError(
              'question phase output rejected',
              'question_phase_output_rejected',
            );
          }
          checkpoint = {
            phaseStatus: 'rejected',
            rejectionCode: repairRejectionCode('consistency', error),
          };
        }
      }
    } else if (request.phase === 'verification_after_repair') {
      const repairedCandidateCourse = applyQuestionConsistencyRepairCheckpoint(
        request.checkpoint.candidateCourse,
        request.checkpoint.repair,
      );
      const phaseRequest = {
        ...legacyRequest,
        existingFingerprints: request.checkpoint.existingFingerprints,
      };
      const recomputedFingerprints = buildQuestionFingerprintCheckpoint(
        phaseRequest,
        repairedCandidateCourse.content.questions,
      );
      if (JSON.stringify(recomputedFingerprints)
        !== JSON.stringify(request.checkpoint.questionFingerprints)) {
        throw new ContractError(
          'consistency repair changed immutable question fingerprints',
          'question_phase_output_rejected',
        );
      }
      const canonicalValidation = buildQuestionValidationCheckpoint(
        phaseRequest,
        repairedCandidateCourse.content.questions,
      );
      if (JSON.stringify(canonicalValidation) !== JSON.stringify(request.checkpoint.validation)) {
        throw new ContractError(
          'phase validation drifted',
          'question_phase_contract_drift',
        );
      }
      checkpoint = {
        phaseStatus: 'accepted',
        repairedCandidateCourse,
        questionFingerprints: request.checkpoint.questionFingerprints,
        validation: request.checkpoint.validation,
        // The consistency repair cannot change any public question. Reuse the
        // phase-11 answer receipt that is already bound to those exact public
        // questions; the Host gate independently validates the repaired course
        // and the answer agreement before publication.
        independentSolution: request.checkpoint.independentSolution,
      };
    } else {
      throw new ContractError('question phase unsupported', 'question_phase_unsupported');
    }
    let normalizedCheckpoint;
    try {
      normalizedCheckpoint = normalizeQuestionPhaseOutputCheckpoint(request, checkpoint);
    } catch (error) {
      if ((request.phase === 'independent_verification'
          || request.phase === 'verification_after_repair')
        && error instanceof ContractError) {
        throw new ContractError(
          'independent verification checkpoint rejected',
          'question_phase_verification_checkpoint_rejected',
        );
      }
      throw error;
    }
    return { checkpoint: normalizedCheckpoint, receipt };
  } catch (error) {
    error.questionPhaseReceipt = receipt;
    error.questionPhaseProviderCompleted = providerCompleted;
    throw error;
  }
}

function normalizedQuestionPhaseFailure(error) {
  if (error instanceof QuestionPhaseDispatchError) {
    return {
      outcome: error.outcome,
      safeErrorCode: error.safeErrorCode,
      receipt: {
        providerRequestIdHash: error.providerRequestIdHash,
        inputTokens: error.inputTokens,
        outputTokens: error.outputTokens,
        billingEvidence: error.billingEvidence,
      },
    };
  }
  const receipt = error?.questionPhaseReceipt ?? emptyQuestionPhaseReceipt();
  const code = error instanceof ContractError && QUESTION_PHASE_SAFE_CODES.has(error.code)
    ? error.code
    : error?.questionPhaseProviderCompleted
      ? 'question_phase_output_rejected'
      : 'question_phase_preflight_rejected';
  return { outcome: 'failed_safe', safeErrorCode: code, receipt };
}

async function runQuestionPhaseV2() {
  const startedAt = performance.now();
  const body = await readRawStdin();
  const parsed = parseQuestionPhaseJson(body);
  let request;
  if (process.argv.slice(2).length !== 1
    || process.argv[2] !== '--question-phase-v2') {
    const result = questionPhaseResult({
      payload: parsed.payload,
      outcome: 'failed_safe',
      safeErrorCode: 'question_phase_preflight_rejected',
      startedAt,
    });
    writeJson(result);
    process.exitCode = 1;
    return;
  }
  if (!parsed.valid) {
    const result = questionPhaseResult({
      payload: parsed.payload,
      outcome: 'failed_safe',
      safeErrorCode: 'question_phase_invalid_input',
      startedAt,
    });
    writeJson(result);
    process.exitCode = 1;
    return;
  }
  try {
    request = normalizeQuestionPhaseRequest(parsed.payload);
  } catch (error) {
    const safeErrorCode = error instanceof ContractError
      && QUESTION_PHASE_SAFE_CODES.has(error.code)
      ? error.code
      : 'question_phase_invalid_input';
    const result = questionPhaseResult({
      payload: parsed.payload,
      outcome: 'failed_safe',
      safeErrorCode,
      startedAt,
    });
    writeJson(result);
    process.exitCode = 1;
    return;
  }
  try {
    const completed = await executeQuestionPhase(request);
    writeJson(questionPhaseResult({
      payload: parsed.payload,
      request,
      outcome: 'succeeded',
      checkpoint: completed.checkpoint,
      receipt: completed.receipt,
      startedAt,
    }));
  } catch (error) {
    const failure = normalizedQuestionPhaseFailure(error);
    writeJson(questionPhaseResult({
      payload: parsed.payload,
      request,
      ...failure,
      startedAt,
    }));
    process.exitCode = 1;
  }
}

async function availability() {
  try {
    const module = await loadOpenMaic();
    const requiredExports = [
      'generateSceneOutlinesFromRequirements',
      'generateSceneContent',
      'generateSceneActions',
      'buildCompleteScene',
      'parseJsonResponse',
    ];
    if (requiredExports.some((name) => typeof module[name] !== 'function')) {
      throw new Error('required OpenMAIC generation API export is missing');
    }
    return {
      available: true,
      schemaVersion: schemas.output,
      generator: 'openmaic',
      packages: {
        '@openmaic/generation': '0.3.1',
        '@openmaic/dsl': '0.10.1',
      },
      supportedContracts: [
        { input: schemas.input, output: schemas.output },
        {
          input: questionSchemas.generationInput,
          output: questionSchemas.candidatesOutput,
        },
        {
          input: questionSchemas.verificationInput,
          output: questionSchemas.verificationOutput,
        },
        {
          input: questionSchemas.consistencyRepairInput,
          output: questionSchemas.consistencyRepairOutput,
        },
        {
          input: classroomSchemas.input,
          output: classroomSchemas.output,
          dslVersion: classroomSchemas.dsl,
        },
      ],
      node: process.version,
    };
  } catch (error) {
    return {
      available: false,
      schemaVersion: schemas.output,
      generator: 'openmaic',
      reason: error instanceof Error ? error.message : String(error),
      node: process.version,
    };
  }
}

async function generateDraft(payload) {
  const startedAt = performance.now();
  const request = normalizeRequest(payload);
  const aiCall = request.mode === 'fake'
    ? createFakeAICall(request.fakeResponses)
    : createLiveAICall(request.provider);
  const { generateSceneContent, generateSceneOutlinesFromRequirements } = await loadOpenMaic();
  const requirements = {
    requirement: buildRequirement(request.skillBoundary),
    userBio: `Grade ${request.skillBoundary.gradeCode}; fixed skill ${request.skillBoundary.skillId}`,
    interactiveMode: false,
    taskEngineMode: false,
  };
  const outlineResult = await generateSceneOutlinesFromRequirements(
    requirements,
    undefined,
    undefined,
    aiCall,
    {
      imageGenerationEnabled: false,
      videoGenerationEnabled: false,
      visionEnabled: false,
    },
  );
  if (!outlineResult.success || !outlineResult.data) {
    throw new ContractError(outlineResult.error || 'OpenMAIC outline generation failed', 'generation_failed');
  }

  const outlines = outlineResult.data.outlines.slice(0, request.skillBoundary.maxScenes);
  const contents = request.includeSceneContent
    ? await Promise.all(
        outlines.map((outline) =>
          generateSceneContent(outline, aiCall, {
            languageDirective: outlineResult.data.languageDirective,
            targetLanguage: request.skillBoundary.language,
            userRequirements: requirements,
            visionEnabled: false,
            allowProceduralSkill: false,
          }),
        ),
      )
    : outlines.map(() => null);
  return buildDraft({
    request,
    generation: { ...outlineResult.data, outlines },
    contents,
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  });
}

function aiCallFor(request) {
  return request.mode === 'fake'
    ? createFakeAICall(request.fakeResponses)
    : createLiveAICall(request.provider);
}

async function generateQuestionCandidates(payload) {
  const startedAt = performance.now();
  const request = normalizeQuestionGenerationRequest(payload);
  const aiCall = aiCallFor(request);
  const { generateSceneOutlinesFromRequirements, parseJsonResponse } = await loadOpenMaic();
  const requirements = {
    requirement: buildQuestionOutlineRequirement(request),
    userBio: `Grade ${request.gradeCode}; subject ${request.subject}; fixed skill ${request.skillBoundary.skillId}`,
    interactiveMode: false,
    taskEngineMode: false,
  };
  const outlineResult = await generateSceneOutlinesFromRequirements(
    requirements,
    undefined,
    undefined,
    aiCall,
    {
      imageGenerationEnabled: false,
      videoGenerationEnabled: false,
      visionEnabled: false,
    },
  );
  if (!outlineResult.success || !outlineResult.data) {
    throw new ContractError(
      outlineResult.error || 'OpenMAIC question-plan generation failed',
      'generation_failed',
    );
  }
  const prompts = buildQuestionGenerationPrompts(request, outlineResult.data);
  const response = await aiCall(prompts.system, prompts.user);
  const generated = parseJsonResponse(response);
  if (!generated || typeof generated !== 'object' || Array.isArray(generated)) {
    throw new ContractError('Kimi returned invalid candidate-question JSON', 'invalid_generation');
  }
  const normalizeCandidateRepairResponse = (response) => {
    const raw = parseJsonResponse(response);
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new ContractError('Kimi returned invalid repaired-candidate JSON', 'invalid_generation');
    }
    const frozen = freezeUnchangedQuestionAuthority(generated, raw);
    assertQuestionCandidateRepairAuthority(generated, frozen);
    const value = applyHostOwnedPracticeHints(request, frozen);
    assertQuestionSetOriginality(request, value.questions);
    return value;
  };
  const repairPrompts = buildQuestionCandidateRepairPrompts(request, generated);
  let repaired;
  try {
    repaired = normalizeCandidateRepairResponse(
      await aiCall(repairPrompts.system, repairPrompts.user),
    );
  } catch (error) {
    const repairableDuplicate = error instanceof ContractError
      && (
        error.code === 'duplicate_candidate'
        || (
          error.code === 'invalid_generation'
          && (
            /generated\.questions\[\d+\]\.choices contains duplicate ids or labels/.test(
              error.message,
            )
            || /out-of-bound tens-and-ones representation/.test(error.message)
            || /production blueprint:/.test(error.message)
          )
        )
      );
    if (!repairableDuplicate) throw error;
    const retryPrompts = buildQuestionCandidateRepairRetryPrompts(request, generated);
    repaired = normalizeCandidateRepairResponse(
      await aiCall(retryPrompts.system, retryPrompts.user),
    );
  }
  // The public lesson copy is produced by a fresh, stateless call that receives
  // only the fixed boundary and q1 worked example. It never receives q2-q5
  // prompts, choices, hints, answers, validation feedback, or evaluation data.
  const answerBlindInput = buildAnswerBlindLessonTextInput(request, repaired);
  const lessonTextPrompts = buildAnswerBlindLessonTextPrompts(request, repaired);
  let lessonText;
  try {
    const lessonTextResponse = await aiCall(lessonTextPrompts.system, lessonTextPrompts.user);
    const lessonTextRaw = parseJsonResponse(lessonTextResponse);
    if (!lessonTextRaw || typeof lessonTextRaw !== 'object' || Array.isArray(lessonTextRaw)) {
      throw new ContractError(
        'Kimi returned invalid answer-blind lesson-text JSON',
        'invalid_generation',
      );
    }
    lessonText = compileAnswerBlindLessonTextProviderOutput(lessonTextRaw, request);
  } catch (error) {
    if (
      !(error instanceof ContractError)
      || request.gradeCode !== 'primary_1'
      || request.subject !== 'math'
      || request.skillBoundary.skillId !== 'number_sense_20'
    ) throw error;
    lessonText = compileAnswerBlindLessonTextFallback(answerBlindInput);
  }
  // Reconcile practice questions to the now-frozen answer-blind lesson copy.
  // This call may regenerate q2-q5, but it cannot edit q1 or any lesson text.
  const reconciliationPrompts = buildQuestionReconciliationPrompts(
    request,
    repaired,
    lessonText,
  );
  const normalizeReconciliationResponse = (response) => {
    const raw = parseJsonResponse(response);
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new ContractError(
        'Kimi returned invalid question-reconciliation JSON',
        'invalid_generation',
      );
    }
    const normalized = normalizeQuestionReconciliation(raw, request);
    const frozen = freezeQuestionReconciliation(repaired, normalized);
    assertQuestionCandidateReconciliationAuthority(repaired, frozen);
    const value = applyHostOwnedPracticeHints(request, frozen);
    assertQuestionSetOriginality(request, value.questions);
    return value;
  };
  let normalizedReconciliation;
  try {
    normalizedReconciliation = normalizeReconciliationResponse(
      await aiCall(reconciliationPrompts.system, reconciliationPrompts.user),
    );
  } catch (error) {
    const repairableDuplicate = error instanceof ContractError
      && (
        error.code === 'duplicate_candidate'
        || (
          error.code === 'invalid_generation'
          && (
            /generated\.questions\[\d+\]\.choices contains duplicate ids or labels/.test(
              error.message,
            )
            || /out-of-bound tens-and-ones representation/.test(error.message)
            || /production blueprint:/.test(error.message)
          )
        )
      );
    if (!repairableDuplicate) throw error;
    const retryPrompts = buildQuestionReconciliationRetryPrompts(
      request,
      repaired,
      lessonText,
    );
    normalizedReconciliation = normalizeReconciliationResponse(
      await aiCall(retryPrompts.system, retryPrompts.user),
    );
  }
  let reconciliation = normalizedReconciliation;
  for (let repairRound = 0; repairRound < 2; repairRound += 1) {
    const teachingLeakIndexes = teachingFlowPracticeAnswerLeakIndexes(
      lessonText.teachingFlow,
      reconciliation.questions,
    );
    if (!teachingLeakIndexes.length) break;
    const leakRepairPrompts = buildQuestionPracticeLeakRepairPrompts(
      request,
      reconciliation,
      lessonText,
      teachingLeakIndexes,
    );
    const leakRepairResponse = await aiCall(
      leakRepairPrompts.system,
      leakRepairPrompts.user,
    );
    const leakRepairRaw = parseJsonResponse(leakRepairResponse);
    if (!leakRepairRaw
      || typeof leakRepairRaw !== 'object'
      || Array.isArray(leakRepairRaw)) {
      throw new ContractError(
        'Kimi returned invalid practice-leak repair JSON',
        'invalid_generation',
      );
    }
    const leakRepair = freezeQuestionReconciliation(
      reconciliation,
      normalizeQuestionReconciliation(leakRepairRaw, request),
    );
    assertQuestionPracticeLeakRepairAuthority(
      reconciliation,
      leakRepair,
      teachingLeakIndexes,
    );
    reconciliation = applyHostOwnedPracticeHints(request, leakRepair);
  }
  if (teachingFlowPracticeAnswerLeakIndexes(
    lessonText.teachingFlow,
    reconciliation.questions,
  ).length) {
    throw new ContractError(
      'practice-leak repair did not remove every teaching answer disclosure after two rounds',
      'invalid_generation',
    );
  }
  const choicePromptViolations = choicePromptViolationIndexes(reconciliation.questions);
  if (choicePromptViolations.includes(0)) {
    throw new ContractError(
      'question reconciliation repeats rendered choice labels in the fixed q1 worked example',
      'invalid_generation',
    );
  }
  if (choicePromptViolations.length) {
    const choiceRepairPrompts = buildChoicePromptRepairPrompts(
      request,
      reconciliation.questions,
      choicePromptViolations,
    );
    const choiceRepairResponse = await aiCall(
      choiceRepairPrompts.system,
      choiceRepairPrompts.user,
    );
    const choiceRepairRaw = parseJsonResponse(choiceRepairResponse);
    if (!choiceRepairRaw
      || typeof choiceRepairRaw !== 'object'
      || Array.isArray(choiceRepairRaw)) {
      throw new ContractError(
        'Kimi returned invalid choice-prompt repair JSON',
        'invalid_generation',
      );
    }
    reconciliation = normalizeChoicePromptRepair(
      choiceRepairRaw,
      reconciliation,
      choicePromptViolations,
    );
    assertQuestionCandidateReconciliationAuthority(repaired, reconciliation);
    reconciliation = applyHostOwnedPracticeHints(request, reconciliation);
  }
  reconciliation = applyHostOwnedPracticeHints(request, reconciliation);
  return buildQuestionCandidates({
    request,
    generationPlan: outlineResult.data,
    generated: { ...repaired, ...lessonText, ...reconciliation },
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  });
}

async function verifyQuestionsIndependently(payload) {
  const startedAt = performance.now();
  const request = normalizeQuestionVerificationRequest(payload);
  // A verification request creates a new callback and sends only public question
  // fields. It cannot inherit the generation prompt or candidate answer context.
  const aiCall = aiCallFor(request);
  const { parseJsonResponse } = await loadOpenMaic();
  const prompts = buildIndependentVerificationPrompts(request);
  const response = await aiCall(prompts.system, prompts.user);
  const generated = parseJsonResponse(response);
  if (!generated || typeof generated !== 'object' || Array.isArray(generated)) {
    throw new ContractError('Kimi returned invalid independent-solution JSON', 'invalid_verification');
  }
  return buildIndependentSolution({
    request,
    generated,
    elapsedMs: Math.max(0, Math.round(performance.now() - startedAt)),
  });
}

async function repairQuestionConsistency(payload) {
  const startedAt = performance.now();
  const request = normalizeQuestionConsistencyRepairRequest(payload);
  const aiCall = aiCallFor(request);
  const { parseJsonResponse } = await loadOpenMaic();
  const prompts = buildQuestionConsistencyRepairPrompts(request);
  const normalizeResponse = (response) => {
    const raw = parseJsonResponse(response);
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      throw new ContractError(
        'Kimi returned invalid question-consistency repair JSON',
        'invalid_generation',
      );
    }
    return normalizeQuestionConsistencyRepair(raw, request);
  };
  let repair;
  try {
    repair = normalizeResponse(await aiCall(prompts.system, prompts.user));
  } catch (error) {
    if (!(error instanceof ContractError) || error.code !== 'invalid_generation') {
      throw error;
    }
    const retryPrompts = buildQuestionConsistencyRepairRetryPrompts(request);
    repair = normalizeResponse(
      await aiCall(retryPrompts.system, retryPrompts.user),
    );
  }
  return buildQuestionConsistencyRepairResult({
    request,
    repair,
    elapsedMs: performance.now() - startedAt,
  });
}

async function generateClassroom(payload) {
  const startedAt = performance.now();
  const request = normalizeClassroomGenerationRequest(payload);
  const aiCall = aiCallFor(request);
  const { generateSceneOutlinesFromRequirements, parseJsonResponse } = await loadOpenMaic();
  const requirements = {
    requirement: buildClassroomRequirement(request),
    userBio: `Grade ${request.gradeCode}; subject ${request.subject}; fixed skill ${request.skillBoundary.skillId}`,
    interactiveMode: true,
    taskEngineMode: false,
  };
  const outlineResult = await generateSceneOutlinesFromRequirements(
    requirements,
    undefined,
    undefined,
    aiCall,
    {
      imageGenerationEnabled: false,
      videoGenerationEnabled: false,
      visionEnabled: false,
      allowProceduralSkill: false,
    },
  );
  if (!outlineResult.success || !outlineResult.data) {
    throw new ContractError(
      outlineResult.error || 'OpenMAIC classroom outline generation failed',
      'generation_failed',
    );
  }
  const compilationPrompts = buildClassroomIntentCompilationPrompts(
    request,
    outlineResult.data,
  );
  const compilationResponse = await aiCall(
    compilationPrompts.system,
    compilationPrompts.user,
  );
  const compilationValue = parseJsonResponse(compilationResponse);
  if (
    !compilationValue
    || typeof compilationValue !== 'object'
    || Array.isArray(compilationValue)
  ) {
    throw new ContractError(
      'Kimi returned invalid classroom-intent JSON',
      'invalid_generation',
    );
  }
  let intent;
  let intentValue = compilationValue;
  for (let repairAttempt = 0; repairAttempt <= 2; repairAttempt += 1) {
    try {
      intent = normalizeClassroomIntent(intentValue, request);
      break;
    } catch (error) {
      if (!(error instanceof ContractError) || error.code !== 'invalid_generation') throw error;
      if (repairAttempt === 2) throw error;
      const repairPrompts = buildClassroomIntentRepairPrompts(request, intentValue);
      const repairResponse = await aiCall(repairPrompts.system, repairPrompts.user);
      intentValue = parseJsonResponse(repairResponse);
      if (!intentValue || typeof intentValue !== 'object' || Array.isArray(intentValue)) {
        throw new ContractError(
          'Kimi returned invalid classroom-intent repair JSON',
          'invalid_generation',
        );
      }
    }
  }

  // This is a separate callback after classroom generation. The reviewer sees
  // only the fixed boundary, public question shells and normalized presentation
  // text; it never receives an answer key from Mira.
  const reviewPrompts = buildClassroomIntentReviewPrompts(request, intent);
  const reviewResponse = await aiCall(reviewPrompts.system, reviewPrompts.user);
  const reviewValue = parseJsonResponse(reviewResponse);
  if (!reviewValue || typeof reviewValue !== 'object' || Array.isArray(reviewValue)) {
    throw new ContractError('Kimi returned invalid classroom review JSON', 'invalid_generation');
  }
  const teachingReview = normalizeClassroomReview(reviewValue);
  return buildClassroomIntentSource({
    request,
    generation: outlineResult.data,
    intent,
    teachingReview,
    elapsedMs: performance.now() - startedAt,
  });
}

async function dispatch(payload) {
  if (payload?.schemaVersion === classroomSchemas.input) {
    return generateClassroom(payload);
  }
  if (payload?.schemaVersion === questionSchemas.generationInput) {
    return generateQuestionCandidates(payload);
  }
  if (payload?.schemaVersion === questionSchemas.verificationInput) {
    return verifyQuestionsIndependently(payload);
  }
  if (payload?.schemaVersion === questionSchemas.consistencyRepairInput) {
    return repairQuestionConsistency(payload);
  }
  return generateDraft(payload);
}

function errorOutputSchema(payload) {
  if (payload?.schemaVersion === classroomSchemas.input) {
    return classroomSchemas.output;
  }
  if (payload?.schemaVersion === questionSchemas.generationInput) {
    return questionSchemas.candidatesOutput;
  }
  if (payload?.schemaVersion === questionSchemas.verificationInput) {
    return questionSchemas.verificationOutput;
  }
  if (payload?.schemaVersion === questionSchemas.consistencyRepairInput) {
    return questionSchemas.consistencyRepairOutput;
  }
  return schemas.output;
}

async function main() {
  if (process.argv.includes('--question-phase-v2')) {
    await runQuestionPhaseV2();
    return;
  }
  if (process.argv.includes('--availability')) {
    const result = await availability();
    writeJson(result);
    process.exitCode = result.available ? 0 : 2;
    return;
  }
  let payload;
  try {
    payload = await readStdin();
    writeJson(await dispatch(payload));
  } catch (error) {
    const code = error instanceof ContractError ? error.code : 'generation_failed';
    writeJson({
      schemaVersion: errorOutputSchema(payload),
      generator: 'openmaic',
      ...(typeof payload?.requestId === 'string' ? { requestId: payload.requestId } : {}),
      error: {
        code,
        message: error instanceof Error ? error.message : String(error),
      },
    });
    process.exitCode = 1;
  }
}

await main();
