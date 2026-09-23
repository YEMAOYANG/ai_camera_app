import { z } from "zod";

const sha = z.string().regex(/^[a-f0-9]{64}$/);
const id = z.string().trim().min(1).max(255);
const text = z.string().trim().min(1).max(8000);
const strings = z.array(text).max(500);
const lessonId = z.string().regex(/^(ZH|M|EN)[1-6][AB][0-9]{2}\.[0-9]{2}$/);
const grade = z.string().regex(/^primary_[1-6]$/);
const subject = z.enum(["chinese", "math", "english"]);
const mode = z.enum(["objective", "observed"]);
const operation = z.enum(["add", "subtract", "multiply", "divide"]);
const evidenceKind = z.enum(["token_match", "numeric_expression", "independent_choice", "count_objects"]);
const curriculumVersion = z.literal("mira.primary.progressive.v1");

export function sameProgressiveValue(left: unknown, right: unknown): boolean {
  const canonical = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)]));
    return value;
  };
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

const constraints = z.object({
  allowedGrammarCodes: strings, allowedLetters: strings, allowedOperations: z.array(operation).max(4),
  allowedPinyin: strings, assessmentEvidenceKinds: z.array(evidenceKind).max(4),
  assessmentEvidenceScope: z.enum(["declared_objective_only", "observed_performance"]),
  audioInstructionsAllowed: z.literal(true), challengeMayOnlyCombineDeclaredKnowledge: z.literal(true),
  excludedGrammarCodes: strings, introducedGrammarCodes: strings, introducedOperations: z.array(operation).max(4),
  introducedTokens: strings, maxCoreNewTargets: z.literal(1),
  minimumNumber: z.number().finite().nullable(), maximumNumber: z.number().finite().nullable(),
  neutralDistractorTokens: z.array(z.enum(["○", "△", "□"])).max(3),
  newVocabularyMustBeIntroducedBeforeUse: z.literal(true), noUnintroducedKnowledgeInInstructions: z.literal(true),
  teachBeforeAssessment: z.literal(true),
  tokenKind: z.enum(["general", "letter", "number", "phonics", "pinyin", "vocabulary"]),
  writtenNumberRecognitionRequired: z.boolean(),
}).strict();

export const progressiveBindingSchema = z.object({
  schemaVersion: z.literal("mira.learning.progressive-binding.v1"), curriculumVersion,
  lessonId, identitySha256: sha, lessonSha256: sha, difficultyCode: z.literal("basic"), assessmentMode: mode,
}).strict();

const lessonScopeFields = {
  unitId: z.string().regex(/^(ZH|M|EN)[1-6][AB][0-9]{2}$/), unitTitle: text, sourceStepTitle: text,
  learningObjectives: strings.min(1), introducedKnowledgeIds: z.array(lessonId).min(1).max(20), constraints,
};
const difficultyScope = z.object({ ...lessonScopeFields, prerequisiteLessonIds: z.array(lessonId).max(500) }).strict();
const assessmentCriteria = z.object({
  claimScope: z.literal("this_lesson_only"), minimumAccuracy: z.number().min(0.8).max(1),
  minimumDistinctTasks: z.number().int().min(5).max(10), minimumIndependentAttempts: z.number().int().min(5),
  promptedAnswersCountAsIndependent: z.literal(false), requiresObservedConfirmation: z.boolean(),
}).strict();

export const progressiveDifficultyPolicySchema = z.object({
  schemaVersion: z.literal("mira.learning.difficulty-policy.v1"),
  policyVersion: z.literal("mira.learning.progressive-difficulty-policy.v1"),
  gradeCode: grade, subject, skillId: lessonId, difficultyCode: z.literal("basic"), curriculumVersion,
  curriculumIdentitySha256: sha, lessonSha256: sha,
  objectiveRuleVersion: z.literal("mira.learning.progressive-host-validation.v1"),
  mode: z.enum(["progressive_objective", "progressive_observed"]), lessonScope: difficultyScope,
  complexity: z.object({
    scope: z.literal("current_grade_current_lesson"),
    reasoningScope: z.literal("direct_application_of_taught_lesson_objectives"), maxCoreNewTargets: z.literal(1),
    assessmentOperation: z.enum(["independent_lesson_tasks", "parent_observation"]), requirements: strings.min(1),
  }).strict(),
  assessment: z.object({
    mode, criteria: assessmentCriteria, evidenceKinds: z.array(evidenceKind).max(4),
    autoMasteryEligible: z.boolean(), manualConfirmationRequired: z.boolean(),
    semanticScoringAuthority: z.enum(["independent_answer_blind_review", "none"]),
  }).strict(), policySha256: sha,
}).strict().superRefine((policy, ctx) => {
  const objective = policy.assessment.mode === "objective";
  const match = /^(ZH|M|EN)([1-6])/.exec(policy.skillId);
  if (!match) return; // The lesson ID schema already reports malformed identities.
  const expectedSubject = { ZH: "chinese", M: "math", EN: "english" }[match[1]];
  const scope = policy.lessonScope;
  if (policy.gradeCode !== `primary_${match[2]}` || policy.subject !== expectedSubject
    || scope.unitId !== policy.skillId.split(".")[0]
    || !sameProgressiveValue(scope.introducedKnowledgeIds, [policy.skillId])
    || policy.mode !== (objective ? "progressive_objective" : "progressive_observed")
    || policy.complexity.assessmentOperation !== (objective ? "independent_lesson_tasks" : "parent_observation")
    || policy.assessment.autoMasteryEligible !== objective || policy.assessment.manualConfirmationRequired === objective
    || policy.assessment.criteria.requiresObservedConfirmation === objective
    || policy.assessment.semanticScoringAuthority !== (objective ? "independent_answer_blind_review" : "none")
    || Boolean(policy.assessment.evidenceKinds.length) !== objective
    || !sameProgressiveValue(policy.assessment.evidenceKinds, scope.constraints.assessmentEvidenceKinds)
    || scope.constraints.assessmentEvidenceScope !== (objective ? "declared_objective_only" : "observed_performance")) {
    ctx.addIssue({ code: "custom", message: "分级难度策略必须绑定本年级、本课次与实际验收模式" });
  }
});

const questionFields = { id, prompt: text, knowledgeIds: z.array(lessonId).min(1).max(500) };
const publicQuestion = z.discriminatedUnion("type", [
  z.object({ ...questionFields, type: z.literal("single_choice"),
    choices: z.array(z.object({ id, label: text }).strict()).min(2).max(32) }).strict(),
  z.object({ ...questionFields, type: z.literal("tap_objects"),
    objects: z.array(z.object({ id, shape: z.enum(["circle", "square", "triangle"]),
      color: z.enum(["red", "blue", "yellow", "green"]) }).strict()).min(1).max(20) }).strict(),
]);
const teachingMaterial = z.object({ text, knowledgeIds: z.array(lessonId).min(1).max(500) }).strict();
const step = z.object({ ...teachingMaterial.shape,
  phase: z.enum(["teach", "example", "guided", "independent", "observe", "recap"]),
  requiresKnowledgeIds: z.array(lessonId).max(500).optional(), questionId: id.optional(),
}).strict();

export const progressiveRuntimeAuthoringScopeSchema = z.object({
  schemaVersion: z.literal("mira.learning.progressive-runtime-authoring-scope.v1"),
  policyVersion: z.literal("mira.learning.progressive-runtime-authoring-policy.v1"), issuer: z.literal("mira_backend"),
  progressiveLesson: progressiveBindingSchema,
  sourceGenerationRequestId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,112}$/), sourceProviderContentSha256: sha,
  lessonScope: z.object({ ...lessonScopeFields, gradeCode: grade, subject }).strict(),
  allowedLearningActions: strings.min(1), forbiddenLearningActions: strings.min(1),
  assessmentProtection: z.object({
    materialSource: z.literal("teachingBrief.lesson.questions"),
    protectedQuestions: z.array(z.object({ questionId: id, phase: z.enum(["guided", "independent"]),
      publicQuestionSha256: sha }).strict()).max(14),
    allowedUse: z.literal("exact_registered_quiz_role_only"), rules: strings.min(1),
  }).strict(), scopeSha256: sha,
}).strict();

export const progressiveTeachingBriefSchema = z.object({
  schemaVersion: z.literal("mira.learning.formal-runtime-teaching-brief.progressive.v1"), sourceCourseContentSha256: sha,
  course: z.object({ id, version: id, gradeCode: grade, subject, skillId: lessonId,
    title: text, objective: text, difficultyCode: z.literal("basic") }).strict(),
  progressiveLesson: progressiveBindingSchema, difficultyPolicy: progressiveDifficultyPolicySchema,
  runtimeAuthoringScope: progressiveRuntimeAuthoringScopeSchema.optional(),
  lesson: z.object({
    intro: text, estimatedMinutes: z.number().int().min(5).max(30), assessmentMode: mode,
    autoMasteryEligible: z.boolean(), manualConfirmationRequired: z.boolean(),
    progressiveFlow: z.array(step).min(4).max(20), questions: z.array(publicQuestion).max(14),
    teachingFlow: z.object({
      schemaVersion: z.literal("mira.learning.progressive-teaching-flow.v1"),
      teach: z.object({ title: text, sayText: text, keyPoints: strings.min(1) }).strict(),
      examples: z.array(teachingMaterial).min(1).max(20), observations: z.array(teachingMaterial).max(20),
      guidedQuestionIds: z.array(id).max(4), independentQuestionIds: z.array(id).max(10),
      recap: z.object({ sayText: text }).strict(),
    }).strict(),
  }).strict(),
  authority: z.object({ source: z.literal("locked_learning_course"), answerContractProvided: z.literal(false),
    scoringRulesProvided: z.literal(false), providerSecretsProvided: z.literal(false) }).strict(),
}).strict().superRefine((brief, ctx) => {
  const { course, difficultyPolicy: policy, progressiveLesson: binding, lesson, runtimeAuthoringScope: scope } = brief;
  const flow = lesson.teachingFlow, steps = lesson.progressiveFlow, objective = lesson.assessmentMode === "objective";
  const reject = (path: (string | number)[], message: string) => ctx.addIssue({ code: "custom", path, message });
  if (binding.lessonId !== course.skillId || binding.curriculumVersion !== policy.curriculumVersion
    || binding.identitySha256 !== policy.curriculumIdentitySha256 || binding.lessonSha256 !== policy.lessonSha256
    || policy.skillId !== course.skillId || policy.gradeCode !== course.gradeCode || policy.subject !== course.subject
    || binding.assessmentMode !== lesson.assessmentMode || policy.assessment.mode !== lesson.assessmentMode
    || lesson.autoMasteryEligible !== objective || lesson.manualConfirmationRequired === objective) {
    reject(["progressiveLesson"], "课次、年级、学科、难度策略和验收身份必须一致");
  }
  const ids = lesson.questions.map(q => q.id);
  const registered = [...flow.guidedQuestionIds, ...flow.independentQuestionIds];
  const questionSteps = steps.filter(s => (s.phase === "guided" || s.phase === "independent") && s.questionId);
  const phases = steps.map(s => s.phase), firstPractice = phases.findIndex(p => ["guided", "independent", "observe"].includes(p));
  if (new Set(ids).size !== ids.length || new Set(registered).size !== registered.length
    || !sameProgressiveValue([...ids].sort(), [...registered].sort())
    || !sameProgressiveValue(flow.guidedQuestionIds, questionSteps.filter(s => s.phase === "guided").map(s => s.questionId))
    || !sameProgressiveValue(flow.independentQuestionIds, questionSteps.filter(s => s.phase === "independent").map(s => s.questionId))
    || phases[0] !== "teach" || phases.indexOf("example") < 0 || firstPractice < 0 || firstPractice < phases.indexOf("example")
    || (objective && (flow.guidedQuestionIds.length < 1 || flow.independentQuestionIds.length < policy.assessment.criteria.minimumDistinctTasks
      || phases.indexOf("guided") > phases.indexOf("independent") || flow.observations.length > 0))
    || (!objective && (ids.length > 0 || registered.length > 0 || flow.observations.length < 1))) {
    reject(["lesson", "teachingFlow"], "分级课堂必须先讲解示范，再引导和足量独立练习；观察课不能提供自动评分题");
  }
  const materials = (phase: string) => steps.filter(s => s.phase === phase).map(s => ({ text: s.text, knowledgeIds: s.knowledgeIds }));
  if (!sameProgressiveValue(flow.examples, materials("example")) || !sameProgressiveValue(flow.observations, materials("observe"))
    || flow.teach.title !== course.title || flow.teach.sayText !== steps.filter(s => s.phase === "teach").map(s => s.text).join("\n")
    || !sameProgressiveValue(flow.teach.keyPoints, policy.lessonScope.learningObjectives)) {
    reject(["lesson", "teachingFlow"], "教学流程必须对应冻结教学步骤和本课目标");
  }
  for (const [i, question] of lesson.questions.entries()) {
    const items = question.type === "single_choice" ? question.choices : question.objects;
    if (new Set(items.map(item => item.id)).size !== items.length || !question.knowledgeIds.includes(course.skillId))
      reject(["lesson", "questions", i], "公开题目须有唯一选项或物体，并绑定本课知识");
  }
  if (scope) {
    const expectedScope = Object.fromEntries(Object.keys(lessonScopeFields)
      .map(key => [key, policy.lessonScope[key as keyof typeof lessonScopeFields]]));
    const protectedQuestions = scope.assessmentProtection.protectedQuestions;
    if (!sameProgressiveValue(scope.progressiveLesson, binding)
      || !sameProgressiveValue(scope.lessonScope, { ...expectedScope, gradeCode: course.gradeCode, subject: course.subject })
      || protectedQuestions.length !== ids.length
      || protectedQuestions.some((q, i) => q.questionId !== ids[i]
        || q.phase !== questionSteps.find(s => s.questionId === q.questionId)?.phase)) {
      reject(["runtimeAuthoringScope"], "课堂编写范围与受保护题目必须绑定同一课次和教学阶段");
    }
  }
});
