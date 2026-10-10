import { z } from "zod";

const region = z.object({ x: z.number().min(0).max(1), y: z.number().min(0).max(1), width: z.number().positive().max(1), height: z.number().positive().max(1) }).refine(value => value.x + value.width <= 1.000001 && value.y + value.height <= 1.000001);
export const homeworkStudentQualitySchema = z.object({
  status: z.enum(["verified", "needs_review"]), reason: z.string(), method: z.string(), countsForAbility: z.literal(false),
});
// Teaching may guide a located source question without certifying its paper
// grade. Keep this tier separate from the formal grading quality above.
export const homeworkTeachingQualitySchema = homeworkStudentQualitySchema.extend({
  status: z.enum(["verified", "guidance", "needs_review"]),
});
export const homeworkStudentCorrectionSchema = z.object({
  status: z.enum(["needs_review", "corrected", "needs_practice", "in_progress", "not_started", "self_reported"]),
  answerEvaluationAllowed: z.boolean(), lastAnswer: z.string(), attempts: z.number().int().min(0), correct: z.boolean().nullable(), updatedAt: z.number().nullable(),
  hintViewed: z.boolean(), explanationViewed: z.boolean(), tutorViewed: z.boolean(),
  independent: z.null(), scope: z.literal("same_question_correction"), countsForAbility: z.literal(false),
  lastAnswerTurnId: z.string().regex(/^hwt_[a-f0-9]{32,64}$/).nullable(), correctedAt: z.number().nullable(),
  selfReportedCompleted: z.boolean().optional(), selfReportedCompletedAt: z.number().nullable().optional(),
});
export const homeworkReviewContextSchema = z.object({
  pageId: z.string().regex(/^hwp_[a-f0-9]{32}$/), region: region.nullable(),
  originalAnswer: z.string().optional(), originalOrdinal: z.number().int().positive(),
  sourceQuestionLabel: z.string().max(120).nullable().optional(),
  sourcePath: z.array(z.string()).optional(), answerIndex: z.number().int().positive().nullable().optional(), answerCount: z.number().int().min(0).optional(),
  sourceHierarchy: z.object({ schemaVersion: z.string(), receiptIndex: z.number().int().positive().nullable(), markPath: z.array(z.number().int().positive()), sourcePath: z.array(z.string()), hierarchyVerified: z.boolean().optional(),
    answerIndex: z.number().int().positive().nullable(), answerCount: z.number().int().min(0), scope: z.literal("answer_blank"), questionTextScope: z.enum(["shared_question", "single_answer", "image_only"]),
  }).optional(),
  answerState: z.enum(["written", "blank", "unclear", "drawing"]).optional(),
  recognitionNeedsConfirmation: z.boolean().optional(), recognitionConfirmed: z.boolean().optional(),
  grading: z.object({
    status: z.enum(["correct", "incorrect", "unknown"]),
    referenceAnswer: z.string().optional(), analysis: z.string().optional(),
    knowledgePoints: z.array(z.string()).default([]), answerRegion: region.nullable().optional(),
    geometryVerified: z.boolean(), source: z.string().optional(), provider: z.string().optional(), countsForAbility: z.boolean().optional(),
    sourceValidationTrusted: z.boolean().optional(), referenceScope: z.literal("answer_blank").optional(),
    providerIsCorrect: z.boolean().nullable().optional(), answerState: z.enum(["written", "blank", "unclear"]).optional(),
    studentQuality: homeworkStudentQualitySchema.optional(),
    referenceGate: z.object({ available: z.boolean(), method: z.string(), status: z.enum(["provider_consistent", "exact", "human_verified", "needs_review"]) }).optional(),
    providerVerdict: z.object({ status: z.enum(["correct", "incorrect"]), source: z.literal("tencent"), provisional: z.literal(true), countsForAbility: z.literal(false) }).optional(),
    providerVerdictBlockedReason: z.string().optional(),
  }).optional(),
});
export const homeworkTutorTurnIdSchema = z.string().regex(/^hwt_[a-f0-9]{32,64}$/);
const assessment = z.object({ status: z.enum(["correct", "incorrect", "needs_confirmation", "guidance_only"]), method: z.literal("ai_guidance"), countsForAbility: z.literal(false), originalAnswerObserved: z.boolean().optional() });
export const homeworkTutorItemSchema = z.object({
  id: z.string().regex(/^hwi_[a-f0-9]{32,64}$/), pageId: z.string().regex(/^hwp_[a-f0-9]{32}$/).optional(), revision: z.number().int().positive(), prompt: z.string(), status: z.string(), type: z.string().nullable().optional(), tutorAvailable: z.boolean(), assessmentMethod: z.string().nullable().optional(), tutorAssessment: assessment.nullable().optional(),
  reviewContext: homeworkReviewContextSchema.optional(),
  studentCorrection: homeworkStudentCorrectionSchema.optional(),
  latestTutorTeachingQuality: homeworkTeachingQualitySchema.nullable().optional(),
  answerMode: z.enum(["picture_choice", "numeric", "spoken"]).nullable().optional(),
});
const visual = z.object({
  kind: z.enum(["paper_region", "quantity", "groups", "shapes", "choices"]), region: region.nullable().optional(), count: z.number().int().min(0).max(100).optional(),
  groups: z.array(z.number().int().min(0).max(100)).max(12).optional(),
  shapes: z.array(z.object({ shape: z.enum(["circle", "triangle", "square", "rectangle"]), count: z.number().int().min(1).max(20), color: z.enum(["amber", "green", "blue", "red"]).optional() })).max(8).optional(),
  choices: z.array(z.object({ id: z.string().max(40), label: z.string().max(100).optional(), region: region.optional(), count: z.number().int().min(0).max(100).optional() })).max(6).optional(),
});
export const homeworkTutorResponseSchema = z.object({ ok: z.literal(true), tutor: z.object({ itemId: z.string(), itemRevision: z.number().int().positive(), enabled: z.boolean(), voiceAvailable: z.boolean(),
  correction: homeworkStudentCorrectionSchema.optional(),
  remainingTurnsPerItem: z.number().int().min(0).optional(), remainingCallsPerSubmission: z.number().int().min(0).optional(), turns: z.array(z.object({
  id: homeworkTutorTurnIdSchema, requestKey: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/).optional(), mode: z.enum(["explain", "followup", "answer"]), message: z.string(), status: z.enum(["queued", "working", "ready", "unknown", "failed"]), teacherText: z.string(), errorCode: z.string().nullable().optional(),
  steps: z.array(z.object({ id: z.string().max(80), text: z.string().max(1000), visual })).max(8), assessment: assessment.nullable().optional(), audio: z.object({ status: z.enum(["ready", "pending", "unavailable"]), assetUrl: z.string().optional(), errorCode: z.string().nullable().optional() }), createdAt: z.number(),
  teachingScope: z.literal("original_image_guidance").optional(),
  teachingQuality: homeworkTeachingQualitySchema.optional(),
  replyReady: z.boolean().optional(),
  reviewState: z.enum(["required", "not_required"]).optional(),
  reviewRetryAllowed: z.boolean().optional(),
  reviewReasonCode: z.string().max(120).optional(),
  sourceConfirmationOnly: z.boolean().optional(),
  sourceImageReviewRequired: z.boolean().optional(),
  feedbackTarget: z.enum(["original_question", "current_student_message"]).optional(),
  gradingReferenceComparison: z.object({ status: z.enum(["consistent", "conflict", "unverified"]), reason: z.string(), referenceAnswer: z.string().optional(), teacherAnswer: z.string().optional() }).optional(),
  sourceCheck: z.object({ status: z.enum(["matched", "mismatch", "unclear"]), reason: z.string().optional(),
    prompt: z.string().optional(), studentAnswer: z.string().optional(), basis: z.literal("original_image").optional(),
    questionLocated: z.boolean().optional(), questionReadable: z.boolean().optional(), studentAnswerReadable: z.boolean().optional(),
    answerLocated: z.boolean().optional(), answerOrdinal: z.number().int().min(1).max(200).optional(), questionRegion: region.optional(),
  }).optional(),
})).max(100) }) });
export const homeworkTutorRequestSchema = z.object({ itemRevision: z.number().int().positive(), idempotencyKey: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/), mode: z.enum(["explain", "followup", "answer"]), message: z.string().max(1000) }).strict().refine(value => value.mode === "explain" || !!value.message.trim());
export const homeworkTranscriptionSchema = z.object({ ok: z.literal(true), transcription: z.object({ id: z.string(), status: z.enum(["ready", "queued", "working", "unknown", "failed"]), transcript: z.string().max(1000), errorCode: z.string().nullable().optional() }) });
export type HomeworkTutorResponse = z.infer<typeof homeworkTutorResponseSchema>;
export type HomeworkStudentCorrection = z.infer<typeof homeworkStudentCorrectionSchema>;
export type HomeworkTutorTurn = HomeworkTutorResponse["tutor"]["turns"][number];
export type HomeworkTutorStep = HomeworkTutorTurn["steps"][number];
export type HomeworkTutorItem = z.infer<typeof homeworkTutorItemSchema>;
export function homeworkTutorAudioPath(value: string | undefined, submissionId: string, itemId: string, turnId: string) {
  const expected = `/api/v2/student/learning/homework/${submissionId}/items/${itemId}/tutor/${turnId}/audio`;
  return value === expected && homeworkTutorTurnIdSchema.safeParse(turnId).success ? expected.replace("/api/v2/student/", "/api/") : null;
}
