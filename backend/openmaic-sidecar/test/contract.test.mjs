import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';

import { buildDraft, normalizeRequest } from '../src/contract.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'src', 'cli.mjs');

function baseInput(overrides = {}) {
  return {
    schemaVersion: 'mira.openmaic.generate.v1',
    requestId: 'req-openmaic-1',
    skillBoundary: {
      gradeCode: 'primary_3',
      subject: 'math',
      skillId: 'math.p3.addition.carry',
      skillTitle: '两位数进位加法',
      learningObjectives: ['理解个位满十向十位进一', '正确计算两位数进位加法'],
      allowedContent: ['和不超过100的两位数加法'],
      excludedContent: ['小数', '负数'],
      prerequisiteSkills: ['两位数不进位加法'],
      language: 'zh-CN',
      outcomeMode: 'scored_deterministic',
      sessionKind: 'lesson',
      maxScenes: 2,
      durationMinutes: 10,
    },
    provider: {
      name: 'kimi',
      model: 'kimi-k2.6',
      baseUrl: 'https://api.moonshot.cn/v1',
      apiKeyEnv: 'APP_AI_API_KEY',
    },
    ...overrides,
  };
}

function runCli(input) {
  return spawnSync(process.execPath, [cli], {
    cwd: root,
    encoding: 'utf8',
    input: JSON.stringify(input),
    env: { ...process.env, OPENMAIC_FAKE_MODE: '1' },
  });
}

test('fake generation returns a neutral Mira draft and strips answer authority', () => {
  const outline = JSON.stringify({
    courseTitle: '进位加法小课堂',
    languageDirective: 'Use Simplified Chinese.',
    outlines: [
      {
        id: 'explain',
        type: 'slide',
        title: '为什么要进位',
        description: '用小棒理解满十进一',
        keyPoints: ['10个一换成1个十'],
      },
      {
        id: 'check',
        type: 'quiz',
        title: '试一试',
        description: '判断是否需要进位',
        keyPoints: ['先算个位'],
        quizConfig: { questionCount: 1, difficulty: 'easy', questionTypes: ['single'] },
      },
    ],
  });
  const slide = JSON.stringify({
    background: { type: 'solid', color: '#ffffff' },
    elements: [],
    remark: '先把个位相加。',
  });
  const quiz = JSON.stringify([
    {
      id: 'q1',
      type: 'single',
      question: '27+15先算哪一位？',
      options: [
        { label: '个位', value: 'A', isCorrect: true },
        { label: '十位', value: 'B' },
      ],
      answer: ['A'],
      correctAnswer: 'A',
      analysis: '个位相加会进位。',
      hasAnswer: true,
      points: 10,
      evaluation: {
        evaluator: 'single_choice',
        expectedOptionId: 'A',
        passingScore: 100,
      },
    },
  ]);
  const result = runCli(baseInput({ mode: 'fake', fakeResponses: [outline, slide, quiz] }));

  assert.equal(result.status, 0, result.stderr || result.stdout);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.schemaVersion, 'mira.openmaic.draft.v1');
  assert.equal(payload.generator, 'openmaic');
  assert.equal(payload.requestId, 'req-openmaic-1');
  assert.equal(payload.provider, 'kimi');
  assert.equal(payload.model, 'kimi-k2.6');
  assert.equal(payload.draft.authoritativeAnswersProvided, false);
  assert.equal(payload.draft.scenes.length, 2);
  const question = payload.draft.scenes[1].interactionDraft.questions[0];
  assert.equal(question.question, '27+15先算哪一位？');
  assert.equal(question.answerAuthority, 'mira_validation_required');
  assert.equal('answer' in question, false);
  assert.equal('correctAnswer' in question, false);
  assert.equal('analysis' in question, false);
  assert.equal('hasAnswer' in question, false);
  assert.equal('points' in question, false);
  assert.equal('evaluation' in question, false);
  assert.equal('isCorrect' in question.options[0], false);
});

test('buildDraft recursively strips non-empty action and media fields while retaining text and shape', () => {
  const request = normalizeRequest(baseInput());
  const result = buildDraft({
    request,
    generation: {
      courseTitle: '安全净化测试',
      languageDirective: 'Use Simplified Chinese.',
      outlines: [
        {
          id: 'safe-slide',
          type: 'slide',
          title: '只保留安全内容',
          description: '危险字段必须在进入 Mira 前移除',
          keyPoints: ['保留文字和形状'],
        },
      ],
    },
    contents: [
      {
        action: { type: 'open-url', src: 'https://unsafe.example/action' },
        media: { image: 'data:image/png;base64,not-empty' },
        nested: {
          html: '<script>unsafe()</script>',
          audio: { src: 'https://unsafe.example/audio.mp3' },
          video: 'https://unsafe.example/video.mp4',
          whiteboard: { actions: [{ type: 'draw' }] },
        },
        elements: [
          {
            type: 'text',
            content: '27 + 15 先算个位',
            src: 'https://unsafe.example/text-background.png',
            action: { type: 'navigate' },
          },
          {
            type: 'shape',
            shape: 'roundRect',
            text: '满十进一',
            html: '<b>unsafe duplicate</b>',
          },
          { type: 'image', src: 'https://unsafe.example/image.png' },
          { type: 'video', mediaRef: 'unsafe-video' },
          { type: 'audio', src: 'https://unsafe.example/audio.mp3' },
          { type: 'embed', html: '<iframe src="https://unsafe.example"></iframe>' },
          { type: 'html', html: '<script>unsafe()</script>' },
          { type: 'chart', data: [{ value: 42 }] },
        ],
      },
    ],
    elapsedMs: 12,
  });

  const interaction = result.draft.scenes[0].interactionDraft;
  assert.deepEqual(
    interaction.elements.map((element) => element.type),
    ['text', 'shape'],
  );
  assert.equal(interaction.elements[0].content, '27 + 15 先算个位');
  assert.equal(interaction.elements[1].text, '满十进一');
  assert.equal('src' in interaction.elements[0], false);
  assert.equal('action' in interaction.elements[0], false);
  assert.equal('html' in interaction.elements[1], false);
  assert.deepEqual(interaction.nested, {});
  assert.equal('action' in interaction, false);
  assert.equal('media' in interaction, false);
  assert.doesNotMatch(JSON.stringify(result), /unsafe\.example|<script>|<iframe/);
});

test('buildDraft converts retained element HTML into plain text', () => {
  const request = normalizeRequest(baseInput());
  const result = buildDraft({
    request,
    generation: {
      courseTitle: '纯文本测试',
      languageDirective: 'Use Simplified Chinese.',
      outlines: [
        {
          id: 'plain-text-slide',
          type: 'slide',
          title: '清理富文本',
          description: '内部草稿不得携带可执行 HTML',
          keyPoints: ['纯文本'],
        },
      ],
    },
    contents: [
      {
        elements: [
          {
            type: 'text',
            content:
              '<p style="color:red" onclick="unsafe()">第一步&nbsp;&amp;检查</p>' +
              '<script>alert(1)</script><style>body{display:none}</style>' +
              '<div>第二步<br>满十进一 &#x2713;</div>' +
              '&lt;script&gt;encodedUnsafe()&lt;/script&gt;',
          },
          {
            type: 'shape',
            text: '<b onmouseover="unsafe()">重点</b>',
            fill: '#fff',
          },
        ],
      },
    ],
    elapsedMs: 7,
  });

  const elements = result.draft.scenes[0].interactionDraft.elements;
  assert.equal(elements[0].content, '第一步 &检查\n第二步\n满十进一 ✓');
  assert.equal(elements[1].text, '重点');
  assert.doesNotMatch(
    JSON.stringify(result),
    /<[^>]*>|onclick|onmouseover|alert\(1\)|encodedUnsafe|display:none/,
  );
});

test('buildDraft also converts quiz and scene rich text into plain text', () => {
  const request = normalizeRequest(baseInput());
  const result = buildDraft({
    request,
    generation: {
      courseTitle: '<b>纯文本课程</b>',
      languageDirective: '<p>使用简体中文</p>',
      outlines: [
        {
          id: 'plain-quiz',
          type: 'quiz',
          title: '<strong>试一试</strong>',
          description: '&lt;script&gt;encodedUnsafe()&lt;/script&gt;请回答',
          keyPoints: ['<em>先思考</em>'],
        },
      ],
    },
    contents: [
      {
        questions: [
        {
          id: 'q1',
          type: 'short_answer',
          question: '<p>8 + 5 = ?</p><script>alert(1)</script>',
        },
        ],
      },
    ],
    elapsedMs: 8,
  });

  const scene = result.draft.scenes[0];
  assert.equal(result.draft.courseTitle, '纯文本课程');
  assert.equal(scene.title, '试一试');
  assert.equal(scene.description, '请回答');
  assert.equal(scene.keyPoints[0], '先思考');
  assert.equal(scene.interactionDraft.questions[0].question, '8 + 5 = ?');
  assert.doesNotMatch(JSON.stringify(result), /<[^>]*>|encodedUnsafe|alert\(1\)/);
});

test('rejects a request without a fixed learning objective', () => {
  const input = baseInput();
  input.skillBoundary.learningObjectives = [];
  const result = runCli(input);
  assert.equal(result.status, 1);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.error.code, 'invalid_input');
});

test('rejects non-language-math subjects and non-lesson outcome boundaries', () => {
  const unsafeInputs = [
    { gradeCode: 'primary_7' },
    { subject: 'science' },
    { subject: 'information_technology' },
    { outcomeMode: 'participation_only' },
    { sessionKind: 'activity' },
  ];
  for (const overrides of unsafeInputs) {
    const input = baseInput();
    Object.assign(input.skillBoundary, overrides);
    const result = runCli(input);
    assert.equal(result.status, 1, result.stdout);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.error.code, 'invalid_input');
  }
});

test('live mode reads the API key only from the configured environment variable', () => {
  const result = spawnSync(process.execPath, [cli], {
    cwd: root,
    encoding: 'utf8',
    input: JSON.stringify(baseInput()),
    env: { ...process.env, APP_AI_API_KEY: '', OPENMAIC_FAKE_MODE: '0' },
  });
  assert.equal(result.status, 1);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.error.code, 'openmaic_unavailable');
  assert.match(payload.error.message, /APP_AI_API_KEY/);
});
