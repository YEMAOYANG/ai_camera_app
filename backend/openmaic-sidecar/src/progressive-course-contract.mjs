import {readFileSync} from 'node:fs';
import {ContractError} from './contract.mjs';
import {createSingleDispatchAICall, QuestionPhaseDispatchError} from './provider.mjs';

export const progressiveSchemas = Object.freeze({
  generationInput: 'mira.openmaic.progressive-generation-input.v1',
  verificationInput: 'mira.openmaic.progressive-verification-input.v1',
  output: 'mira.openmaic.progressive-result.v1',
});

const prompts = JSON.parse(readFileSync(new URL('../../prompts/progressive-course.v1.json', import.meta.url), 'utf8'));

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exactKeys = (value, keys) => object(value)
  && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const text = (value, maximum = 6000) => typeof value === 'string' && value.trim().length > 0
  && value.length <= maximum;

function validateGenerationContext(context, brief) {
  if (context === undefined) return;
  const validQuestion = question => {
    if (!object(question) || !text(question.id, 128) || !text(question.prompt)) return false;
    if (question.type === 'single_choice') {
      return exactKeys(question, ['id', 'type', 'prompt', 'choices'])
        && Array.isArray(question.choices) && question.choices.length >= 2 && question.choices.length <= 4
        && question.choices.every(choice => exactKeys(choice, ['id', 'label'])
          && text(choice.id, 128) && text(choice.label))
        && new Set(question.choices.map(choice => choice.id)).size === question.choices.length;
    }
    if (question.type === 'tap_objects') {
      return exactKeys(question, ['id', 'type', 'prompt', 'objects'])
        && Array.isArray(question.objects) && question.objects.length >= 1 && question.objects.length <= 20
        && question.objects.every(item => exactKeys(item, ['id', 'shape', 'color'])
          && text(item.id, 128) && ['circle', 'square', 'triangle'].includes(item.shape)
          && ['red', 'blue', 'yellow', 'green'].includes(item.color))
        && new Set(question.objects.map(item => item.id)).size === question.objects.length;
    }
    return false;
  };
  if (!exactKeys(context, ['schemaVersion', 'curriculumVersion', 'lessonId', 'previousQuestions'])
      || context.schemaVersion !== 'mira.learning.progressive-generation-context.v1'
      || context.curriculumVersion !== brief.binding.curriculumVersion
      || context.lessonId !== brief.lesson.lessonId || brief.lesson.assessmentMode !== 'objective'
      || !Array.isArray(context.previousQuestions)
      || !context.previousQuestions.every(item => exactKeys(item, ['courseId', 'courseVersion', 'question'])
        && text(item.courseId, 255) && text(item.courseVersion, 64) && validQuestion(item.question))) {
    throw new ContractError('invalid public prior-question context', 'progressive_invalid_generation_context');
  }
}

function generationContentSkeleton(brief) {
  const lesson = brief.lesson;
  const knowledgeIds = lesson.introducedKnowledgeIds;
  const step = (phase, questionId) => ({phase, text: '', knowledgeIds: [...knowledgeIds],
    requiresKnowledgeIds: phase === 'teach' ? [] : [...knowledgeIds],
    ...(questionId ? {questionId} : {})});
  let questions = [];
  let progressiveFlow;
  if (lesson.assessmentMode === 'observed') {
    progressiveFlow = ['teach', 'example', 'observe', 'recap'].map(phase => step(phase));
  } else {
    const minimum = Math.max(5, lesson.assessmentCriteria?.minimumDistinctTasks ?? 5);
    if (!Number.isInteger(minimum) || minimum > 10) {
      throw new ContractError('unsupported progressive assessment count', 'progressive_invalid_input');
    }
    const kinds = lesson.constraints?.assessmentEvidenceKinds ?? [];
    const kind = kinds.includes('count_objects') ? 'count_objects'
      : kinds.find(value => ['token_match', 'numeric_expression', 'independent_choice'].includes(value));
    if (!kind) throw new ContractError('missing progressive assessment capability', 'progressive_invalid_input');
    const ids = ['guided_1', ...Array.from({length: minimum}, (_, index) => `independent_${index + 1}`)];
    questions = ids.map(id => ({id, type: kind === 'count_objects' ? 'tap_objects' : 'single_choice',
      prompt: '', ...(kind === 'count_objects' ? {objects: [], answer: []}
        : {choices: ['A', 'B', 'C'].map(choiceId => ({id: choiceId, label: ''})), answer: ''}),
      hint: '', explanation: '', knowledgeIds: [...knowledgeIds],
      evidence: {kind, ...(kind === 'token_match' ? {targetToken: ''} : {}),
        ...(kind === 'numeric_expression' ? {expression: ''} : {})},
    }));
    progressiveFlow = [step('teach'), step('example'),
      ...ids.map((id, index) => step(index === 0 ? 'guided' : 'independent', id)), step('recap')];
  }
  return {
    schemaVersion: 'mira.learning.progressive-course.v1', progressiveLesson: brief.binding,
    difficultyCode: 'basic', assessmentMode: lesson.assessmentMode,
    autoMasteryEligible: brief.autoMasteryEligible, manualConfirmationRequired: brief.manualConfirmationRequired,
    estimatedMinutes: 10, intro: '', progressiveFlow, questions,
  };
}

export function buildProgressivePrompt(payload) {
  const verification = payload.schemaVersion === progressiveSchemas.verificationInput;
  const {brief, requestId} = payload;
  validateGenerationContext(payload.generationContext, brief);
  const prompt = verification ? prompts.verification : prompts.generation;
  const correction = payload.correctionRequirements;
  if (correction !== undefined && (verification || !correction || typeof correction !== 'object'
      || Array.isArray(correction) || Object.keys(correction).sort().join(',') !== 'auditShaId,issues'
      || !/^[0-9a-f]{64}$/.test(correction.auditShaId ?? '')
      || !Array.isArray(correction.issues) || correction.issues.length < 1 || correction.issues.length > 32
      || correction.issues.some(issue => typeof issue !== 'string' || !issue.trim() || issue.length > 6000)
      || JSON.stringify(correction).length > 32000)) {
    throw new ContractError('invalid progressive correction requirements', 'progressive_invalid_input');
  }
  const lessonScopedRequirements = (prompts.lessonScopes ?? [])
    .filter(scope => Object.entries(scope.match).every(([key, value]) => brief.lesson[key] === value))
    .flatMap(scope => scope[verification ? 'verificationRequirements' : 'generationRequirements']);
  // Give the model literal server identity values, never a textual object reference.
  // This only constrains a future reply: it does not repair a returned candidate.
  const expectedOutputSkeleton = verification ? {verification: {
    requestId, lessonId: brief.lesson.lessonId, binding: brief.binding,
    passed: null, issues: [], undeclaredKnowledgeIds: [], answers: {},
  }} : {candidateCourse: {
    gradeCode: brief.lesson.gradeCode, subject: brief.lesson.subject, nodeCode: brief.lesson.lessonId,
    title: brief.lesson.title, objective: brief.lesson.learningObjectives.join('；'),
    content: generationContentSkeleton(brief),
  }};
  return {system: prompt.system, user: JSON.stringify({
    requestId, requirements: prompt.requirements, lessonScopedRequirements, expectedOutputSkeleton, brief,
    ...(verification ? {publicCandidate: payload.publicCandidate} : {}),
    ...(correction !== undefined ? {correctionRequirements: correction} : {}),
    ...(payload.generationContext !== undefined ? {generationContext: payload.generationContext} : {}),
  })};
}

export async function runProgressiveCourse(payload) {
  const verification = payload?.schemaVersion === progressiveSchemas.verificationInput;
  const brief = payload?.brief;
  if ((!verification && payload?.schemaVersion !== progressiveSchemas.generationInput)
      || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(payload?.requestId ?? '')
      || brief?.schemaVersion !== 'mira.learning.progressive-generation-brief.v1'
      || brief?.contractVersion !== prompts.version
      || brief?.binding?.lessonId !== brief?.lesson?.lessonId
      || brief?.binding?.curriculumVersion !== 'mira.primary.progressive.v1'
      || brief?.binding?.difficultyCode !== 'basic'
      || !['objective', 'observed'].includes(brief?.lesson?.assessmentMode)
      || !Array.isArray(brief?.allowedKnowledgeIds)
      || !Array.isArray(brief?.mustNotDependOnKnowledgeIds)
      || (verification && (!payload.publicCandidate || typeof payload.publicCandidate !== 'object'))) {
    throw new ContractError('invalid progressive lesson request', 'progressive_invalid_input');
  }
  const prompt = buildProgressivePrompt(payload);
  let content, receipt = {};
  if (payload.mode === 'fake') {
    if (process.env.OPENMAIC_FAKE_MODE !== '1' || !Array.isArray(payload.fakeResponses)
        || payload.fakeResponses.length !== 1 || typeof payload.fakeResponses[0] !== 'string') {
      throw new ContractError('exactly one fake reply is required', 'progressive_invalid_input');
    }
    content = payload.fakeResponses[0];
  } else if (payload.mode === 'live') {
    try {
      const result = await createSingleDispatchAICall(payload.provider, {
        requestId: payload.requestId,
        questionPhase: verification ? 'progressive_verification' : 'progressive_generation',
      })(prompt.system, prompt.user);
      ({content, ...receipt} = result);
    } catch (error) {
      if (error instanceof QuestionPhaseDispatchError) {
        throw new ContractError(error.safeErrorCode, error.safeErrorCode);
      }
      throw error;
    }
  } else {
    throw new ContractError('invalid progressive execution mode', 'progressive_invalid_input');
  }
  let parsed;
  try { parsed = JSON.parse(content); }
  catch { throw new ContractError('progressive reply must be strict JSON', 'progressive_invalid_reply'); }
  const key = verification ? 'verification' : 'candidateCourse';
  // The verifier prompt asks for a verification object; both its named envelope
  // and that exact object are valid transport shapes. Host validation still
  // checks the frozen binding, independent answers and every review criterion.
  const verificationKeys = ['requestId', 'lessonId', 'binding', 'passed', 'issues', 'undeclaredKnowledgeIds', 'answers'];
  if (verification && parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      && Object.keys(parsed).sort().join(',') === verificationKeys.sort().join(',')
      && typeof parsed.passed === 'boolean' && Array.isArray(parsed.issues)
      && Array.isArray(parsed.undeclaredKnowledgeIds)) {
    parsed = {verification: parsed};
  }
  if (!parsed?.[key] || typeof parsed[key] !== 'object' || Array.isArray(parsed[key])) {
    throw new ContractError('progressive reply is missing its result', 'progressive_invalid_reply');
  }
  return {schemaVersion: progressiveSchemas.output, generator: 'openmaic', requestId: payload.requestId,
    [key]: parsed[key], provider: payload.provider?.name, model: payload.provider?.model, receipt};
}
