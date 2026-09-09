import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';
import * as providerModule from '../src/provider.mjs';

const { createLiveAICall } = providerModule;

function v2Provider(overrides = {}) {
  return {
    name: 'kimi',
    model: 'kimi-k2.6',
    baseUrl: 'https://api.moonshot.cn/v1',
    apiKeyEnv: 'TEST_KIMI_KEY',
    timeoutMs: 1000,
    maxTokens: 6000,
    temperature: 0.2,
    ...overrides,
  };
}

function verificationResponseJsonSchema() {
  const scalar = (answer = { type: 'string' }) => ({
    type: 'object',
    additionalProperties: false,
    required: ['answer'],
    properties: { answer },
  });
  return {
    type: 'object',
    additionalProperties: false,
    required: ['answers', 'teachingReview'],
    properties: {
      answers: {
        type: 'object',
        additionalProperties: false,
        required: ['q1', 'q2', 'q3', 'q4', 'q5'],
        properties: {
          q1: {
            type: 'object',
            additionalProperties: false,
            required: ['answer', 'derivedExpression'],
            properties: {
              answer: { type: 'string' },
              derivedExpression: { type: 'string' },
            },
          },
          q2: scalar({ type: 'string', enum: ['A', 'B'] }),
          q3: scalar(),
          q4: scalar(),
          q5: scalar({
              type: 'array',
              items: { type: 'string', enum: ['first', 'second'] },
          }),
        },
      },
      teachingReview: {
        type: 'object',
        additionalProperties: false,
        required: ['issues'],
        properties: {
          issues: { type: 'array', items: { type: 'string' } },
        },
      },
    },
  };
}

function response({
  status = 200,
  payload,
  text,
  requestId = null,
  moonshotRequestId = null,
  onRead = null,
}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name) {
        if (name.toLowerCase() === 'msh-request-id') return moonshotRequestId;
        return name.toLowerCase() === 'x-request-id' ? requestId : null;
      },
    },
    async text() {
      onRead?.();
      if (text instanceof Error) throw text;
      return text ?? JSON.stringify(payload);
    },
  };
}

function kimiStreamResponse({
  id = null,
  content = '{}',
  finishReason = 'stop',
  usage,
  choiceUsage,
  requestId = null,
  moonshotRequestId = null,
}) {
  const chunk = {
    ...(id == null ? {} : { id }),
    choices: [{
      index: 0,
      delta: { content },
      finish_reason: finishReason,
      ...(choiceUsage === undefined ? {} : { usage: choiceUsage }),
    }],
    ...(usage === undefined ? {} : { usage }),
  };
  return response({
    text: [`data: ${JSON.stringify(chunk)}`, '', 'data: [DONE]', ''].join('\n'),
    requestId,
    moonshotRequestId,
  });
}

async function captureRejection(operation) {
  try {
    await operation();
  } catch (error) {
    return error;
  }
  assert.fail('operation must reject');
}

test('Kimi payload disables thinking and never embeds the key in its JSON body', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'secret-from-environment';
  let captured;
  const fetchImpl = async (url, options) => {
    captured = { url, options };
    return {
      ok: true,
      async json() {
        return { choices: [{ message: { content: '{"ok":true}' } }] };
      },
    };
  };
  try {
    const call = createLiveAICall(
      {
        name: 'kimi',
        model: 'kimi-k2.6',
        baseUrl: 'https://api.moonshot.cn/v1',
        apiKeyEnv: 'TEST_KIMI_KEY',
        timeoutMs: 1000,
        maxTokens: 6000,
        temperature: 0.2,
      },
      { fetchImpl },
    );
    assert.equal(await call('system', 'user'), '{"ok":true}');
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }

  const body = JSON.parse(captured.options.body);
  assert.deepEqual(body.thinking, { type: 'disabled' });
  assert.deepEqual(body.response_format, { type: 'json_object' });
  assert.equal(body.max_completion_tokens, 6000);
  assert.equal(Object.hasOwn(body, 'max_tokens'), false);
  assert.equal(body.temperature, 0.6);
  assert.equal(body.model, 'kimi-k2.6');
  assert.equal(captured.options.headers.Authorization, 'Bearer secret-from-environment');
  assert.equal(captured.options.body.includes('secret-from-environment'), false);
});

test('V2 single dispatch preserves the canonical temperature and rejects a second call before fetch', async () => {
  assert.equal(typeof providerModule.createSingleDispatchAICall, 'function');
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'single-dispatch-secret';
  let fetchCalls = 0;
  let captured;
  const rawCompletionId = '  completion-123  ';
  const rawRequestId = 'msh-request-123';
  const expectedHash = createHash('sha256')
    .update(rawRequestId, 'utf8')
    .digest('hex');
  try {
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async (url, options) => {
        fetchCalls += 1;
        captured = { url, options };
        return kimiStreamResponse({
          id: rawCompletionId,
          content: '{"phaseStatus":"accepted"}',
          usage: { prompt_tokens: 0 },
          requestId: 'x-request-must-not-win',
          moonshotRequestId: rawRequestId,
        });
      },
    });
    const result = await call('safe system', 'safe user');
    assert.deepEqual(result, {
      content: '{"phaseStatus":"accepted"}',
      providerRequestIdHash: expectedHash,
      inputTokens: 0,
      outputTokens: null,
      billingEvidence: 'reported',
    });
    const secondError = await captureRejection(() => call('again', 'again'));
    assert.equal(secondError.outcome, 'failed_safe');
    assert.equal(secondError.safeErrorCode, 'question_phase_preflight_rejected');
    assert.equal(fetchCalls, 1);
    const disclosed = JSON.stringify(result);
    assert.equal(disclosed.includes(rawRequestId), false);
    assert.equal(disclosed.includes(rawCompletionId.trim()), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }

  assert.equal(captured.options.redirect, 'error');
  const body = JSON.parse(captured.options.body);
  assert.deepEqual(body.thinking, { type: 'disabled' });
  assert.deepEqual(body.response_format, { type: 'json_object' });
  assert.equal(body.max_completion_tokens, 6000);
  assert.equal(Object.hasOwn(body, 'max_tokens'), false);
  assert.equal(body.temperature, 0.2);
  assert.equal(body.model, 'kimi-k2.6');
  assert.equal(body.stream, true);
  assert.deepEqual(body.stream_options, { include_usage: true });
  assert.equal(captured.options.body.includes('single-dispatch-secret'), false);
});

test('learning courseware v2 dispatch uses only the private OpenMAIC boundary', async () => {
  const previousInternal = process.env.TEST_OPENMAIC_INTERNAL_TOKEN;
  const previousKimi = process.env.TEST_KIMI_KEY;
  const previousDeepSeek = process.env.TEST_DEEPSEEK_KEY;
  process.env.TEST_OPENMAIC_INTERNAL_TOKEN = 'private-openmaic-token';
  process.env.TEST_KIMI_KEY = 'camera-kimi-key-must-not-cross';
  process.env.TEST_DEEPSEEK_KEY = 'openmaic-deepseek-key-must-not-cross';
  let captured;
  let fetchCalls = 0;
  const requestId = 'grade-primary_1-course-1-outline-attempt-1';
  const receiptHash = createHash('sha256').update('openmaic-receipt').digest('hex');
  try {
    const call = providerModule.createSingleDispatchAICall(
      {
        name: 'openmaic_runtime',
        model: 'courseware-v2',
        baseUrl: 'http://127.0.0.1:3100',
        apiKeyEnv: 'TEST_OPENMAIC_INTERNAL_TOKEN',
        timeoutMs: 300_000,
        maxTokens: 8_000,
        temperature: 0.6,
      },
      {
        questionPhase: 'outline',
        requestId,
        fetchImpl: async (url, options) => {
          fetchCalls += 1;
          captured = { url, options };
          return {
            status: 200,
            async json() {
              return {
                success: true,
                schemaVersion: 'mira.openmaic.courseware-provider-call.v1',
                requestId,
                phase: 'outline',
                content: '{"phaseStatus":"accepted"}',
                providerRequestIdHash: receiptHash,
                inputTokens: 15,
                outputTokens: 9,
                billingEvidence: 'reported',
              };
            },
          };
        },
      },
    );
    assert.deepEqual(await call('courseware system', 'courseware user'), {
      content: '{"phaseStatus":"accepted"}',
      providerRequestIdHash: receiptHash,
      inputTokens: 15,
      outputTokens: 9,
      billingEvidence: 'reported',
    });
  } finally {
    if (previousInternal === undefined) delete process.env.TEST_OPENMAIC_INTERNAL_TOKEN;
    else process.env.TEST_OPENMAIC_INTERNAL_TOKEN = previousInternal;
    if (previousKimi === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previousKimi;
    if (previousDeepSeek === undefined) delete process.env.TEST_DEEPSEEK_KEY;
    else process.env.TEST_DEEPSEEK_KEY = previousDeepSeek;
  }

  assert.equal(fetchCalls, 1);
  assert.equal(captured.url, 'http://127.0.0.1:3100/api/mira/courseware-provider-call');
  assert.equal(captured.options.headers['X-Mira-Internal-Token'], 'private-openmaic-token');
  assert.equal(Object.hasOwn(captured.options.headers, 'Authorization'), false);
  assert.equal(captured.options.body.includes('camera-kimi-key-must-not-cross'), false);
  assert.equal(captured.options.body.includes('openmaic-deepseek-key-must-not-cross'), false);
  const body = JSON.parse(captured.options.body);
  assert.equal(body.requestId, requestId);
  assert.equal(body.phase, 'outline');
  assert.equal(body.responseJsonSchema.type, 'object');
  assert.equal(body.responseJsonSchema.additionalProperties, false);
});

test('V2 Kimi streaming response reconstructs one content result with exact usage evidence', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'streaming-secret';
  const providerId = 'cmpl-streaming-123';
  const body = [
    `data: ${JSON.stringify({
      id: providerId,
      object: 'chat.completion.chunk',
      choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }],
    })}`,
    '',
    `data: ${JSON.stringify({
      id: providerId,
      object: 'chat.completion.chunk',
      choices: [{ index: 0, delta: { content: '{"phase' }, finish_reason: null }],
    })}`,
    '',
    `data: ${JSON.stringify({
      id: providerId,
      object: 'chat.completion.chunk',
      choices: [{ index: 0, delta: { content: 'Status":"accepted"}' }, finish_reason: 'stop' }],
      usage: { prompt_tokens: 11, completion_tokens: 7, total_tokens: 18 },
    })}`,
    '',
    'data: [DONE]',
    '',
  ].join('\n');
  try {
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => response({ text: body }),
    });

    assert.deepEqual(await call('system', 'user'), {
      content: '{"phaseStatus":"accepted"}',
      providerRequestIdHash: createHash('sha256').update(providerId, 'utf8').digest('hex'),
      inputTokens: 11,
      outputTokens: 7,
      billingEvidence: 'reported',
    });
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi truncated streaming response is ambiguous and never inferred as complete', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'truncated-stream-secret';
  const raw = [
    `data: ${JSON.stringify({
      id: 'cmpl-truncated-secret',
      choices: [{ index: 0, delta: { content: '{"partial":' }, finish_reason: null }],
    })}`,
    '',
  ].join('\n');
  try {
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => response({ text: raw }),
    });
    const error = await captureRejection(() => call('system', 'user'));
    assert.equal(error.outcome, 'ambiguous');
    assert.equal(error.safeErrorCode, 'provider_response_lost');
    assert.equal(`${String(error)} ${JSON.stringify(error)}`.includes('cmpl-truncated-secret'), false);
    assert.equal(`${String(error)} ${JSON.stringify(error)}`.includes('truncated-stream-secret'), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi mid-JSON or empty SSE clean EOF is ambiguous response loss', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'clean-eof-secret';
  const cases = [
    '',
    '   \n\t',
    ': keep-alive without terminal evidence\n\n',
    '{"id":"cmpl-plain-partial-secret","choices":[',
    JSON.stringify({
      id: 'cmpl-plain-json-secret',
      choices: [{ message: { content: '{"phaseStatus":"accepted"}' } }],
      usage: { prompt_tokens: 5, completion_tokens: 2 },
    }),
    'data: {"id":"cmpl-mid-json-secret","choices":[',
    'data:\n\n',
    [
      `data: ${JSON.stringify({
        id: 'cmpl-terminal-without-done-secret',
        choices: [{
          index: 0,
          delta: { content: '{"phaseStatus":"accepted"}' },
          finish_reason: 'stop',
        }],
      })}`,
      '',
    ].join('\n'),
  ];
  try {
    for (const raw of cases) {
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        fetchImpl: async () => response({ text: raw }),
      });
      const error = await captureRejection(() => call('system', 'user'));
      assert.equal(error.outcome, 'ambiguous');
      assert.equal(error.safeErrorCode, 'provider_response_lost');
      const disclosed = `${String(error)} ${JSON.stringify(error)}`;
      assert.equal(disclosed.includes('cmpl-mid-json-secret'), false);
      assert.equal(disclosed.includes('cmpl-terminal-without-done-secret'), false);
      assert.equal(disclosed.includes('cmpl-plain-partial-secret'), false);
      assert.equal(disclosed.includes('cmpl-plain-json-secret'), false);
      assert.equal(disclosed.includes('clean-eof-secret'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi streaming accepts usage evidence on the terminal choice variant', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'choice-usage-secret';
  const raw = [
    `data: ${JSON.stringify({
      id: 'cmpl-choice-usage',
      choices: [{
        index: 0,
        delta: { content: '{}' },
        finish_reason: 'stop',
        usage: { prompt_tokens: 3, completion_tokens: 2, total_tokens: 5 },
      }],
    })}`,
    '',
    'data: [DONE]',
    '',
  ].join('\n');
  try {
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => response({ text: raw }),
    });
    const result = await call('system', 'user');
    assert.equal(result.inputTokens, 3);
    assert.equal(result.outputTokens, 2);
    assert.equal(result.billingEvidence, 'reported');
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi candidate phases use one fixed MFJS-safe strict candidate JSON schema', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'structured-output-secret';
  try {
    for (const questionPhase of ['raw_candidate', 'candidate_repair', 'candidate_repair_retry']) {
      let captured;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        questionPhase,
        fetchImpl: async (_url, options) => {
          captured = options;
          return kimiStreamResponse({
            content: '{"title":"RAW_PROVIDER_RESULT"}',
          });
        },
      });
      await call('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA', 'USER_INPUT_MUST_NOT_ENTER_SCHEMA');

      const body = JSON.parse(captured.body);
      assert.equal(body.response_format.type, 'json_schema');
      assert.equal(body.response_format.json_schema.strict, true);
      assert.equal(body.response_format.json_schema.name, 'mira_question_candidate_v3');
      const schema = body.response_format.json_schema.schema;
      assert.deepEqual(schema.required, [
        'title',
        'intro',
        'estimatedMinutes',
        'teachingFlow',
        'questions',
      ]);
      assert.equal(schema.additionalProperties, false);
      const questions = schema.properties.questions;
      assert.equal(questions.type, 'object');
      assert.equal(questions.additionalProperties, false);
      assert.deepEqual(questions.required, ['q1', 'q2', 'q3', 'q4', 'q5']);
      assert.deepEqual(Object.keys(questions.properties), ['q1', 'q2', 'q3', 'q4', 'q5']);
      for (const slot of Object.values(questions.properties)) {
        assert.equal(slot.type, 'object');
        assert.equal(slot.additionalProperties, false);
        assert.deepEqual(slot.properties.type.enum, [
          'numeric',
          'single_choice',
          'exact_text',
          'accepted_text',
          'sequence',
        ]);
        assert.deepEqual(slot.properties.answer.anyOf, [
          { type: 'string' },
          { type: 'array', items: { type: 'string' } },
        ]);
      }
      const serializedFormat = JSON.stringify(body.response_format);
      for (const keyword of [
        'oneOf',
        'minItems',
        'maxItems',
        'minLength',
        'maxLength',
        'pattern',
        'minimum',
        'maximum',
      ]) {
        assert.equal(serializedFormat.includes(`"${keyword}"`), false);
      }
      assert.equal(serializedFormat.includes('structured-output-secret'), false);
      assert.equal(serializedFormat.includes('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA'), false);
      assert.equal(serializedFormat.includes('USER_INPUT_MUST_NOT_ENTER_SCHEMA'), false);
      assert.equal(captured.body.includes('structured-output-secret'), false);
      assert.equal(captured.body.includes('RAW_PROVIDER_RESULT'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi outline uses one fixed MFJS-safe strict JSON schema', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'outline-structured-output-secret';
  try {
    let captured;
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      questionPhase: 'outline',
      fetchImpl: async (_url, options) => {
        captured = options;
        return kimiStreamResponse({
          content: '{"courseTitle":"课程"}',
        });
      },
    });
    await call('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA', 'USER_INPUT_MUST_NOT_ENTER_SCHEMA');

    const body = JSON.parse(captured.body);
    assert.equal(body.response_format.type, 'json_schema');
    assert.equal(body.response_format.json_schema.strict, true);
    assert.equal(body.response_format.json_schema.name, 'mira_question_outline_v1');
    const schema = body.response_format.json_schema.schema;
    assert.deepEqual(schema.required, ['courseTitle', 'languageDirective', 'outlines']);
    assert.equal(schema.additionalProperties, false);
    assert.equal(schema.properties.outlines.type, 'array');
    assert.deepEqual(schema.properties.outlines.items.required, [
      'title', 'description', 'keyPoints',
    ]);
    assert.equal(schema.properties.outlines.items.additionalProperties, false);
    assert.equal(JSON.stringify(body.response_format).includes('outline-structured-output-secret'), false);
    assert.equal(JSON.stringify(body.response_format).includes('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA'), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi independent verification phases use the fixed-slot MFJS schema', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'verification-structured-output-secret';
  try {
    for (const questionPhase of ['independent_verification', 'verification_after_repair']) {
      let captured;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        questionPhase,
        responseJsonSchema: verificationResponseJsonSchema(),
        fetchImpl: async (_url, options) => {
          captured = options;
          return kimiStreamResponse({
            content: '{"answers":[],"teachingReview":{}}',
          });
        },
      });
      await call('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA', 'USER_INPUT_MUST_NOT_ENTER_SCHEMA');

      const body = JSON.parse(captured.body);
      assert.equal(body.response_format.type, 'json_schema');
      assert.equal(body.response_format.json_schema.strict, true);
      assert.equal(
        body.response_format.json_schema.name,
        'mira_question_independent_verification_v3',
      );
      const schema = body.response_format.json_schema.schema;
      assert.equal(schema.type, 'object');
      assert.equal(schema.additionalProperties, false);
      assert.deepEqual(schema.required, ['answers', 'teachingReview']);
      const answers = schema.properties.answers;
      assert.equal(answers.type, 'object');
      assert.equal(answers.additionalProperties, false);
      assert.deepEqual(answers.required, ['q1', 'q2', 'q3', 'q4', 'q5']);
      assert.deepEqual(answers.properties.q1.required, ['answer', 'derivedExpression']);
      assert.deepEqual(answers.properties.q2.properties.answer.enum, ['A', 'B']);
      assert.deepEqual(answers.properties.q3.required, ['answer']);
      assert.equal(answers.properties.q3.properties.answer.type, 'string');
      assert.deepEqual(answers.properties.q5.required, ['answer']);
      assert.equal(answers.properties.q5.properties.answer.type, 'array');
      assert.equal(answers.properties.q5.properties.answer.items.type, 'string');
      assert.equal(
        Object.values(answers.properties).every(
          (branch) => branch.additionalProperties === false,
        ),
        true,
      );
      const review = schema.properties.teachingReview;
      assert.equal(review.additionalProperties, false);
      assert.deepEqual(review.required, ['issues']);
      assert.deepEqual(Object.keys(review.properties), ['issues']);
      assert.equal(review.properties.issues.items.type, 'string');
      const serializedFormat = JSON.stringify(body.response_format);
      for (const keyword of [
        'oneOf',
        'minItems',
        'maxItems',
        'minLength',
        'maxLength',
        'pattern',
        'minimum',
        'maximum',
      ]) {
        assert.equal(serializedFormat.includes(`"${keyword}"`), false);
      }
      assert.equal(serializedFormat.includes('verification-structured-output-secret'), false);
      assert.equal(serializedFormat.includes('SYSTEM_INPUT_MUST_NOT_ENTER_SCHEMA'), false);
      assert.equal(serializedFormat.includes('USER_INPUT_MUST_NOT_ENTER_SCHEMA'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 responseJsonSchema is required only for verification phases and rejects malformed input', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'schema-preflight-secret';
  let fetchCalls = 0;
  const fetchImpl = async () => {
    fetchCalls += 1;
    return response({ payload: { choices: [{ message: { content: '{}' } }] } });
  };
  try {
    for (const options of [
      { questionPhase: 'outline', responseJsonSchema: verificationResponseJsonSchema() },
      { questionPhase: 'independent_verification' },
      {
        questionPhase: 'verification_after_repair',
        responseJsonSchema: { ...verificationResponseJsonSchema(), prompt: 'forbidden' },
      },
    ]) {
      const error = await captureRejection(async () => {
        const call = providerModule.createSingleDispatchAICall(v2Provider(), {
          ...options,
          fetchImpl,
        });
        return call('system', 'user');
      });
      assert.equal(error.outcome, 'failed_safe');
      assert.equal(error.safeErrorCode, 'question_phase_preflight_rejected');
    }
    assert.equal(fetchCalls, 0);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Kimi phases outside structured generation keep json_object response format', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'phase-scope-secret';
  try {
    for (const questionPhase of ['lesson_text', 'reconciliation']) {
      let captured;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        questionPhase,
        fetchImpl: async (_url, options) => {
          captured = options;
          return kimiStreamResponse({ content: '{}' });
        },
      });
      await call('system', 'user');
      assert.deepEqual(JSON.parse(captured.body).response_format, { type: 'json_object' });
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 explicit HTTP outcomes are terminal, never replayed, and preserve only a request-id hash', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'http-matrix-secret';
  const cases = [
    { status: 302, outcome: 'ambiguous', code: 'provider_outcome_unknown' },
    { status: 429, outcome: 'failed_safe', code: 'provider_request_rejected' },
    { status: 408, outcome: 'ambiguous', code: 'provider_timeout' },
    { status: 503, outcome: 'ambiguous', code: 'provider_outcome_unknown' },
  ];
  try {
    for (const item of cases) {
      let fetchCalls = 0;
      let bodyReads = 0;
      const rawRequestId = `raw-${item.status}-secret`;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        fetchImpl: async () => {
          fetchCalls += 1;
          return response({
            status: item.status,
            text: 'RAW_PROVIDER_BODY_MUST_NOT_BE_READ',
            requestId: rawRequestId,
            onRead: () => { bodyReads += 1; },
          });
        },
      });
      const error = await captureRejection(() => call('system secret', 'prompt secret'));
      assert.equal(error.outcome, item.outcome);
      assert.equal(error.safeErrorCode, item.code);
      assert.equal(
        error.providerRequestIdHash,
        createHash('sha256').update(rawRequestId, 'utf8').digest('hex'),
      );
      assert.equal(fetchCalls, 1);
      assert.equal(bodyReads, 0);
      const disclosed = `${String(error)} ${JSON.stringify(error)}`;
      assert.equal(disclosed.includes(rawRequestId), false);
      assert.equal(disclosed.includes('RAW_PROVIDER_BODY'), false);
      assert.equal(disclosed.includes('system secret'), false);
      assert.equal(disclosed.includes('prompt secret'), false);
      assert.equal(disclosed.includes('http-matrix-secret'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 Moonshot error responses hash Msh-Request-Id without exposing the raw trace id', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'moonshot-header-secret';
  const rawRequestId = 'msh-sensitive-trace-123';
  try {
    const call = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => response({
        status: 503,
        text: 'RAW_PROVIDER_BODY_MUST_NOT_BE_READ',
        moonshotRequestId: rawRequestId,
      }),
    });
    const error = await captureRejection(() => call('system', 'user'));
    assert.equal(error.outcome, 'ambiguous');
    assert.equal(error.safeErrorCode, 'provider_outcome_unknown');
    assert.equal(
      error.providerRequestIdHash,
      createHash('sha256').update(rawRequestId, 'utf8').digest('hex'),
    );
    const disclosed = `${String(error)} ${JSON.stringify(error)}`;
    assert.equal(disclosed.includes(rawRequestId), false);
    assert.equal(disclosed.includes('RAW_PROVIDER_BODY'), false);
    assert.equal(disclosed.includes('moonshot-header-secret'), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 timeout, connection, and body-read loss are ambiguous with one fetch and no raw disclosure', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'transport-secret';
  const abortError = new Error('RAW_ABORT_DETAIL');
  abortError.name = 'AbortError';
  const cases = [
    {
      fetchImpl: async () => { throw abortError; },
      code: 'provider_timeout',
    },
    {
      fetchImpl: async () => { throw new TypeError('RAW_CONNECTION_DETAIL'); },
      code: 'provider_connection_interrupted',
    },
    {
      fetchImpl: async () => response({
        text: new Error('RAW_BODY_READ_DETAIL'),
        requestId: 'body-read-request-id',
      }),
      code: 'provider_response_lost',
    },
  ];
  try {
    for (const item of cases) {
      let fetchCalls = 0;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        fetchImpl: async (...args) => {
          fetchCalls += 1;
          return item.fetchImpl(...args);
        },
      });
      const error = await captureRejection(() => call('system', 'user'));
      assert.equal(error.outcome, 'ambiguous');
      assert.equal(error.safeErrorCode, item.code);
      assert.equal(fetchCalls, 1);
      const disclosed = `${String(error)} ${JSON.stringify(error)}`;
      assert.equal(disclosed.includes('RAW_'), false);
      assert.equal(disclosed.includes('transport-secret'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 native redirect rejection is outcome-unknown while an ordinary TypeError remains connection-interrupted', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'redirect-transport-secret';
  const nativeRedirectError = new TypeError('fetch failed');
  nativeRedirectError.cause = new Error('unexpected redirect');
  const cases = [
    {
      error: nativeRedirectError,
      code: 'provider_outcome_unknown',
    },
    {
      error: new TypeError('RAW_ORDINARY_CONNECTION_DETAIL'),
      code: 'provider_connection_interrupted',
    },
  ];
  try {
    for (const item of cases) {
      let fetchCalls = 0;
      let bodyReads = 0;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        fetchImpl: async () => {
          fetchCalls += 1;
          throw item.error;
        },
      });
      const error = await captureRejection(() => call('redirect system', 'redirect user'));
      assert.equal(error.outcome, 'ambiguous');
      assert.equal(error.safeErrorCode, item.code);
      assert.equal(fetchCalls, 1);
      assert.equal(bodyReads, 0);
      const disclosed = `${String(error)} ${JSON.stringify(error)}`;
      assert.equal(disclosed.includes('unexpected redirect'), false);
      assert.equal(disclosed.includes('RAW_'), false);
      assert.equal(disclosed.includes('redirect-transport-secret'), false);
      assert.equal(disclosed.includes('redirect system'), false);
      assert.equal(disclosed.includes('redirect user'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 one AbortController deadline remains active through the complete response body read', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'body-timeout-secret';
  let fetchCalls = 0;
  try {
    const call = providerModule.createSingleDispatchAICall(
      v2Provider({ timeoutMs: 10 }),
      {
        fetchImpl: async (_url, options) => {
          fetchCalls += 1;
          return {
            ok: true,
            status: 200,
            headers: { get: () => null },
            text: async () => new Promise((resolve, reject) => {
              const timeoutError = new Error('RAW_BODY_TIMEOUT');
              timeoutError.name = 'AbortError';
              options.signal.addEventListener('abort', () => reject(timeoutError), { once: true });
              setTimeout(() => reject(new Error('RAW_DEADLINE_WAS_CLEARED')), 50);
            }),
          };
        },
      },
    );
    const error = await captureRejection(() => call('system', 'user'));
    assert.equal(error.outcome, 'ambiguous');
    assert.equal(error.safeErrorCode, 'provider_timeout');
    assert.equal(fetchCalls, 1);
    assert.equal(`${String(error)} ${JSON.stringify(error)}`.includes('RAW_'), false);
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 completely read malformed responses fail safely and do not infer usage', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'metadata-secret';
  const cases = [
    {
      response: response({
        text: 'data: RAW_INVALID_JSON{\n\ndata: [DONE]\n\n',
      }),
      code: 'provider_invalid_response',
    },
    {
      response: kimiStreamResponse({ content: '', finishReason: 'length' }),
      code: 'provider_no_candidate',
    },
    {
      response: kimiStreamResponse({
        usage: { prompt_tokens: -1, completion_tokens: 2 },
      }),
      code: 'provider_invalid_response',
    },
    {
      response: kimiStreamResponse({
        usage: { prompt_tokens: Number.MAX_SAFE_INTEGER + 1 },
      }),
      code: 'provider_invalid_response',
    },
    {
      response: kimiStreamResponse({ id: 123 }),
      code: 'provider_invalid_response',
    },
  ];
  try {
    for (const item of cases) {
      let fetchCalls = 0;
      const call = providerModule.createSingleDispatchAICall(v2Provider(), {
        fetchImpl: async () => {
          fetchCalls += 1;
          return item.response;
        },
      });
      const error = await captureRejection(() => call('system', 'user'));
      assert.equal(error.outcome, 'failed_safe');
      assert.equal(error.safeErrorCode, item.code);
      assert.equal(error.inputTokens, null);
      assert.equal(error.outputTokens, null);
      assert.equal(error.billingEvidence, 'unknown');
      assert.equal(fetchCalls, 1);
      assert.equal(`${String(error)} ${JSON.stringify(error)}`.includes('RAW_INVALID_JSON'), false);
    }
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});

test('V2 missing usage remains unknown while independently reported usage remains exact', async () => {
  const previous = process.env.TEST_KIMI_KEY;
  process.env.TEST_KIMI_KEY = 'usage-secret';
  try {
    const noUsage = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => kimiStreamResponse({ content: '{}' }),
    });
    assert.deepEqual(await noUsage('system', 'user'), {
      content: '{}',
      providerRequestIdHash: null,
      inputTokens: null,
      outputTokens: null,
      billingEvidence: 'unknown',
    });

    const partialUsage = providerModule.createSingleDispatchAICall(v2Provider(), {
      fetchImpl: async () => kimiStreamResponse({
        content: '{}',
        usage: { completion_tokens: 7 },
      }),
    });
    assert.deepEqual(await partialUsage('system', 'user'), {
      content: '{}',
      providerRequestIdHash: null,
      inputTokens: null,
      outputTokens: 7,
      billingEvidence: 'reported',
    });
  } finally {
    if (previous === undefined) delete process.env.TEST_KIMI_KEY;
    else process.env.TEST_KIMI_KEY = previous;
  }
});
