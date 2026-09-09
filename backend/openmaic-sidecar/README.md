# Mira OpenMAIC sidecar

This is a narrow, backend-only adapter around the official OpenMAIC generation
package. It is **not** a second product backend and is never called by Flutter or
camera firmware directly.

The integration is pinned to the OpenMAIC source snapshot
`aa2bfb3c1d406c47100c6744d90e788abdf1f6d5` and the exact npm packages:

- `@openmaic/generation@0.3.1`
- `@openmaic/dsl@0.10.1`

The classroom API seam is
`generateSceneOutlinesFromRequirements(requirements, ..., aiCall)`. For the
structured classroom path, later content/action/build primitives are
deliberately not called; the Python host compiles the intent into controlled
templates. The host owns the OpenAI-compatible/Kimi callback. OpenMAIC never
reads Mira configuration files or owns persistence.

## Install and verify

Node.js 20 or newer is required.

```sh
cd backend/openmaic-sidecar
npm ci
npm test
npm run availability
```

## Runtime contracts

The CLI reads one JSON object from stdin, dispatches by `schemaVersion`, writes
one JSON object to stdout, and exits. The Python adapter can therefore enforce
an outer process timeout. Four contracts are supported:

| Purpose | Input | Output |
| --- | --- | --- |
| Backward-compatible lesson presentation enrichment | `mira.openmaic.generate.v1` | `mira.openmaic.draft.v1` |
| New question candidate generation | `mira.openmaic.question_generation.v1` | `mira.openmaic.question_candidates.v1` |
| Fresh-context independent solving | `mira.openmaic.question_verification.v1` | `mira.openmaic.question_verification_result.v1` |
| Structured classroom intent generation | `mira.openmaic.classroom_generation.v1` | `mira.openmaic.classroom_intent.v2` |

### Structured classroom intent

The classroom contract uses OpenMAIC for the instructional plan, not for
runtime rendering code:

1. `generateSceneOutlinesFromRequirements` with `interactiveMode: true`;
2. normalize exactly five intents: teach, demo, guided, independent, recap;
3. select only allowlisted `layoutTemplate` and `widgetTemplate` identifiers;
4. a separate Kimi review call over the normalized, answer-blind intent;
5. Python compiles the intent into the trusted lesson-package runtime shape.

The sidecar cannot return HTML, JavaScript, canvas geometry, runtime actions,
URLs, scoring rules, or answer keys. `assetBrief` is a bounded production
description and never a fetchable asset. PBL, code widgets, 3D widgets, video,
and procedural-skill widgets do not enter this publication path.

The input is deliberately answer-blind. `publicQuestions` may contain only
`id`, `type`, `prompt`, and public `choices`; alternatively, a trusted host may
supply opaque `questionRefs`. When both are present, every ref must name a
public question. The output quiz contains only `questionRefs` and never uses
OpenMAIC's generated quiz questions as authority. The Python caller passes q2-q5;
the sidecar binds q2/q3 to guided interaction and q4/q5 to independent evidence.

Input example:

```json
{
  "schemaVersion": "mira.openmaic.classroom_generation.v1",
  "requestId": "classroom-primary1-chinese-1",
  "gradeCode": "primary_1",
  "subject": "chinese",
  "skillBoundary": {
    "skillId": "pinyin_syllables",
    "skillTitle": "单韵母 a、o、e",
    "learningObjectives": ["能看口形认读 a、o、e", "能听辨 a、o、e"],
    "allowedContent": ["单韵母 a、o、e", "a、o、e 的口形提示"],
    "excludedContent": ["声母", "偏旁部首", "生字认读"],
    "prerequisiteSkills": [],
    "language": "zh-CN",
    "estimatedMinutes": 15
  },
  "publicQuestions": [
    {
      "id": "q2",
      "type": "single_choice",
      "prompt": "听老师读音后，选择 a。",
      "choices": [
        { "id": "A", "label": "a" },
        { "id": "B", "label": "o" },
        { "id": "C", "label": "e" }
      ]
    },
    {
      "id": "q3",
      "type": "single_choice",
      "prompt": "听老师读音后，选择 o。",
      "choices": [
        { "id": "A", "label": "e" },
        { "id": "B", "label": "o" },
        { "id": "C", "label": "a" }
      ]
    },
    { "id": "q4", "type": "exact_text", "prompt": "写出 e。" },
    { "id": "q5", "type": "exact_text", "prompt": "写出 a。" }
  ],
  "questionRefs": ["q2", "q3", "q4", "q5"],
  "assets": [],
  "classroomOptions": {
    "maxScenes": 5,
    "maxActionsPerScene": 8,
    "maxCanvasElements": 40,
    "maxHtmlChars": 50000,
    "allowedSceneTypes": ["slide", "interactive", "quiz"],
    "requiredSceneTypes": ["slide", "interactive", "quiz"],
    "quizMode": "independent"
  },
  "provider": {
    "name": "kimi",
    "model": "kimi-k2.6",
    "baseUrl": "https://api.moonshot.cn/v1",
    "apiKeyEnv": "APP_AI_API_KEY"
  }
}
```

Normalized output shape (content abbreviated):

```json
{
  "schemaVersion": "mira.openmaic.classroom_intent.v2",
  "dslVersion": "0.2.0",
  "generator": "openmaic",
  "status": "unverified",
  "publicationEligible": false,
  "authoritativeAnswersProvided": false,
  "classroom": {
    "id": "stage-1",
    "title": "单韵母 a、o、e",
    "language": "zh-CN",
    "intent": {
      "schemaVersion": "mira.learning.classroom-intent.v1",
      "layoutTemplate": "phonics_focus.v1",
      "widgetTemplate": "listen_tap_choice.v1",
      "assetBrief": [
        {
          "id": "aoe-pronunciation",
          "kind": "audio",
          "purpose": "a、o、e 标准发音，可由受控 TTS 提供",
          "required": false,
          "deliveryMode": "tts"
        }
      ],
      "misconceptions": ["把 a、o、e 的口形混在一起"],
      "teach": { "title": "先认识 a、o、e", "sayText": "...", "keyPoints": ["..."] },
      "demo": { "title": "老师示范", "sayText": "...", "keyPoints": ["..."] },
      "guided": {
        "title": "听一听，点一点",
        "sayText": "...",
        "keyPoints": [],
        "questionRefs": ["q2", "q3"]
      },
      "independent": {
        "title": "我来自己试",
        "sayText": "...",
        "keyPoints": [],
        "questionRefs": ["q4", "q5"]
      },
      "recap": { "title": "回顾一下", "sayText": "...", "keyPoints": ["..."] },
      "gameRules": {
        "goal": "完成两道引导听辨",
        "instructions": ["先听读音", "再点字母", "听反馈后继续"],
        "successCriterion": "两道引导练习都经过服务器判定",
        "maxAttempts": 2,
        "feedbackMode": "encouraging_retry"
      }
    }
  },
  "generationMeta": {
    "teachingReview": {
      "passed": true,
      "issues": [],
      "reviewer": "independent_ai_classroom_intent_review_v2"
    }
  }
}
```

The output is a production intent, not a runtime scene tree. The Python compiler
adds the fixed five-scene sequence, authoritative q1 worked example, q2/q3
guided state contract, q4/q5 independent evidence, and server-only assessment
references. No raw media is fabricated: an `assetBrief` is not an asset URL.

Every source remains unverified and non-publishable. A host publication gate
must require `generationMeta.teachingReview.passed === true`, revalidate the
fixed skill boundary and question refs, and persist a newly constructed trusted
lesson package. The review is an additional quality signal, not answer
authority.

Question generation requires top-level `gradeCode`, `subject`,
`skillBoundary`, `questionCount`, `existingFingerprints`, and `requestId`.
V1 deliberately requires exactly five questions. It first asks the official
OpenMAIC outline primitive for a bounded teaching plan, then uses the same
host-owned Kimi `AICallFn` seam for strict, teach-first candidate JSON. Only `chinese`,
`math`, and `english`, grades `primary_1` through `primary_6`, and the
deterministic types `numeric`, `single_choice`, `exact_text`, `accepted_text`,
and `sequence` are accepted.

The five objects have fixed roles: q1 is a validated, non-scored worked
example; q2-q3 are guided practice; q4-q5 are independent practice. All four
practice items run through deterministic server evaluation, while mastery uses
only the first attempts on q4 and q5 and requires two of two. The sidecar still
requires q1 to have a deterministic answer so Mira can verify and safely present
the worked example. Because one controlled widget renders the guided phase,
q2 and q3 must use the same type: both `single_choice` or both `sequence`.
Numeric and text-entry questions remain available for q1, q4, and q5.

Every candidate course contains this required host-normalized teaching flow:

```json
{
  "schemaVersion": "mira.learning.teaching-flow.v1",
  "teach": {
    "title": "short plain-text title",
    "sayText": "plain-text explanation spoken before practice",
    "keyPoints": ["one to three unique plain-text points"]
  },
  "demoQuestionId": "normalized q1 id",
  "guidedQuestionIds": ["normalized q2 id", "normalized q3 id"],
  "independentQuestionIds": ["normalized q4 id", "normalized q5 id"],
  "recap": {
    "sayText": "plain-text concept recap spoken after practice"
  }
}
```

Kimi supplies only `teach` and `recap`. The sidecar rejects model-provided role
IDs and always assigns the demonstration, guided, and independent IDs from the
five normalized question objects in order. `teach.title` is limited to 160
characters, `teach.sayText` to 1200, each of 1-3 key points to 200, and
`recap.sayText` to 600. Teaching-flow objects use exact field allowlists. Media,
HTML, URL, executable action, and whiteboard fields fail generation. Retained
strings are normalized to plain text. The sidecar also compares teaching and
recap text with the declared answers for q2-q5, including the correct option
label, and rejects direct answer disclosures. The q1 demonstration binding does
not add an answer or worked example to `teachingFlow`; Mira may construct that
later from its independently validated course.

The returned course is always `status: unverified` and
`publicationEligible: false`. It carries candidate-only source authority and
SHA-256 public-question fingerprints. Exact fingerprint collisions, unsafe
fields, unsupported question shapes, contradictory answer fields, and numeric
answers that disagree with their arithmetic verification expression fail the
request instead of being published.

Independent solving is a separate CLI request and therefore a fresh provider
call. Its input questions may contain only `id`, `type`, `prompt`, and public
`choices`; answer, hint, explanation, and evaluation fields are rejected. The
request must also carry `publicTeachingFlow`: the candidate's public flow plus a
required backend-constructed worked example:

```json
{
  "workedExample": {
    "questionId": "q1",
    "explanation": "plain-text explanation of the validated q1 example"
  }
}
```

`workedExample.questionId` must be exactly `q1`; `explanation` is required,
normalized to plain text, and limited to 1500 characters. The object uses an
exact field allowlist, so it cannot contain `answer`, media, or action fields.
The remaining role IDs must match public-question order exactly. The fresh call
independently reviews boundary preservation, factual consistency, age
appropriateness, whether the worked-example explanation correctly explains q1,
and whether teach/recap text leaks a practice answer. It must return the exact object
`teachingReview: {passed: boolean, issues: string[]}`; a passing review requires
an empty issue list, while a failing review requires at least one issue (maximum
8 issues, 300 characters each). Its
result embeds a `mira.learning.independent-solution.v1` object with exactly one
answer for every public question plus that `teachingReview`. Chinese, math, and
English all require this second solve. Mira must still require a passing review,
compare both answer sets, re-evaluate numeric
expressions programmatically, run the Python quality gates, and construct a new
published object. The sidecar never promotes its own candidate.

### Presentation enrichment

Required skill-boundary fields are `gradeCode`, `subject`, `skillId`, and at
least one `learningObjectives` item. Optional allow/exclude/prerequisite lists,
duration and scene count further constrain the draft. The boundary is repeated
in the output for auditability.

The provider object contains the model, base URL and **environment variable
name**, never an API key. The default key variable is `APP_AI_API_KEY`. Secrets
are read by the child process from its environment and are never placed in
stdin, command arguments, output, errors, or persisted draft JSON.

Example:

```sh
APP_AI_API_KEY=... node src/cli.mjs <<'JSON'
{
  "schemaVersion": "mira.openmaic.generate.v1",
  "requestId": "req-1",
  "skillBoundary": {
    "gradeCode": "primary_3",
    "subject": "math",
    "skillId": "math.p3.addition.carry",
    "skillTitle": "两位数进位加法",
    "learningObjectives": ["理解个位满十向十位进一"],
    "allowedContent": ["和不超过100"],
    "excludedContent": ["小数", "负数"],
    "outcomeMode": "scored_deterministic",
    "sessionKind": "lesson"
  },
  "provider": {
    "name": "kimi",
    "model": "kimi-k2.6",
    "baseUrl": "https://api.moonshot.cn/v1",
    "apiKeyEnv": "APP_AI_API_KEY"
  }
}
JSON
```

### Candidate-question example

```sh
APP_AI_API_KEY=... node src/cli.mjs <<'JSON'
{
  "schemaVersion": "mira.openmaic.question_generation.v1",
  "requestId": "questions-primary3-math-1",
  "gradeCode": "primary_3",
  "subject": "math",
  "skillBoundary": {
    "skillId": "math.p3.addition.carry",
    "skillTitle": "两位数进位加法",
    "learningObjectives": ["正确完成两位数进位加法"],
    "allowedContent": ["和不超过100"],
    "excludedContent": ["小数", "负数"],
    "prerequisiteSkills": ["两位数不进位加法"],
    "language": "zh-CN",
    "estimatedMinutes": 10
  },
  "questionCount": 5,
  "existingFingerprints": [],
  "provider": {
    "name": "kimi",
    "model": "kimi-k2.6",
    "baseUrl": "https://api.moonshot.cn/v1",
    "apiKeyEnv": "APP_AI_API_KEY"
  }
}
JSON
```

The Kimi candidate JSON for this request must include `teachingFlow.teach` and
`teachingFlow.recap` as described above. It must omit all question-role IDs;
those are assigned by the sidecar after the five questions are normalized.

## Content authority boundary

Every generated artifact is non-published. OpenMAIC is allowed to propose an
outline, explanation order, question wording, distractors, candidate answers,
and interaction drafts. It is not allowed to establish curriculum truth or
publish a lesson.

For the backward-compatible presentation-enrichment contract, OpenMAIC's
upstream quiz answers are recursively removed before anything crosses into
Mira. Every retained quiz item is marked
`answerAuthority: mira_validation_required`, and the overall draft says
`authoritativeAnswersProvided: false`.

The question-candidate contract necessarily retains proposed answers so Mira
can validate them. They remain untrusted generation output. A separate fresh
solver call, deterministic evaluator compatibility checks, fingerprint checks,
and programmatic numeric recalculation are mandatory before the host may build
a published course.

Presentation enrichment recursively removes disabled action and media fields,
including `action`, `media`, `html`, `src`, audio, video, image and whiteboard
payloads. Inside slide `elements`, only plain `text` and `shape` elements are
retained. Candidate generation is stricter: a generated action/media/HTML field
fails the request; rich-text strings are reduced to plain text. This
normalization is not the trust boundary by itself: the Python learning-content
service independently rejects forbidden fields or unsafe content, providing
defense in depth.

Fake generation is test-only and requires `OPENMAIC_FAKE_MODE=1` in the child
environment.

For Kimi/Moonshot requests, the callback sends `thinking: {"type":"disabled"}`
and temperature `0.6`, matching Mira's existing Kimi provider contract. This
prevents reasoning tokens from consuming the bounded JSON-output budget and
returning empty `content`.
