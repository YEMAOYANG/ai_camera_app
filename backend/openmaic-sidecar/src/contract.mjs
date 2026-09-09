const INPUT_SCHEMA = 'mira.openmaic.generate.v1';
const OUTPUT_SCHEMA = 'mira.openmaic.draft.v1';
const SAFE_DETERMINISTIC_SUBJECTS = new Set(['chinese', 'math', 'english']);
const SAFE_PRIMARY_GRADES = new Set(
  Array.from({ length: 6 }, (_, index) => `primary_${index + 1}`),
);
const REQUIRED_OUTCOME_MODE = 'scored_deterministic';
const REQUIRED_SESSION_KIND = 'lesson';

const ANSWER_KEYS = new Set([
  'answer',
  'answers',
  'correctAnswer',
  'correctAnswers',
  'correct_answer',
  'correct_answers',
  'correct',
  'isCorrect',
  'expectedAnswer',
  'expectedAnswers',
  'referenceAnswer',
  'referenceAnswers',
  'analysis',
  'commentPrompt',
  'hasAnswer',
  'solution',
  'solutions',
  'rubric',
  'gradingRubric',
  'evaluation',
  'evaluationMode',
  'evaluator',
  'evaluatorVersion',
  'expected',
  'acceptedAnswers',
  'expectedOptionId',
  'expectedSequence',
  'passingScore',
  'score',
  'points',
]);

const ACTION_OR_MEDIA_KEYS = new Set([
  'action',
  'actions',
  'audio',
  'audios',
  'html',
  'image',
  'images',
  'media',
  'mediaGenerations',
  'mediaRef',
  'src',
  'video',
  'videos',
  'whiteboard',
  'whiteboards',
]);

const SAFE_ELEMENT_TYPES = new Set(['text', 'shape']);
const NORMALIZED_ANSWER_KEYS = new Set([...ANSWER_KEYS].map((key) => key.toLowerCase()));
const NORMALIZED_ACTION_OR_MEDIA_KEYS = new Set(
  [...ACTION_OR_MEDIA_KEYS].map((key) => key.toLowerCase()),
);

const HTML_ENTITY_MAP = Object.freeze({
  amp: '&',
  apos: "'",
  gt: '>',
  lt: '<',
  nbsp: ' ',
  quot: '"',
});

export class ContractError extends Error {
  constructor(message, code = 'invalid_input') {
    super(message);
    this.name = 'ContractError';
    this.code = code;
  }
}

function cleanString(value, field, { required = false, max = 500 } = {}) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (required && !result) {
    throw new ContractError(`${field} is required`);
  }
  if (result.length > max) {
    throw new ContractError(`${field} exceeds ${max} characters`);
  }
  return result;
}

function cleanStringList(value, field, { required = false, maxItems = 20 } = {}) {
  if (value == null) {
    if (required) throw new ContractError(`${field} is required`);
    return [];
  }
  if (!Array.isArray(value)) {
    throw new ContractError(`${field} must be an array`);
  }
  const result = value
    .map((item, index) => cleanString(item, `${field}[${index}]`, { required: true }))
    .filter(Boolean);
  if (required && result.length === 0) {
    throw new ContractError(`${field} must not be empty`);
  }
  if (result.length > maxItems) {
    throw new ContractError(`${field} exceeds ${maxItems} items`);
  }
  return [...new Set(result)];
}

export function normalizeRequest(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new ContractError('input must be a JSON object');
  }
  if (payload.schemaVersion !== INPUT_SCHEMA) {
    throw new ContractError(`schemaVersion must be ${INPUT_SCHEMA}`);
  }
  const requestId = cleanString(payload.requestId, 'requestId', { required: true, max: 120 });
  const raw = payload.skillBoundary;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new ContractError('skillBoundary is required');
  }

  const maxScenes = Number(raw.maxScenes ?? 4);
  const durationMinutes = Number(raw.durationMinutes ?? 12);
  if (!Number.isInteger(maxScenes) || maxScenes < 1 || maxScenes > 8) {
    throw new ContractError('skillBoundary.maxScenes must be an integer from 1 to 8');
  }
  if (!Number.isFinite(durationMinutes) || durationMinutes < 3 || durationMinutes > 45) {
    throw new ContractError('skillBoundary.durationMinutes must be from 3 to 45');
  }

  const subject = cleanString(raw.subject, 'skillBoundary.subject', {
    required: true,
    max: 80,
  });
  if (!SAFE_DETERMINISTIC_SUBJECTS.has(subject)) {
    throw new ContractError('skillBoundary.subject is not enabled for OpenMAIC');
  }
  const outcomeMode = cleanString(raw.outcomeMode, 'skillBoundary.outcomeMode', {
    required: true,
    max: 40,
  });
  if (outcomeMode !== REQUIRED_OUTCOME_MODE) {
    throw new ContractError(`skillBoundary.outcomeMode must be ${REQUIRED_OUTCOME_MODE}`);
  }
  const sessionKind = cleanString(raw.sessionKind, 'skillBoundary.sessionKind', {
    required: true,
    max: 40,
  });
  if (sessionKind !== REQUIRED_SESSION_KIND) {
    throw new ContractError(`skillBoundary.sessionKind must be ${REQUIRED_SESSION_KIND}`);
  }

  const gradeCode = cleanString(raw.gradeCode, 'skillBoundary.gradeCode', {
    required: true,
    max: 40,
  });
  if (!SAFE_PRIMARY_GRADES.has(gradeCode)) {
    throw new ContractError('skillBoundary.gradeCode must be primary_1 through primary_6');
  }

  const skillBoundary = {
    gradeCode,
    subject,
    skillId: cleanString(raw.skillId, 'skillBoundary.skillId', { required: true, max: 120 }),
    skillTitle: cleanString(raw.skillTitle, 'skillBoundary.skillTitle', { max: 160 }),
    learningObjectives: cleanStringList(
      raw.learningObjectives,
      'skillBoundary.learningObjectives',
      { required: true, maxItems: 12 },
    ),
    allowedContent: cleanStringList(raw.allowedContent, 'skillBoundary.allowedContent'),
    excludedContent: cleanStringList(raw.excludedContent, 'skillBoundary.excludedContent'),
    prerequisiteSkills: cleanStringList(
      raw.prerequisiteSkills,
      'skillBoundary.prerequisiteSkills',
      { maxItems: 12 },
    ),
    language: cleanString(raw.language || 'zh-CN', 'skillBoundary.language', {
      required: true,
      max: 20,
    }),
    outcomeMode,
    sessionKind,
    maxScenes,
    durationMinutes,
  };

  return {
    schemaVersion: INPUT_SCHEMA,
    requestId,
    skillBoundary,
    includeSceneContent: payload.includeSceneContent !== false,
    mode: payload.mode === 'fake' ? 'fake' : 'live',
    fakeResponses: Array.isArray(payload.fakeResponses) ? payload.fakeResponses.map(String) : [],
    provider: normalizeProvider(payload.provider),
  };
}

export function normalizeProvider(raw) {
  const value = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  const apiKeyEnv = cleanString(value.apiKeyEnv || 'APP_AI_API_KEY', 'provider.apiKeyEnv', {
    required: true,
    max: 80,
  });
  if (!/^[A-Z][A-Z0-9_]*$/.test(apiKeyEnv)) {
    throw new ContractError('provider.apiKeyEnv must be an environment variable name');
  }
  const timeoutMs = Number(value.timeoutMs ?? 90000);
  const maxTokens = Number(value.maxTokens ?? 6000);
  const temperature = Number(value.temperature ?? 0.2);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 180000) {
    throw new ContractError('provider.timeoutMs must be an integer from 1000 to 180000');
  }
  if (!Number.isInteger(maxTokens) || maxTokens < 512 || maxTokens > 32000) {
    throw new ContractError('provider.maxTokens must be an integer from 512 to 32000');
  }
  if (!Number.isFinite(temperature) || temperature < 0 || temperature > 1) {
    throw new ContractError('provider.temperature must be from 0 to 1');
  }
  return {
    name: cleanString(value.name || 'kimi', 'provider.name', { required: true, max: 80 }),
    model: cleanString(value.model, 'provider.model', { required: true, max: 160 }),
    baseUrl: cleanString(value.baseUrl, 'provider.baseUrl', { required: true, max: 500 }),
    apiKeyEnv,
    timeoutMs,
    maxTokens,
    temperature,
  };
}

export function buildRequirement(boundary) {
  const list = (values) => (values.length ? values.map((value) => `- ${value}`).join('\n') : '- None');
  return [
    'Draft a short child-facing lesson strictly inside this fixed Mira skill boundary.',
    `Grade code: ${boundary.gradeCode}`,
    `Subject: ${boundary.subject}`,
    `Outcome mode: ${boundary.outcomeMode}`,
    `Session kind: ${boundary.sessionKind}`,
    `Skill ID: ${boundary.skillId}`,
    `Skill title: ${boundary.skillTitle || boundary.skillId}`,
    `Language: ${boundary.language}`,
    `Total duration: about ${boundary.durationMinutes} minutes`,
    `Maximum scenes: ${boundary.maxScenes}`,
    '',
    'Fixed learning objectives (do not add or replace objectives):',
    list(boundary.learningObjectives),
    '',
    'Allowed content:',
    list(boundary.allowedContent),
    '',
    'Prerequisite skills that may be reviewed briefly:',
    list(boundary.prerequisiteSkills),
    '',
    'Excluded content (must not appear):',
    list(boundary.excludedContent),
    '',
    'The result is an unverified teaching draft. Mira owns curriculum truth, computes all',
    'authoritative answers independently, and validates every item before publishing.',
    'Do not claim that any generated answer, solution, rubric, or mastery decision is authoritative.',
    'Do not emit answer keys, accepted answers, evaluator configuration, scoring rules, or points.',
    'Prefer an explain -> guided example -> learner question -> recap sequence.',
    'For early-primary learners, use one visible teaching move per scene, short action titles, concrete manipulatives or before/after states, and a meaningful learner action at least every second scene.',
    'Every visual must teach, scaffold, or receive an action. Do not substitute decoration, repeated text cards, or a static picture for explanation or interaction.',
  ].join('\n');
}

function sanitizeDraftValue(value) {
  if (Array.isArray(value)) return value.map(sanitizeDraftValue);
  if (!value || typeof value !== 'object') {
    return typeof value === 'string' ? htmlToPlainText(value) : value;
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => {
        const normalized = key.toLowerCase();
        return (
          !NORMALIZED_ANSWER_KEYS.has(normalized) &&
          !NORMALIZED_ACTION_OR_MEDIA_KEYS.has(normalized)
        );
      })
      .map(([key, child]) => {
        if (key.toLowerCase() !== 'elements' || !Array.isArray(child)) {
          return [key, sanitizeDraftValue(child)];
        }
        const safeElements = child.filter((element) => {
          if (!element || typeof element !== 'object' || Array.isArray(element)) return false;
          return SAFE_ELEMENT_TYPES.has(String(element.type || '').trim().toLowerCase());
        });
        return [key, safeElements.map(sanitizeElement)];
      }),
  );
}

function sanitizeElement(element) {
  const sanitized = sanitizeDraftValue(element);
  return Object.fromEntries(
    Object.entries(sanitized).map(([key, value]) => [
      key,
      typeof value === 'string' ? htmlToPlainText(value) : value,
    ]),
  );
}

function htmlToPlainText(value) {
  const decoded = value.replace(
    /&(#x[0-9a-f]+|#\d+|amp|apos|gt|lt|nbsp|quot);/gi,
    (match, entity) => {
      const normalized = String(entity).toLowerCase();
      if (normalized.startsWith('#x')) {
        return safeCodePoint(Number.parseInt(normalized.slice(2), 16), match);
      }
      if (normalized.startsWith('#')) {
        return safeCodePoint(Number.parseInt(normalized.slice(1), 10), match);
      }
      return HTML_ENTITY_MAP[normalized] ?? match;
    },
  );
  return decoded
    .replace(/<\s*(script|style)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
    .replace(/<\s*br\s*\/?>/gi, '\n')
    .replace(/<\s*\/\s*(p|div|li|h[1-6])\s*>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function safeCodePoint(value, fallback) {
  if (!Number.isInteger(value) || value < 0 || value > 0x10ffff) return fallback;
  if (value >= 0xd800 && value <= 0xdfff) return fallback;
  return String.fromCodePoint(value);
}

function neutralizeSceneContent(outline, content) {
  if (!content || typeof content !== 'object') return null;
  const sanitized = sanitizeDraftValue(content);
  if (outline.type !== 'quiz') return sanitized;
  const questions = Array.isArray(sanitized.questions)
    ? sanitized.questions.map((question) => ({
        ...question,
        answerAuthority: 'mira_validation_required',
      }))
    : [];
  return { questions };
}

export function buildDraft({ request, generation, contents, elapsedMs }) {
  const outlines = generation.outlines.slice(0, request.skillBoundary.maxScenes);
  return sanitizeDraftValue({
    schemaVersion: OUTPUT_SCHEMA,
    requestId: request.requestId,
    generator: 'openmaic',
    provider: request.provider.name,
    model: request.provider.model,
    elapsedMs,
    draft: {
      status: 'unverified',
      sourceContract: {
        package: '@openmaic/generation',
        version: '0.3.1',
        upstreamCommit: 'aa2bfb3c1d406c47100c6744d90e788abdf1f6d5',
      },
      skillBoundary: request.skillBoundary,
      courseTitle: generation.courseTitle || request.skillBoundary.skillTitle || request.skillBoundary.skillId,
      languageDirective: generation.languageDirective,
      authoritativeAnswersProvided: false,
      scenes: outlines.map((outline, index) => ({
        id: String(outline.id || `${request.requestId}-scene-${index + 1}`),
        type: outline.type,
        order: index + 1,
        title: String(outline.title || '').trim(),
        description: String(outline.description || '').trim(),
        keyPoints: Array.isArray(outline.keyPoints) ? outline.keyPoints.map(String) : [],
        teachingObjective: outline.teachingObjective ? String(outline.teachingObjective) : undefined,
        estimatedDuration: Number.isFinite(outline.estimatedDuration)
          ? Number(outline.estimatedDuration)
          : undefined,
        interactionDraft: neutralizeSceneContent(outline, contents[index]),
      })),
    },
  });
}

export const schemas = { input: INPUT_SCHEMA, output: OUTPUT_SCHEMA };
