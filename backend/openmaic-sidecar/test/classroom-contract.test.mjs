import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import { postProcessInteractiveHtml } from '@openmaic/generation';

import {
  buildClassroomRequirement,
  classroomSchemas,
  normalizeClassroomGenerationRequest,
  normalizeClassroomReview,
  normalizeClassroomOutlines,
  normalizeCompleteClassroomScene,
  normalizeInteractiveHtml,
} from '../src/classroom-contract.mjs';
import {
  buildClassroomIntentCompilationPrompts,
  buildClassroomIntentRepairPrompts,
  buildClassroomIntentReviewPrompts,
  normalizeClassroomIntent,
} from '../src/classroom-intent-contract.mjs';

test('classroom reviewer applies only the active subject and skill boundary', () => {
  const mathRequest = baseInput({
    subject: 'math',
    skillBoundary: {
      skillId: 'number_sense_20',
      skillTitle: '20以内数感',
      learningObjectives: ['比较20以内的数', '理解十和一'],
      allowedContent: ['0到20', '数的比较', '十和一'],
      excludedContent: ['乘除法'],
      prerequisiteSkills: ['会数到10'],
      language: 'zh-CN',
      estimatedMinutes: 10,
    },
  });
  const mathPrompts = buildClassroomIntentReviewPrompts(mathRequest, {
    schemaVersion: 'mira.learning.classroom-intent.v1',
  });
  assert.match(mathPrompts.system, /number_sense_20/);
  assert.doesNotMatch(mathPrompts.system, /single vowels|a, o, e/);
  assert.match(mathPrompts.system, /Never substitute pinyin_syllables/);
  const mathReviewInput = JSON.parse(mathPrompts.user);
  assert.match(mathPrompts.system, /Every issues item must identify a concrete/);
  assert.match(mathPrompts.system, /整体正确/);
  assert.match(mathPrompts.system, /at most three concise unique strings/);
  assert.deepEqual(Object.keys(mathReviewInput).sort(), [
    'gradeCode',
    'presentation',
    'skillBoundary',
    'subject',
  ]);
  assert.equal('publicQuestions' in mathReviewInput, false);
  assert.equal('courseTeaching' in mathReviewInput, false);
  assert.equal('practiceRoleMap' in mathReviewInput, false);
  assert.deepEqual(mathReviewInput.presentation.hostWidgetCapabilities, {
    renderedContent: ['plain_text_question_prompt', 'rendered_choice_labels'],
    responseMode: 'single_choice',
    supportedTasks: ['concept_choice', 'arithmetic_choice', 'textual_story_context'],
    gradingAuthority: 'mira_host',
  });
  assert.equal('guidedInstructions' in mathReviewInput.presentation, false);
  assert.equal('independentInstructions' in mathReviewInput.presentation, false);
  assert.equal('gameRules' in mathReviewInput.presentation, false);
  assert.deepEqual(mathReviewInput.presentation.sceneTitles, {
    teach: '',
    demo: '',
    guided: '',
    independent: '',
    recap: '',
  });
  assert.match(mathPrompts.system, /deterministic host validation/);
  assert.match(mathPrompts.system, /Do not report missing worked examples/);
  assert.match(mathPrompts.system, /Never infer limitations from a widgetTemplate name/);
  assert.match(mathPrompts.system, /Never speculate that an asset number might conflict/);
  assert.throws(
    () => normalizeClassroomReview({
      passed: false,
      issues: ['一', '二', '三', '四'],
    }),
    /at most 3 items/,
  );

  const pinyinRequest = baseInput({
    skillBoundary: {
      ...baseInput().skillBoundary,
      skillId: 'pinyin_syllables',
    },
  });
  const pinyinPrompts = buildClassroomIntentReviewPrompts(pinyinRequest, {});
  assert.match(pinyinPrompts.system, /single vowels a, o, e/);
});

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'src', 'cli.mjs');

function baseInput(overrides = {}) {
  return {
    schemaVersion: classroomSchemas.input,
    requestId: 'classroom-primary1-chinese-1',
    gradeCode: 'primary_1',
    subject: 'chinese',
    skillBoundary: {
      skillId: 'chinese.p1.pinyin.initials-bpmf',
      skillTitle: '认识声母 b、p、m、f',
      learningObjectives: ['能听辨并正确认读 b、p、m、f'],
      allowedContent: ['声母 b、p、m、f 与简单音节'],
      excludedContent: ['偏旁部首', '生字默写'],
      prerequisiteSkills: ['能专注听短音节'],
      language: 'zh-CN',
      estimatedMinutes: 15,
    },
    courseTeaching: {
      teach: {
        title: '先听声母',
        sayText: '先看口形，再听老师读 b、p、m、f。',
        keyPoints: ['看口形', '听读音'],
      },
      workedExample: {
        questionId: 'q-demo',
        prompt: '示范：听老师读 p。',
        explanation: '老师先示范 p 的口形和读音。',
      },
      recap: { sayText: '回顾今天听过的声母和口形。' },
    },
    publicQuestions: [
      {
        id: 'q-public-1',
        type: 'single_choice',
        prompt: '听老师读音后，选择声母 p。',
        choices: [
          { id: 'A', label: 'b' },
          { id: 'B', label: 'p' },
          { id: 'C', label: 'm' },
        ],
      },
      {
        id: 'q-public-2',
        type: 'exact_text',
        prompt: '跟读声母 f。',
      },
    ],
    assets: [],
    classroomOptions: {
      maxScenes: 4,
      maxActionsPerScene: 7,
      maxCanvasElements: 20,
      maxHtmlChars: 30000,
      allowedSceneTypes: ['slide', 'interactive', 'quiz'],
      requiredSceneTypes: ['slide', 'interactive', 'quiz'],
      quizMode: 'practice',
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

function strictIntentRequest() {
  return {
    gradeCode: 'primary_1',
    subject: 'math',
    skillBoundary: {
      skillId: 'number_sense_20',
      skillTitle: '20以内数感',
      learningObjectives: ['认读并比较20以内的数'],
      allowedContent: ['20以内数的认读与比较'],
      excludedContent: ['进位加法'],
      prerequisiteSkills: ['10以内数感'],
      language: 'zh-CN',
      estimatedMinutes: 10,
    },
    courseTeaching: {
      teach: {
        title: '认识20以内的数',
        sayText: '先看十位有几个十，再看个位有几个一，然后比较大小。',
        keyPoints: ['先看十位', '再看个位'],
      },
      workedExample: {
        questionId: 'q1',
        prompt: '例题：比较9和12。',
        explanation: '12有一个十，9没有十，所以12比9大。',
      },
      recap: { sayText: '比较两个数时，先看十位，再看个位。' },
    },
    publicQuestions: [
      { id: 'q2', type: 'single_choice', prompt: '哪一个数更大？', choices: [] },
      { id: 'q3', type: 'single_choice', prompt: '选择较小的数。', choices: [] },
      { id: 'q4', type: 'accepted_text', prompt: '写出这个数。' },
      { id: 'q5', type: 'accepted_text', prompt: '再写一个数。' },
    ],
    questionRefs: ['q2', 'q3', 'q4', 'q5'],
  };
}

function strictIntentCandidate() {
  return {
    outlines: [
      {
        phaseRole: 'teach', type: 'slide', title: '先认识数',
        description: '先看数的组成，再比较大小。', keyPoints: ['看十位', '再看个位'],
        layoutTemplate: 'concept_focus.v1',
        misconceptions: ['只看个位就比较'],
        assetBrief: [],
      },
      {
        phaseRole: 'demo', type: 'slide', title: '老师示范',
        description: '老师示范怎样比较两个数。', keyPoints: ['按位比较'],
      },
      {
        phaseRole: 'guided', type: 'interactive', title: '一起练',
        description: '跟着提示完成两道练习。', keyPoints: [],
        widgetTemplate: 'match_pairs.v1',
        gameRules: {
          goal: '完成两道引导练习',
          instructions: ['先读题', '再选择', '听反馈后继续'],
          successCriterion: '两道引导题都得到服务器判定',
          maxAttempts: 2,
          feedbackMode: 'encouraging_retry',
        },
      },
      {
        phaseRole: 'independent', type: 'quiz', title: '自己试',
        description: '独立完成最后两道练习。', keyPoints: [],
      },
      {
        phaseRole: 'recap', type: 'slide', title: '回顾',
        description: '回顾按位比较的方法。', keyPoints: ['先十位后个位'],
      },
    ],
  };
}

function strictIntentCliInput(fakeResponses) {
  const request = strictIntentRequest();
  const publicQuestions = request.publicQuestions.map((question, index) => ({
    ...question,
    type: 'single_choice',
    choices: [
      { id: `q${index + 2}-a`, label: `${index + 11}` },
      { id: `q${index + 2}-b`, label: `${index + 12}` },
    ],
  }));
  return baseInput({
    requestId: 'classroom-primary1-math-repair',
    gradeCode: request.gradeCode,
    subject: request.subject,
    skillBoundary: request.skillBoundary,
    publicQuestions,
    questionRefs: request.questionRefs,
    mode: 'fake',
    fakeResponses,
  });
}

function runCli(input) {
  return spawnSync(process.execPath, [cli], {
    cwd: root,
    encoding: 'utf8',
    input: JSON.stringify(input),
    env: { ...process.env, OPENMAIC_FAKE_MODE: '1' },
  });
}

function assertNoAnswerKeys(value) {
  const forbidden = new Set([
    'answer',
    'answers',
    'correctanswer',
    'correctanswers',
    'analysis',
    'solution',
    'expectedanswer',
    'iscorrect',
    'hasanswer',
    'evaluation',
    'points',
  ]);
  if (Array.isArray(value)) {
    for (const item of value) assertNoAnswerKeys(item);
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const [key, item] of Object.entries(value)) {
    assert.equal(forbidden.has(key.toLowerCase()), false, `forbidden output key: ${key}`);
    assertNoAnswerKeys(item);
  }
}

test('classroom requirement states bounded asset and misconception contracts', () => {
  const requirement = buildClassroomRequirement(
    normalizeClassroomGenerationRequest(baseInput()),
  );
  assert.match(requirement, /zero to four assetBrief entries on the teach outline only/i);
  assert.match(requirement, /kind must be audio, image, or video/i);
  assert.match(requirement, /deliveryMode must be tts, generated_asset, or none/i);
  assert.match(requirement, /exactly one to three concise misconceptions on the teach outline only/i);
  assert.match(requirement, /guided outline must include the exact key widgetTemplate/i);
});

test('strict intent compilation receives only answer-blind public outline fields', () => {
  const input = normalizeClassroomGenerationRequest(baseInput());
  const prompts = buildClassroomIntentCompilationPrompts(input, {
    outlines: [
      {
        id: 'generic-outline-1',
        phaseRole: 'teach',
        type: 'slide',
        title: '先观察数量',
        description: '看一看两组物体的多少。',
        keyPoints: ['一一对应'],
        answer: 'private-answer-sentinel',
        correctAnswer: 'private-answer-sentinel',
        actions: [{ type: 'reveal-answer' }],
      },
    ],
  });
  const supplied = JSON.parse(prompts.user);
  assertNoAnswerKeys(supplied);
  assert.equal(prompts.user.includes('private-answer-sentinel'), false);
  assert.deepEqual(Object.keys(supplied.openMaicOutlines[0]), [
    'order',
    'phaseRole',
    'type',
    'title',
    'description',
    'keyPoints',
  ]);
  assert.deepEqual(supplied.courseTeaching, input.courseTeaching);
  assert.match(prompts.system, /Never solve a practice question/i);
  assert.match(prompts.system, /return JSON only/i);
  assert.match(prompts.system, /instructions is a JSON array of one to three unique/i);
  assert.match(prompts.system, /maxAttempts is the JSON integer 2 exactly/i);
  assert.match(prompts.system, /stateContract.*Mira host-owned/i);
  assert.match(prompts.system, /sort_order\.v1 only when both guided public questions are sequence/i);
});

test('strict intent game rules reject boundary violations without coercion or truncation', () => {
  const request = strictIntentRequest();
  assert.doesNotThrow(() => normalizeClassroomIntent(strictIntentCandidate(), request));

  const cases = [
    {
      message: /instructions must contain 1 to 3 items/,
      mutate: (candidate) => { candidate.outlines[2].gameRules.instructions = []; },
    },
    {
      message: /instructions must contain 1 to 3 items/,
      mutate: (candidate) => {
        candidate.outlines[2].gameRules.instructions = ['一', '二', '三', '四'];
      },
    },
    {
      message: /instructions must contain 1 to 3 items/,
      mutate: (candidate) => { candidate.outlines[2].gameRules.instructions = '先读题'; },
    },
    {
      message: /instructions\[0\] exceeds 240 characters/,
      mutate: (candidate) => {
        candidate.outlines[2].gameRules.instructions = ['学'.repeat(241)];
      },
    },
    {
      message: /instructions must not contain duplicates/,
      mutate: (candidate) => {
        candidate.outlines[2].gameRules.instructions = ['先读题', '先读题'];
      },
    },
    {
      message: /maxAttempts must be 2/,
      mutate: (candidate) => { candidate.outlines[2].gameRules.maxAttempts = '2'; },
    },
    {
      message: /feedbackMode is not supported/,
      mutate: (candidate) => {
        candidate.outlines[2].gameRules.feedbackMode = 'show_answer';
      },
    },
    {
      message: /guided\.gameRules must contain exactly/,
      mutate: (candidate) => {
        candidate.outlines[2].gameRules.stateContract = { completion: 'model_owned' };
      },
    },
    {
      message: /outlines\.guided must contain exactly/,
      mutate: (candidate) => {
        candidate.outlines[2].stateContract = { transitions: [] };
      },
    },
    {
      message: /lessonIntent must contain exactly/,
      mutate: (candidate) => { candidate.stateContract = { completion: 'model_owned' }; },
    },
  ];
  for (const { mutate, message } of cases) {
    const candidate = JSON.parse(JSON.stringify(strictIntentCandidate()));
    mutate(candidate);
    assert.throws(() => normalizeClassroomIntent(candidate, request), message);
  }
});

test('classroom compiler owns non-authoritative key-point display density', () => {
  const request = strictIntentRequest();
  const candidate = strictIntentCandidate();
  candidate.outlines[0].keyPoints = ['一', '二', '三', '四', '三'];
  candidate.outlines[1].keyPoints = [];
  const normalized = normalizeClassroomIntent(candidate, request);
  assert.deepEqual(normalized.teach.keyPoints, ['先看十位', '再看个位']);
  assert.deepEqual(normalized.demo.keyPoints, ['12有一个十，9没有十，所以12比9大']);
  assert.equal(normalized.demo.sayText, '12有一个十，9没有十，所以12比9大。');
  assert.equal(normalized.demo.title, '老师示范');
  assert.deepEqual(normalized.guided.keyPoints, []);
  assert.deepEqual(normalized.independent.keyPoints, []);

  const missingFeedback = strictIntentCandidate();
  missingFeedback.outlines[2].gameRules.instructions = ['先读题', '再选择'];
  const aligned = normalizeClassroomIntent(missingFeedback, request);
  assert.deepEqual(aligned.gameRules.instructions, [
    '读清题目',
    '点击一个选项',
    '提交后等待系统反馈',
  ]);
  assert.equal(aligned.gameRules.goal, '完成两道引导选择题');
  assert.equal(
    aligned.gameRules.successCriterion,
    '完成两道引导选择题并获得系统反馈',
  );
  assert.equal(
    aligned.guided.sayText,
    '完成两道引导选择题，每题提交后先看反馈再继续。',
  );
  assert.equal(
    aligned.independent.sayText,
    '用自己的方法，独立完成最后两道练习。',
  );

  const excessive = strictIntentCandidate();
  excessive.outlines[0].keyPoints = ['一', '二', '三', '四', '五', '六', '七'];
  assert.throws(
    () => normalizeClassroomIntent(excessive, request),
    /must be an array containing at most 6 source items/,
  );
});

test('classroom intent gets at most two answer-blind schema recompilations before review', () => {
  const generic = {
    courseTitle: '20以内数感',
    outlines: strictIntentCandidate().outlines,
  };
  const malformed = strictIntentCandidate();
  malformed.outlines[2].gameRules.instructions = [];
  const stillMalformed = strictIntentCandidate();
  stillMalformed.outlines[2].gameRules.maxAttempts = '2';
  const result = runCli(strictIntentCliInput([
    JSON.stringify(generic),
    JSON.stringify(malformed),
    JSON.stringify(stillMalformed),
    JSON.stringify(strictIntentCandidate()),
    JSON.stringify({ passed: true, issues: [] }),
  ]));
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.classroom.intent.teach.keyPoints.length, 2);
  assert.deepEqual(payload.generationMeta.teachingReview.passed, true);
});

test('classroom intent schema recompilation remains fail-closed after two repairs', () => {
  const generic = {
    courseTitle: '20以内数感',
    outlines: strictIntentCandidate().outlines,
  };
  const malformed = strictIntentCandidate();
  malformed.outlines[2].gameRules.instructions = [];
  const stillMalformed = strictIntentCandidate();
  stillMalformed.outlines[2].gameRules.maxAttempts = '2';
  const finalMalformed = strictIntentCandidate();
  finalMalformed.outlines[2].gameRules.feedbackMode = 'show_answer';
  const result = runCli(strictIntentCliInput([
    JSON.stringify(generic),
    JSON.stringify(malformed),
    JSON.stringify(stillMalformed),
    JSON.stringify(finalMalformed),
  ]));
  assert.equal(result.status, 1);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.error.code, 'invalid_generation');
  assert.match(payload.error.message, /feedbackMode is not supported/);
});

test('classroom intent repair prompt is same-course, answer-blind, and contains no validation feedback', () => {
  const request = strictIntentRequest();
  const malformed = strictIntentCandidate();
  malformed.outlines[0].keyPoints = ['一', '二', '三', '四'];
  malformed.outlines[0].unrelatedProviderField = 'must-not-be-forwarded';
  const prompts = buildClassroomIntentRepairPrompts(request, malformed);
  const supplied = JSON.parse(prompts.user);
  assertNoAnswerKeys(supplied);
  assert.equal(prompts.user.includes('must-not-be-forwarded'), false);
  assert.equal(/validation|error|issue/i.test(prompts.user), false);
  assert.deepEqual(Object.keys(supplied).sort(), [
    'classroomIntentCandidate',
    'courseTeaching',
    'gradeCode',
    'hostRequirements',
    'publicPracticeQuestions',
    'questionRefs',
    'skillBoundary',
    'subject',
  ]);
  assert.equal(supplied.classroomIntentCandidate.outlines[0].keyPoints.length, 4);
  assert.match(prompts.system, /schema-only recompilation/i);
  assert.match(prompts.system, /Mandatory final count check/);
  assert.match(prompts.system, /teach\.keyPoints=1\.\.3/);
});

test('classroom intent repair refuses authoritative or executable candidate fields', () => {
  const request = strictIntentRequest();
  for (const forbidden of [
    { answer: 'private-answer-sentinel' },
    { html: '<script>unsafe()</script>' },
    { actions: [{ type: 'reveal' }] },
  ]) {
    const candidate = strictIntentCandidate();
    Object.assign(candidate.outlines[0], forbidden);
    assert.throws(
      () => buildClassroomIntentRepairPrompts(request, candidate),
      (error) => error?.code === 'unsafe_generation',
    );
  }
});

test('fake classroom generation emits only a five-phase structured lesson intent', () => {
  const outline = JSON.stringify({
    courseTitle: '单韵母 a、o、e',
    misconceptions: ['把 a、o、e 的口形混在一起', '只看字形，不认真听读音'],
    assetBrief: [
      {
        id: 'aoe-pronunciation',
        kind: 'audio',
        purpose: 'a、o、e 标准发音，可由受控 TTS 提供',
        required: false,
        deliveryMode: 'tts',
      },
    ],
    outlines: [
      {
        phaseRole: 'teach', type: 'slide', title: '先认识 a、o、e',
        description: '今天先听一听、看一看三个单韵母 a、o、e。',
        keyPoints: ['嘴巴张大读 a', '嘴巴圆圆读 o', '嘴巴扁扁读 e'],
        layoutTemplate: 'phonics_focus.v1',
        misconceptions: ['把 a、o、e 的口形混在一起', '只看字形，不认真听读音'],
        assetBrief: [
          {
            id: 'aoe-pronunciation', kind: 'audio',
            purpose: 'a、o、e 标准发音，可由受控 TTS 提供', required: false, deliveryMode: 'tts',
          },
        ],
      },
      {
        phaseRole: 'demo', type: 'slide', title: '老师示范',
        description: '老师先看口形，再慢慢示范 a、o、e。',
        keyPoints: ['看口形', '听读音'],
      },
      {
        phaseRole: 'guided', type: 'interactive', title: '听一听，点一点',
        description: '听完一个读音，再点对应的字母。', keyPoints: [],
        widgetTemplate: 'listen_tap_choice.v1',
        gameRules: {
          goal: '完成两道引导听辨',
          instructions: ['先听读音', '再点字母', '听反馈后继续'],
          successCriterion: '两道引导练习都完成服务器判定',
          maxAttempts: 2,
          feedbackMode: 'encouraging_retry',
        },
      },
      {
        phaseRole: 'independent', type: 'quiz', title: '我来自己试',
        description: '独立完成最后两道练习。', keyPoints: [],
      },
      {
        phaseRole: 'recap', type: 'slide', title: '回顾一下',
        description: '再看一次 a、o、e 的口形和读音，之后可以继续练习。',
        keyPoints: ['认清 a、o、e', '先听再读'],
      },
    ],
  });
  const input = baseInput({
    skillBoundary: {
      skillId: 'pinyin_syllables',
      skillTitle: '单韵母 a、o、e',
      learningObjectives: ['能看口形认读单韵母 a、o、e', '能听辨 a、o、e 的基本读音'],
      allowedContent: ['单韵母 a、o、e', 'a、o、e 的口形提示'],
      excludedContent: ['声母', '偏旁部首', '生字认读'],
      prerequisiteSkills: [],
      language: 'zh-CN',
      estimatedMinutes: 10,
    },
    courseTeaching: {
      teach: {
        title: '先认识 a、o、e',
        sayText: '先看口形，再听老师示范单韵母 a、o、e。',
        keyPoints: ['嘴巴张大读 a', '嘴巴圆圆读 o', '嘴巴扁扁读 e'],
      },
      workedExample: {
        questionId: 'q-demo',
        prompt: '示范：听老师读 a。',
        explanation: '老师张大嘴巴，清楚地读出 a。',
      },
      recap: { sayText: '回顾 a、o、e 的口形和读音。' },
    },
    publicQuestions: [
      ...baseInput().publicQuestions,
      { id: 'q-public-3', type: 'single_choice', prompt: '选择 o。', choices: [{ id: 'A', label: 'o' }, { id: 'B', label: 'e' }] },
      { id: 'q-public-4', type: 'exact_text', prompt: '写出 e。' },
    ],
    mode: 'fake',
    fakeResponses: [
      outline,
      JSON.stringify({ outlines: JSON.parse(outline).outlines }),
      JSON.stringify({ passed: true, issues: [] }),
    ],
  });

  const result = runCli(input);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.schemaVersion, 'mira.openmaic.classroom_intent.v2');
  assert.equal(payload.classroom.intent.schemaVersion, 'mira.learning.classroom-intent.v1');
  assert.equal(payload.classroom.intent.layoutTemplate, 'phonics_focus.v1');
  assert.equal(payload.classroom.intent.widgetTemplate, 'listen_tap_choice.v1');
  assert.deepEqual(payload.classroom.intent.guided.questionRefs, ['q-public-1', 'q-public-2']);
  assert.deepEqual(payload.classroom.intent.independent.questionRefs, ['q-public-3', 'q-public-4']);
  assert.deepEqual(payload.classroom.intent.gameRules.maxAttempts, 2);
  assert.equal('scenes' in payload.classroom, false);
  assert.equal(/html|canvas|javascript|actions/i.test(JSON.stringify(payload.classroom.intent)), false);
  assertNoAnswerKeys(payload);
  assert.deepEqual(payload.generationMeta.teachingReview, {
    passed: true,
    issues: [],
    reviewer: 'independent_ai_classroom_intent_review_v2',
  });
});

test('interactive HTML keeps offline addEventListener logic but rejects escape and network APIs', () => {
  const safe = normalizeInteractiveHtml(
    '<html><head><meta charset="utf-8"><style>body{color:#222}</style>' +
      '<script type="application/json" id="widget-config">{"type":"simulation"}</script>' +
      '</head><body>' +
      '<input id="s" type="range"><script>' +
      "document.getElementById('s').addEventListener('input',()=>{document.body.dataset.done='1';});" +
      '</script></body></html>',
    5000,
  );
  assert.match(safe, /<script>/);
  assert.match(safe, /addEventListener/);
  assert.doesNotMatch(safe, /<meta/i);
  assert.doesNotMatch(safe, /widget-config/);
  assert.doesNotThrow(() =>
    normalizeInteractiveHtml(
      "<script>document.body.textContent='Try this sound';</script>",
      5000,
    ),
  );

  const unsafe = [
    '<script src="lesson.js"></script>',
    '<button onclick="play()">开始</button>',
    '<link rel="stylesheet" href="lesson.css">',
    '<img src="data:image/png;base64,AA">',
    '<script>fetch("/api")</script>',
    '<script>new XMLHttpRequest()</script>',
    '<script>new WebSocket("wss:"+"//x")</script>',
    '<script>new EventSource("/events")</script>',
    '<script>localStorage.setItem("x","1")</script>',
    '<script>document.cookie="x=1"</script>',
    '<script>parent.postMessage("x","*")</script>',
    '<script>window.location="/next"</script>',
    '<form action="/submit"><input></form>',
    '<style>.x{background:url(icon.png)}</style>',
    '<script>new Worker("worker.js")</script>',
    '<a href="https://example.com">离开</a>',
    '<script>const root=this;</script>',
    '<script>setTimeout("doWork()", 1)</script>',
    '<script>const key=`${document.body.id}`</script>',
    '<script>document.body["href"]="/next"</script>',
  ];
  for (const html of unsafe) {
    assert.throws(() => normalizeInteractiveHtml(html, 5000), /interactive HTML contains forbidden/);
  }
});

test('normalization removes OpenMAIC CDN KaTeX injection before enforcing offline HTML', () => {
  const upstream = postProcessInteractiveHtml(
    '<!doctype html><html><head><style>body{color:#222}</style></head>' +
      '<body><p>拖动滑杆：$b$</p><input id="s" type="range">' +
      '<script>document.getElementById("s").addEventListener("input",()=>{});</script>' +
      '</body></html>',
  );
  assert.match(upstream, /cdn\.jsdelivr\.net/);
  const normalized = normalizeInteractiveHtml(upstream, 10000);
  assert.doesNotMatch(normalized, /cdn\.jsdelivr\.net|setInterval|setTimeout|renderMathInElement/);
  assert.match(normalized, /type="range"/);
  assert.match(normalized, /addEventListener/);
});

test('classroom input is answer-blind and asset references are opaque allowlisted identifiers', () => {
  const withAnswer = baseInput();
  withAnswer.publicQuestions[0].answer = 'B';
  assert.throws(() => normalizeClassroomGenerationRequest(withAnswer), /answer is not allowed/);

  const withUrlAsset = baseInput({
    assets: [{ assetRef: 'https://example.com/image.png', kind: 'image', alt: 'unsafe' }],
  });
  assert.throws(() => normalizeClassroomGenerationRequest(withUrlAsset), /opaque identifier/);

  const withSchemeAsset = baseInput({
    assets: [{ assetRef: 'javascript:lesson', kind: 'image', alt: 'unsafe' }],
  });
  assert.throws(() => normalizeClassroomGenerationRequest(withSchemeAsset), /URL-like scheme/);

  const withUnknownRef = baseInput({ questionRefs: ['not-in-public-questions'] });
  assert.throws(() => normalizeClassroomGenerationRequest(withUnknownRef), /unknown id/);
});

test('CLI dispatches classroom errors with the classroom output schema', () => {
  const input = baseInput({ gradeCode: 'primary_7', mode: 'fake', fakeResponses: [] });
  const result = runCli(input);
  assert.equal(result.status, 1);
  const payload = JSON.parse(result.stdout);
  assert.equal(payload.schemaVersion, 'mira.openmaic.classroom_intent.v2');
  assert.equal(payload.requestId, input.requestId);
  assert.equal(payload.error.code, 'invalid_input');
});

test('normalization keeps one ordered runtime quiz and Python-compatible limits', () => {
  const request = normalizeClassroomGenerationRequest(baseInput());
  const outlines = normalizeClassroomOutlines(
    {
      outlines: [
        { id: 's1', type: 'slide', title: '讲解', description: '先学', keyPoints: [] },
        {
          id: 'i1',
          type: 'interactive',
          title: '互动',
          description: '再练',
          keyPoints: [],
          widgetType: 'game',
          widgetOutline: { challenge: '配对' },
        },
        { id: 'q1', type: 'quiz', title: '练习一', description: '检查', keyPoints: [] },
        { id: 'q2', type: 'quiz', title: '练习二', description: '重复检查', keyPoints: [] },
      ],
    },
    request,
  );
  assert.equal(outlines.filter((outline) => outline.type === 'quiz').length, 1);
  assert.equal(outlines.find((outline) => outline.type === 'quiz').id, 'q1');

  const tooManyActions = baseInput();
  tooManyActions.classroomOptions.maxActionsPerScene = 9;
  assert.throws(() => normalizeClassroomGenerationRequest(tooManyActions), /integer from 2 to 8/);

  assert.throws(
    () => normalizeInteractiveHtml(`<p>${'汉'.repeat(20000)}</p>`, 50000),
    /UTF-8 byte limit/,
  );
});

test('slide canvas accepts only registered assetRef media and never emits a raw URL', () => {
  const request = normalizeClassroomGenerationRequest(
    baseInput({
      assets: [{ assetRef: 'asset-image-1', kind: 'image', alt: '声母口形示意图' }],
    }),
  );
  const outline = {
    id: 'slide-with-image',
    type: 'slide',
    title: '看口形',
    description: '观察口形。',
    keyPoints: ['看清嘴唇动作'],
    order: 1,
  };
  const safe = normalizeCompleteClassroomScene({
    builtScene: {
      title: '看口形',
      content: {
        canvas: {
          elements: [
            {
              id: 'image-1',
              type: 'image',
              src: 'asset-image-1',
              left: 100,
              top: 80,
              width: 400,
              height: 300,
              rotate: 0,
              fixedRatio: true,
            },
          ],
          background: { type: 'solid', color: '#ffffff' },
        },
      },
      actions: [],
    },
    outline,
    request,
    sceneIndex: 0,
    questionRefs: request.questionRefs,
  });
  assert.equal(safe.canvas.elements[0].src, 'asset-image-1');
  assert.equal(safe.canvas.elements[0].assetRef, 'asset-image-1');
  assert.equal(safe.blocks[0].assetRef, 'asset-image-1');

  const unsafeScene = {
    title: '看口形',
    content: {
      canvas: {
        elements: [
          {
            id: 'image-1',
            type: 'image',
            src: 'https://unsafe.example/image.png',
            left: 100,
            top: 80,
            width: 400,
            height: 300,
          },
        ],
      },
    },
    actions: [],
  };
  assert.throws(
    () =>
      normalizeCompleteClassroomScene({
        builtScene: unsafeScene,
        outline,
        request,
        sceneIndex: 0,
        questionRefs: request.questionRefs,
      }),
    /registered assetRef/,
  );
});
