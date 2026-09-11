import { z } from "zod";

const sha = z.string().regex(/^[0-9a-f]{64}$/);
const id = z.string().trim().min(1).max(255);
const text = z.string().trim().min(1).max(2000);
const selector = z.string().regex(/^#[A-Za-z][A-Za-z0-9_-]{0,98}$/);
const index = z.number().int().min(0).max(29);
const viewport = z.union([
  z.object({ width: z.literal(1280), height: z.literal(720) }).strict(),
  z.object({ width: z.literal(1024), height: z.literal(768) }).strict(),
]);
export const difficultyCodeSchema = z.enum(["basic", "standard", "challenge"]);
export const difficultyPolicySchema = z.object({
  schemaVersion: z.literal("mira.learning.difficulty-policy.v1"),
  gradeCode: z.string().regex(/^primary_[2-6]$/), subject: z.enum(["chinese", "math", "english"]),
  skillId: id, difficultyCode: difficultyCodeSchema,
  objectiveRuleVersion: z.literal("mira.learning.primary-2-6-objective-rules.v2"),
  mode: id, publicPromptExample: text, policySha256: sha,
  complexity: z.object({
    grammarVersion: z.literal("mira.learning.banded-objective-grammar.v1"),
    reasoningSteps: z.number().int().positive(), minEvidenceFacts: z.number().int().positive(),
    maxEvidenceFacts: z.number().int().positive(), assessmentOperation: id,
    requirements: z.array(text).optional(),
    operandBounds: z.union([
      z.object({ denominatorMax: z.literal(100) }).strict(),
      z.object({ totalPeople: z.tuple([z.literal(10), z.literal(1000)]),
        denominator: z.tuple([z.literal(2), z.literal(100)]),
        numerator: z.literal("positive and less than denominator"), participants: z.literal("integer"),
        percentDecimalPlacesMax: z.literal(1) }).strict(),
      z.object({ originalPrice: z.tuple([z.literal(10), z.literal(10000)]),
        firstDecreasePercent: z.tuple([z.literal(1), z.literal(50)]),
        secondIncreasePercent: z.tuple([z.literal(1), z.literal(30)]),
        finalPrice: z.literal("less than original price") }).strict(),
    ]).optional(),
  }).strict(),
}).strict();

const policyBase = {
  enabled: z.literal(true), profile: z.literal("primary-adaptive"),
  objectiveCoverageRequired: z.literal(true), demonstrationRequired: z.literal(true),
  learnerOperationRequired: z.literal(true), explanatoryFeedbackRequired: z.literal(true),
  independentJudgmentRequired: z.literal(true), finalSnapshotRequired: z.literal(true),
  renderedInteractionRequired: z.literal(true),
};
export const interactionDesignPolicySchema = z.union([
  z.object({ ...policyBase, schemaVersion: z.literal("mira.openmaic.interaction-design.v1"),
    policyId: z.literal("mira-primary-adaptive-interaction.v1") }).strict(),
  z.object({ ...policyBase, schemaVersion: z.literal("mira.openmaic.interaction-design.v2"),
    policyId: z.literal("mira-primary-multistate-interaction.v2"),
    visualReviewRequired: z.literal(true), visualRubricVersion: z.literal("mira.primary-teaching-visual.v1"),
    explorationPolicy: z.object({ schemaVersion: z.literal("mira.openmaic.multistate-exploration.v1"),
      minimumStates: z.literal(3), maximumStates: z.literal(5), resetRequired: z.literal(true),
      inputModes: z.tuple([z.literal("pointer"), z.literal("touch")]),
      mechanismRegistry: z.tuple([z.literal("fraction-ratio-percentage.v1"), z.literal("semantic-state-model.v1")]),
    }).strict(),
  }).strict(),
]);
const operation = z.discriminatedUnion("action", [
  z.object({ selector, action: z.literal("click") }).strict(),
  z.object({ selector, action: z.enum(["fill", "select"]), value: z.string().min(1).max(100) }).strict(),
]);
const stateBase = { id, operations: z.array(operation).min(1).max(3), resultText: text, explanationText: text };
const explorationBase = {
  schemaVersion: z.literal("mira.openmaic.multistate-exploration.v1"),
  diagramSelector: selector, feedbackSelector: selector,
  reset: z.object({ selector, stateId: id }).strict(),
};
const exploration = z.union([
  z.object({ ...explorationBase,
    mechanism: z.object({ kind: z.literal("fraction-ratio-percentage.v1"), numeratorSelector: selector,
      denominatorSelector: selector, decimalSelector: selector, percentSelector: selector,
      wholeSelector: selector, partSelector: selector }).strict(),
    states: z.array(z.object({ ...stateBase, numerator: z.number().int().positive().max(1000),
      denominator: z.number().int().positive().max(1000) }).strict()).min(3).max(5),
  }).strict(),
  z.object({ ...explorationBase, mechanism: z.object({ kind: z.literal("semantic-state-model.v1") }).strict(),
    states: z.array(z.object(stateBase).strict()).min(3).max(5) }).strict(),
]);
const objectiveBase = {
  objectiveIndex: index,
  demonstration: z.object({ sceneId: id, quote: text }).strict(),
  operation: z.object({ sceneId: id, controlSelector: selector, action: z.enum(["click", "fill", "range", "select"]),
    value: z.string().max(500).optional() }).strict(),
  feedback: z.object({ sceneId: id, selector, textIncludes: text, reasonQuote: text }).strict(),
  independentJudgment: z.object({ sceneId: id, questionId: id }).strict(),
  checks: z.array(z.object({ viewport, sceneSha256: sha, screenshotSha256: sha, domSha256: sha, probeId: id }).strict()).length(2),
};
const visualReview = z.object({
  schemaVersion: z.literal("mira.openmaic.visual-review.v1"), reviewerKind: z.literal("vision_model"),
  status: z.literal("passed"), rubricVersion: z.literal("mira.primary-teaching-visual.v1"),
  snapshotSha256: sha, teachingQualityContextSha256: sha, providerId: z.literal("deepseek"),
  modelId: z.literal("deepseek-v4-flash-vision-exp"), providerRequestIdHash: sha,
  providerResponseModelId: z.string().trim().min(1).max(200).optional(), receiptSha256: sha,
  sceneReviews: z.array(z.object({ sceneId: id, sceneSha256: sha, viewport, screenshotSha256: sha,
    legibility: z.literal("passed"), layout: z.literal("passed"), teachingGraphic: z.literal("passed"),
    interactionAffordance: z.literal("passed"), notes: text }).strict()).min(2).max(120),
}).strict();
const observationBase = { inputMode: z.enum(["pointer", "touch"]), resetPassed: z.literal(true) };
const observedState = { stateId: id, diagramSha256: sha, feedbackSha256: sha };
const explorationObservation = z.union([
  z.object({ ...observationBase, mechanism: z.literal("fraction-ratio-percentage.v1"),
    verification: z.literal("independent_numeric_svg"),
    states: z.array(z.object({ ...observedState, numeric: z.object({ numerator: z.number().int().positive(),
      denominator: z.number().int().positive(), decimal: z.number(), percent: z.number(), diagramRatio: z.number(),
    }).strict() }).strict()).min(3).max(5),
  }).strict(),
  z.object({ ...observationBase, mechanism: z.literal("semantic-state-model.v1"),
    verification: z.literal("structural_then_semantic_visual_review"),
    states: z.array(z.object(observedState).strict()).min(3).max(5),
  }).strict(),
]);
const receiptBase = {
  status: z.literal("passed"), sessionId: id, stageId: id, gradeBoundarySha256: sha,
  snapshotSha256: sha, planSha256: sha, teachingQualityReceiptSha256: sha, receiptSha256: sha,
};
export const interactionDesignReceiptSchema = z.discriminatedUnion("schemaVersion", [
  z.object({ ...receiptBase, schemaVersion: z.literal("mira.openmaic.interaction-design-receipt.v1"),
    policyId: z.literal("mira-primary-adaptive-interaction.v1"),
    objectives: z.array(z.object(objectiveBase).strict()).min(1).max(30) }).strict(),
  z.object({ ...receiptBase, schemaVersion: z.literal("mira.openmaic.interaction-design-receipt.v2"),
    policyId: z.literal("mira-primary-multistate-interaction.v2"), visualReview,
    objectives: z.array(z.object({ ...objectiveBase, exploration }).strict()).min(1).max(30),
    explorationChecks: z.array(z.object({ objectiveIndex: index, viewport, evidence: explorationObservation }).strict()).min(2).max(60),
  }).strict(),
]);
export const interactionDesignEvidenceSchema = z.object({ verified: z.literal(true), objectiveCount: z.number().int().min(1).max(30),
  planSha256: sha, receiptSha256: sha, snapshotSha256: sha }).strict();
export const requiredTeachingActionsSchema = z.array(z.object({ sceneId: id, actionId: id }).strict()).max(1200);
