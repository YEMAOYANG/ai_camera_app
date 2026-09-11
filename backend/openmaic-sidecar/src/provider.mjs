import { paidBudgetHeaders, beginPaidProviderDispatch } from './paid-budget.mjs';
import { createHash } from 'node:crypto';
import process from 'node:process';
import { ContractError } from './contract.mjs';

export function chatCompletionsUrl(baseUrl) {
  const url = new URL(baseUrl);
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new ContractError('provider.baseUrl must use http or https');
  }
  const normalized = url.toString().replace(/\/$/, '');
  return normalized.endsWith('/chat/completions') ? normalized : `${normalized}/chat/completions`;
}

function isKimiProvider(provider) {
  return provider.name.toLowerCase().includes('kimi') || provider.baseUrl.toLowerCase().includes('moonshot');
}

function isOpenMaicRuntimeProvider(provider) {
  return provider.name === 'openmaic_runtime';
}

async function callOpenMaicRuntimeProvider(
  provider,
  { fetchImpl, questionPhase, requestId, responseJsonSchema, systemPrompt, userPrompt },
) {
  const internalToken = process.env[provider.apiKeyEnv]?.trim();
  if (!internalToken || typeof fetchImpl !== 'function') {
    throw failedSafe('provider_unavailable');
  }
  let endpoint;
  try {
    endpoint = new URL('/api/mira/courseware-provider-call', provider.baseUrl);
  } catch {
    throw failedSafe('question_phase_preflight_rejected');
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), provider.timeoutMs);
  try {
    let response;
    try {
      response = await fetchImpl(endpoint.toString(), {
        method: 'POST',
        signal: controller.signal,
        redirect: 'error',
        headers: {
          'Content-Type': 'application/json',
          'X-Mira-Internal-Token': internalToken,
          ...paidBudgetHeaders(),
          'X-Forwarded-For': '127.0.0.1',
          'X-Forwarded-Host': endpoint.host,
          'X-Forwarded-Port': endpoint.port || (endpoint.protocol === 'https:' ? '443' : '80'),
          'X-Forwarded-Proto': endpoint.protocol.replace(':', ''),
        },
        body: JSON.stringify({
          schemaVersion: 'mira.openmaic.courseware-provider-call.v1',
          requestId,
          phase: questionPhase,
          systemPrompt,
          userPrompt,
          responseJsonSchema,
        }),
      });
    } catch (error) {
      if (error?.name === 'AbortError') throw ambiguous('provider_timeout');
      throw ambiguous('provider_connection_interrupted');
    }
    if (!response || !Number.isInteger(response.status)) {
      throw ambiguous('provider_outcome_unknown');
    }
    if (response.status < 200 || response.status >= 300) {
      if (response.status >= 400 && response.status < 500) {
        throw failedSafe('provider_request_rejected');
      }
      throw ambiguous('provider_outcome_unknown');
    }
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw ambiguous('provider_response_lost');
    }
    const hash = payload?.providerRequestIdHash;
    const content = payload?.content;
    const inputTokens = payload?.inputTokens;
    const outputTokens = payload?.outputTokens;
    const billingEvidence = payload?.billingEvidence;
    if (
      payload?.success !== true ||
      payload?.schemaVersion !== 'mira.openmaic.courseware-provider-call.v1' ||
      payload?.requestId !== requestId ||
      payload?.phase !== questionPhase ||
      typeof content !== 'string' ||
      !content.trim() ||
      typeof hash !== 'string' ||
      !/^[0-9a-f]{64}$/.test(hash) ||
      (![null, undefined].includes(inputTokens) && !Number.isSafeInteger(inputTokens)) ||
      (![null, undefined].includes(outputTokens) && !Number.isSafeInteger(outputTokens)) ||
      !['reported', 'unknown'].includes(billingEvidence)
    ) {
      throw failedSafe('provider_invalid_response');
    }
    return {
      content: content.trim(),
      providerRequestIdHash: hash,
      inputTokens: inputTokens ?? null,
      outputTokens: outputTokens ?? null,
      billingEvidence,
    };
  } finally {
    clearTimeout(timeout);
  }
}

const MFJS_STRING = Object.freeze({ type: 'string' });
const CHOICE_SCHEMA = Object.freeze({
  type: 'object',
  additionalProperties: false,
  required: ['id', 'label'],
  properties: {
    id: MFJS_STRING,
    label: MFJS_STRING,
  },
});
const CHOICES = Object.freeze({
  type: 'array',
  items: CHOICE_SCHEMA,
});
const STRING_LIST = Object.freeze({
  type: 'array',
  items: MFJS_STRING,
});
const QUESTION_ANSWER = Object.freeze({
  anyOf: [MFJS_STRING, STRING_LIST],
});
const QUESTION_SLOT_KEYS = Object.freeze(['q1', 'q2', 'q3', 'q4', 'q5']);
const QUESTION_SLOT_SCHEMA = Object.freeze({
  type: 'object',
  additionalProperties: false,
  required: ['type', 'prompt', 'skill', 'hint', 'explanation', 'answer'],
  properties: {
    type: {
      type: 'string',
      enum: ['numeric', 'single_choice', 'exact_text', 'accepted_text', 'sequence'],
    },
    prompt: MFJS_STRING,
    skill: MFJS_STRING,
    hint: MFJS_STRING,
    explanation: MFJS_STRING,
    answer: QUESTION_ANSWER,
    choices: CHOICES,
    acceptedAnswers: STRING_LIST,
    verificationExpression: MFJS_STRING,
  },
});

const QUESTION_CANDIDATE_RESPONSE_FORMAT = Object.freeze({
  type: 'json_schema',
  json_schema: {
    name: 'mira_question_candidate_v3',
    strict: true,
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['title', 'intro', 'estimatedMinutes', 'teachingFlow', 'questions'],
      properties: {
        title: MFJS_STRING,
        intro: MFJS_STRING,
        estimatedMinutes: { type: 'integer' },
        teachingFlow: {
          type: 'object',
          additionalProperties: false,
          required: ['teach', 'recap'],
          properties: {
            teach: {
              type: 'object',
              additionalProperties: false,
              required: ['title', 'sayText', 'keyPoints'],
              properties: {
                title: MFJS_STRING,
                sayText: MFJS_STRING,
                keyPoints: {
                  type: 'array',
                  items: MFJS_STRING,
                },
              },
            },
            recap: {
              type: 'object',
              additionalProperties: false,
              required: ['sayText'],
              properties: {
                sayText: MFJS_STRING,
              },
            },
          },
        },
        questions: {
          type: 'object',
          additionalProperties: false,
          required: QUESTION_SLOT_KEYS,
          properties: Object.fromEntries(
            QUESTION_SLOT_KEYS.map((key) => [key, QUESTION_SLOT_SCHEMA]),
          ),
        },
      },
    },
  },
});

const QUESTION_OUTLINE_RESPONSE_FORMAT = Object.freeze({
  type: 'json_schema',
  json_schema: {
    name: 'mira_question_outline_v1',
    strict: true,
    schema: {
      type: 'object',
      additionalProperties: false,
      required: ['courseTitle', 'languageDirective', 'outlines'],
      properties: {
        courseTitle: MFJS_STRING,
        languageDirective: MFJS_STRING,
        outlines: {
          type: 'array',
          items: {
            type: 'object',
            additionalProperties: false,
            required: ['title', 'description', 'keyPoints'],
            properties: {
              title: MFJS_STRING,
              description: MFJS_STRING,
              keyPoints: {
                type: 'array',
                items: MFJS_STRING,
              },
            },
          },
        },
      },
    },
  },
});

const INDEPENDENT_VERIFICATION_PHASES = new Set([
  'independent_verification',
  'verification_after_repair',
]);

function schemaObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  return value;
}

function schemaExactKeys(value, expected) {
  if (Object.keys(value).sort().join(',') !== [...expected].sort().join(',')) {
    throw failedSafe('question_phase_preflight_rejected');
  }
}

function schemaRequired(value, expected) {
  if (!Array.isArray(value)
    || value.length !== expected.length
    || value.some((item, index) => item !== expected[index])) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  return [...value];
}

function schemaStringEnum(value, { minimum = 1, maximum = 8, maxLength = 120 } = {}) {
  if (!Array.isArray(value)
    || value.length < minimum
    || value.length > maximum
    || value.some((item) => (
      typeof item !== 'string'
      || !item
      || item !== item.trim()
      || item.length > maxLength
    ))
    || new Set(value).size !== value.length) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  return [...value];
}

function normalizeAnswerSchema(raw) {
  const value = schemaObject(raw);
  if (value.type === 'string') {
    if (Object.hasOwn(value, 'enum')) {
      schemaExactKeys(value, ['type', 'enum']);
      return {
        type: 'string',
        enum: schemaStringEnum(value.enum, { minimum: 2, maximum: 8, maxLength: 80 }),
      };
    }
    schemaExactKeys(value, ['type']);
    return { type: 'string' };
  }
  if (value.type !== 'array') throw failedSafe('question_phase_preflight_rejected');
  schemaExactKeys(value, ['type', 'items']);
  const items = schemaObject(value.items);
  schemaExactKeys(items, ['type', 'enum']);
  if (items.type !== 'string') throw failedSafe('question_phase_preflight_rejected');
  return {
    type: 'array',
    items: {
      type: 'string',
      enum: schemaStringEnum(items.enum, { minimum: 2, maximum: 8, maxLength: 80 }),
    },
  };
}

function normalizeAnswerValueSchema(raw) {
  const value = schemaObject(raw);
  schemaExactKeys(value, ['type', 'additionalProperties', 'required', 'properties']);
  if (value.type !== 'object' || value.additionalProperties !== false) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  const numeric = Array.isArray(value.required) && value.required.length === 2;
  const required = numeric
    ? schemaRequired(value.required, ['answer', 'derivedExpression'])
    : schemaRequired(value.required, ['answer']);
  const properties = schemaObject(value.properties);
  schemaExactKeys(properties, required);
  const normalized = {
    answer: normalizeAnswerSchema(properties.answer),
  };
  if (numeric) {
    const derivedExpression = schemaObject(properties.derivedExpression);
    schemaExactKeys(derivedExpression, ['type']);
    if (derivedExpression.type !== 'string'
      || Object.keys(normalized.answer).length !== 1
      || normalized.answer.type !== 'string') {
      throw failedSafe('question_phase_preflight_rejected');
    }
    normalized.derivedExpression = { type: 'string' };
  }
  return {
    type: 'object',
    additionalProperties: false,
    required,
    properties: normalized,
  };
}

function normalizeIndependentVerificationResponseJsonSchema(raw) {
  const value = schemaObject(raw);
  schemaExactKeys(value, ['type', 'additionalProperties', 'required', 'properties']);
  if (value.type !== 'object' || value.additionalProperties !== false) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  const required = schemaRequired(value.required, ['answers', 'teachingReview']);
  const properties = schemaObject(value.properties);
  schemaExactKeys(properties, required);
  const answers = schemaObject(properties.answers);
  schemaExactKeys(
    answers,
    ['type', 'additionalProperties', 'required', 'properties'],
  );
  if (answers.type !== 'object' || answers.additionalProperties !== false) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  const answerRequired = schemaRequired(answers.required, QUESTION_SLOT_KEYS);
  const answerProperties = schemaObject(answers.properties);
  schemaExactKeys(answerProperties, answerRequired);
  const normalizedAnswerProperties = Object.fromEntries(
    answerRequired.map((questionId) => [
      questionId,
      normalizeAnswerValueSchema(answerProperties[questionId]),
    ]),
  );
  const teachingReview = schemaObject(properties.teachingReview);
  schemaExactKeys(
    teachingReview,
    ['type', 'additionalProperties', 'required', 'properties'],
  );
  if (teachingReview.type !== 'object' || teachingReview.additionalProperties !== false) {
    throw failedSafe('question_phase_preflight_rejected');
  }
  const reviewRequired = schemaRequired(teachingReview.required, ['issues']);
  const reviewProperties = schemaObject(teachingReview.properties);
  schemaExactKeys(reviewProperties, reviewRequired);
  const issues = schemaObject(reviewProperties.issues);
  schemaExactKeys(issues, ['type', 'items']);
  const issueItems = schemaObject(issues.items);
  schemaExactKeys(issueItems, ['type']);
  if (issues.type !== 'array' || issueItems.type !== 'string') {
    throw failedSafe('question_phase_preflight_rejected');
  }
  return {
    type: 'object',
    additionalProperties: false,
    required,
    properties: {
      answers: {
        type: 'object',
        additionalProperties: false,
        required: answerRequired,
        properties: normalizedAnswerProperties,
      },
      teachingReview: {
        type: 'object',
        additionalProperties: false,
        required: reviewRequired,
        properties: {
          issues: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  };
}

function kimiQuestionPhaseResponseFormat(questionPhase, responseJsonSchema) {
  if (questionPhase === 'outline') {
    if (responseJsonSchema != null) throw failedSafe('question_phase_preflight_rejected');
    return QUESTION_OUTLINE_RESPONSE_FORMAT;
  }
  if (questionPhase === 'raw_candidate'
    || questionPhase === 'candidate_repair'
    || questionPhase === 'candidate_repair_retry') {
    if (responseJsonSchema != null) throw failedSafe('question_phase_preflight_rejected');
    return QUESTION_CANDIDATE_RESPONSE_FORMAT;
  }
  if (INDEPENDENT_VERIFICATION_PHASES.has(questionPhase)) {
    return {
      type: 'json_schema',
      json_schema: {
        name: 'mira_question_independent_verification_v3',
        strict: true,
        schema: normalizeIndependentVerificationResponseJsonSchema(responseJsonSchema),
      },
    };
  }
  if (responseJsonSchema != null) throw failedSafe('question_phase_preflight_rejected');
  return { type: 'json_object' };
}

export class QuestionPhaseDispatchError extends Error {
  constructor(outcome, safeErrorCode, metadata = {}) {
    super(safeErrorCode);
    this.name = 'QuestionPhaseDispatchError';
    this.outcome = outcome;
    this.safeErrorCode = safeErrorCode;
    this.providerRequestIdHash = metadata.providerRequestIdHash ?? null;
    this.inputTokens = metadata.inputTokens ?? null;
    this.outputTokens = metadata.outputTokens ?? null;
    this.billingEvidence = metadata.billingEvidence ?? 'unknown';
  }
}

function failedSafe(safeErrorCode, metadata) {
  return new QuestionPhaseDispatchError('failed_safe', safeErrorCode, metadata);
}

function ambiguous(safeErrorCode, metadata) {
  return new QuestionPhaseDispatchError('ambiguous', safeErrorCode, metadata);
}

function requestIdentityHash(value) {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  if (!normalized) return null;
  return createHash('sha256').update(normalized, 'utf8').digest('hex');
}

function responseRequestIdentityHash(response) {
  try {
    return requestIdentityHash(response?.headers?.get?.('msh-request-id'))
      ?? requestIdentityHash(response?.headers?.get?.('x-request-id'));
  } catch {
    throw ambiguous('provider_outcome_unknown');
  }
}

function isNativeUnexpectedRedirect(error) {
  return error instanceof TypeError
    && error.cause
    && typeof error.cause === 'object'
    && error.cause.message === 'unexpected redirect';
}

function normalizedUsage(payload, providerRequestIdHash) {
  const unknown = {
    providerRequestIdHash,
    inputTokens: null,
    outputTokens: null,
    billingEvidence: 'unknown',
  };
  if (!Object.hasOwn(payload, 'usage') || payload.usage == null) return unknown;
  if (typeof payload.usage !== 'object' || Array.isArray(payload.usage)) {
    throw failedSafe('provider_invalid_response', unknown);
  }
  const normalizeTokenCount = (key) => {
    if (!Object.hasOwn(payload.usage, key) || payload.usage[key] == null) return null;
    const value = payload.usage[key];
    if (!Number.isSafeInteger(value) || value < 0) {
      throw failedSafe('provider_invalid_response', unknown);
    }
    return value;
  };
  const inputTokens = normalizeTokenCount('prompt_tokens');
  const outputTokens = normalizeTokenCount('completion_tokens');
  return {
    providerRequestIdHash,
    inputTokens,
    outputTokens,
    billingEvidence: inputTokens != null || outputTokens != null ? 'reported' : 'unknown',
  };
}

function parseKimiStreamingPayload(rawBody, responseMetadata) {
  const lines = String(rawBody ?? '').split(/\r?\n/);
  const hasTerminalDone = lines.some((rawLine) => rawLine.trim() === 'data: [DONE]');
  if (!hasTerminalDone) {
    throw ambiguous('provider_response_lost', responseMetadata);
  }
  let done = false;
  let sawData = false;
  let terminalReason = null;
  let providerId = null;
  let usage = null;
  let content = '';

  const evidence = () => normalizedUsage(
    usage == null ? {} : { usage },
    responseMetadata.providerRequestIdHash ?? requestIdentityHash(providerId),
  );

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith(':')) continue;
    if (!line.startsWith('data:')) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    const data = line.slice('data:'.length).trim();
    if (done) throw failedSafe('provider_invalid_response', evidence());
    if (data === '[DONE]') {
      done = true;
      continue;
    }
    let chunk;
    try {
      chunk = JSON.parse(data);
    } catch {
      throw failedSafe('provider_invalid_response', evidence());
    }
    if (!chunk || typeof chunk !== 'object' || Array.isArray(chunk)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    sawData = true;
    if (Object.hasOwn(chunk, 'id') && chunk.id != null) {
      if (typeof chunk.id !== 'string' || !chunk.id.trim()) {
        throw failedSafe('provider_invalid_response', evidence());
      }
      const normalizedId = chunk.id.trim();
      if (providerId != null && providerId !== normalizedId) {
        throw failedSafe('provider_invalid_response', evidence());
      }
      providerId = normalizedId;
    }
    if (Object.hasOwn(chunk, 'usage') && chunk.usage != null) {
      if (usage != null && JSON.stringify(usage) !== JSON.stringify(chunk.usage)) {
        throw failedSafe('provider_invalid_response', evidence());
      }
      usage = chunk.usage;
    }
    if (!Array.isArray(chunk.choices)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    if (chunk.choices.length === 0) continue;
    if (chunk.choices.length !== 1) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    const choice = chunk.choices[0];
    if (!choice || typeof choice !== 'object' || Array.isArray(choice)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    if (Object.hasOwn(choice, 'index') && choice.index !== 0) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    if (Object.hasOwn(choice, 'usage') && choice.usage != null) {
      if (usage != null && JSON.stringify(usage) !== JSON.stringify(choice.usage)) {
        throw failedSafe('provider_invalid_response', evidence());
      }
      usage = choice.usage;
    }
    const delta = choice.delta;
    if (!delta || typeof delta !== 'object' || Array.isArray(delta)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    const deltaContent = delta.content;
    if (deltaContent != null && typeof deltaContent !== 'string') {
      throw failedSafe('provider_invalid_response', evidence());
    }
    const finishReason = choice.finish_reason;
    if (finishReason != null && (typeof finishReason !== 'string' || !finishReason)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    if (terminalReason != null && ((deltaContent ?? '') || finishReason != null)) {
      throw failedSafe('provider_invalid_response', evidence());
    }
    content += deltaContent ?? '';
    if (finishReason != null) terminalReason = finishReason;
  }

  if (!done) throw ambiguous('provider_response_lost', evidence());
  if (!sawData || terminalReason == null) {
    throw failedSafe('provider_invalid_response', evidence());
  }
  if (terminalReason !== 'stop') {
    throw failedSafe('provider_no_candidate', evidence());
  }
  return {
    ...(providerId == null ? {} : { id: providerId }),
    choices: [{ message: { content } }],
    ...(usage == null ? {} : { usage }),
  };
}

function singleDispatchEndpoint(provider, fetchImpl) {
  if (typeof fetchImpl !== 'function') throw failedSafe('provider_unavailable');
  const apiKey = process.env[provider.apiKeyEnv]?.trim();
  if (!apiKey) throw failedSafe('provider_unavailable');
  let endpoint;
  try {
    endpoint = chatCompletionsUrl(provider.baseUrl);
  } catch {
    throw failedSafe('question_phase_preflight_rejected');
  }
  return { apiKey, endpoint };
}

export function createSingleDispatchAICall(
  provider,
  {
    fetchImpl = globalThis.fetch,
    questionPhase = null,
    requestId = null,
    responseJsonSchema = null,
  } = {},
) {
  const questionPhaseResponseFormat = kimiQuestionPhaseResponseFormat(
    questionPhase,
    responseJsonSchema,
  );
  let invoked = false;
  return async (systemPrompt, userPrompt, images = []) => {
    if (invoked) throw failedSafe('question_phase_preflight_rejected');
    invoked = true;
    if (!Array.isArray(images) || images.length) {
      throw failedSafe('question_phase_preflight_rejected');
    }
    if (isOpenMaicRuntimeProvider(provider)) {
      if (typeof requestId !== 'string' || !requestId.trim()) {
        throw failedSafe('question_phase_preflight_rejected');
      }
      return callOpenMaicRuntimeProvider(
        provider,
        {
          fetchImpl,
          questionPhase,
          requestId: requestId.trim(),
          responseJsonSchema: (
            questionPhaseResponseFormat.type === 'json_schema'
              ? questionPhaseResponseFormat.json_schema.schema
              : null
          ),
          systemPrompt,
          userPrompt,
        },
      );
    }
    const { apiKey, endpoint } = singleDispatchEndpoint(provider, fetchImpl);
    const requestBody = {
      model: provider.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: provider.temperature,
      max_tokens: provider.maxTokens,
    };
    if (isKimiProvider(provider)) {
      delete requestBody.max_tokens;
      requestBody.max_completion_tokens = provider.maxTokens;
      requestBody.thinking = { type: 'disabled' };
      requestBody.response_format = questionPhaseResponseFormat;
      requestBody.stream = true;
      requestBody.stream_options = { include_usage: true };
    }
    let budget;
    try { budget = await beginPaidProviderDispatch(provider, requestBody, requestId, fetchImpl); }
    catch { throw failedSafe('provider_unavailable'); }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), provider.timeoutMs);
    try {
      let response;
      try {
        response = await fetchImpl(endpoint, {
          method: 'POST',
          signal: controller.signal,
          redirect: 'error',
          headers: {
            Authorization: `Bearer ${apiKey}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
        });
      } catch (error) {
        if (error?.name === 'AbortError') throw ambiguous('provider_timeout');
        if (isNativeUnexpectedRedirect(error)) {
          throw ambiguous('provider_outcome_unknown');
        }
        throw ambiguous('provider_connection_interrupted');
      }

      const providerRequestIdHash = responseRequestIdentityHash(response);
      const responseMetadata = {
        providerRequestIdHash,
        inputTokens: null,
        outputTokens: null,
        billingEvidence: 'unknown',
      };
      if (!response || !Number.isInteger(response.status)) {
        throw ambiguous('provider_outcome_unknown', responseMetadata);
      }
      if (response.status < 200 || response.status >= 300) {
        if (response.status === 408) {
          throw ambiguous('provider_timeout', responseMetadata);
        }
        if (response.status >= 400 && response.status < 500) {
          throw failedSafe('provider_request_rejected', responseMetadata);
        }
        throw ambiguous('provider_outcome_unknown', responseMetadata);
      }

      let rawBody;
      try {
        if (typeof response.text !== 'function') {
          throw new TypeError('response body reader unavailable');
        }
        rawBody = await response.text();
      } catch (error) {
        if (error?.name === 'AbortError') {
          throw ambiguous('provider_timeout', responseMetadata);
        }
        throw ambiguous('provider_response_lost', responseMetadata);
      }
      let payload;
      if (isKimiProvider(provider)) {
        payload = parseKimiStreamingPayload(rawBody, responseMetadata);
      } else {
        try {
          payload = JSON.parse(rawBody);
        } catch {
          throw failedSafe('provider_invalid_response', responseMetadata);
        }
      }
      if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw failedSafe('provider_invalid_response', responseMetadata);
      }
      if (Object.hasOwn(payload, 'id') && payload.id != null && typeof payload.id !== 'string') {
        throw failedSafe('provider_invalid_response', responseMetadata);
      }
      const successfulRequestIdHash = providerRequestIdHash ?? requestIdentityHash(payload.id);
      const usage = normalizedUsage(payload, successfulRequestIdHash);
      await budget?.settle(usage);
      const content = payload?.choices?.[0]?.message?.content;
      if (typeof content !== 'string' || !content.trim()) {
        throw failedSafe('provider_no_candidate', usage);
      }
      return { content: content.trim(), ...usage };
    } finally {
      await budget?.unknown();
      clearTimeout(timeout);
    }
  };
}

export function createLiveAICall(provider, { fetchImpl = globalThis.fetch } = {}) {
  const apiKey = process.env[provider.apiKeyEnv]?.trim();
  if (!apiKey) {
    throw new ContractError(
      `AI API key environment variable ${provider.apiKeyEnv} is not configured`,
      'openmaic_unavailable',
    );
  }
  if (typeof fetchImpl !== 'function') {
    throw new ContractError('Node.js fetch API is unavailable', 'openmaic_unavailable');
  }
  const endpoint = chatCompletionsUrl(provider.baseUrl);
  return async (systemPrompt, userPrompt, images = []) => {
    if (images.length) {
      throw new ContractError('this OpenMAIC sidecar accepts text-only generation', 'generation_failed');
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), provider.timeoutMs);
    const requestBody = {
      model: provider.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: provider.temperature,
      max_tokens: provider.maxTokens,
    };
    // Kimi K2 thinking can consume the output budget and return empty content.
    // Mira's existing Kimi gateway uses this same explicit non-thinking mode;
    // Moonshot requires temperature 0.6 for that request shape.
    if (isKimiProvider(provider)) {
      delete requestBody.max_tokens;
      requestBody.max_completion_tokens = provider.maxTokens;
      requestBody.thinking = { type: 'disabled' };
      requestBody.temperature = 0.6;
      requestBody.response_format = { type: 'json_object' };
    }
    const budget = await beginPaidProviderDispatch(provider, requestBody, null, fetchImpl);
    try {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 300);
        throw new Error(`OpenAI-compatible API returned HTTP ${response.status}: ${detail}`);
      }
      const payload = await response.json();
      await budget?.settle(normalizedUsage(payload, responseRequestIdentityHash(response) ?? requestIdentityHash(payload.id)));
      const content = payload?.choices?.[0]?.message?.content;
      if (typeof content !== 'string' || !content.trim()) {
        throw new Error('OpenAI-compatible API returned no message content');
      }
      return content;
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new Error(`OpenAI-compatible API timed out after ${provider.timeoutMs}ms`);
      }
      throw error;
    } finally {
      await budget?.unknown();
      clearTimeout(timeout);
    }
  };
}
