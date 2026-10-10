import { z } from "zod";
import { homeworkReviewContextSchema, homeworkTutorItemSchema, homeworkStudentCorrectionSchema, homeworkTeachingQualitySchema } from "./homework-tutor";

export const homeworkIdSchema = z.string().regex(/^hw_[a-f0-9]{32}$/);
export const homeworkItemIdSchema = z.string().regex(/^hwi_[a-f0-9]{32,64}$/);
export const homeworkPageIdSchema = z.string().regex(/^hwp_[a-f0-9]{32}$/);
const homeworkRegionSchema = z.object({
  x: z.number().min(0).max(1), y: z.number().min(0).max(1),
  width: z.number().positive().max(1), height: z.number().positive().max(1),
}).refine((region) => region.x + region.width <= 1.000001 && region.y + region.height <= 1.000001);
export type HomeworkPaperRegion = z.infer<typeof homeworkRegionSchema>;
type PaperElement = { id: string; region: HomeworkPaperRegion | null; geometryVerified: boolean };
export type HomeworkPaperQuestion = PaperElement & {
  label: string | null; prompt: string;
  illustrations: PaperElement[];
  options: (PaperElement & { label: string | null; text: string })[];
  tables: (PaperElement & { text: string })[];
  answers: { itemId: string; index: number | null; count: number; region: HomeworkPaperRegion | null; geometryVerified: boolean }[];
  children: HomeworkPaperQuestion[];
};
const paperElement = z.object({ id: z.string(), region: homeworkRegionSchema.nullable(), geometryVerified: z.boolean() });
export const homeworkPaperQuestionSchema: z.ZodType<HomeworkPaperQuestion> = z.lazy(() => z.object({
  id: z.string().regex(/^hwq_[a-f0-9]{32}$/), label: z.string().nullable(), prompt: z.string(),
  region: homeworkRegionSchema.nullable(), geometryVerified: z.boolean(),
  illustrations: z.array(paperElement),
  options: z.array(paperElement.extend({ label: z.string().nullable(), text: z.string() })),
  tables: z.array(paperElement.extend({ text: z.string() })),
  answers: z.array(z.object({ itemId: homeworkItemIdSchema, index: z.number().int().positive().nullable(), count: z.number().int().min(0), region: homeworkRegionSchema.nullable(), geometryVerified: z.boolean() })),
  children: z.array(homeworkPaperQuestionSchema),
}));
const paperCoverage = z.object({ status: z.enum(["ready", "partial", "unavailable"]), issues: z.array(z.string()) });
export const homeworkPaperStructureSchema = z.object({
  schemaVersion: z.literal("mira.homework-paper-structure.v1"), projectionVersion: z.string(), sourceDigest: z.string().regex(/^[a-f0-9]{64}$/),
  coverage: paperCoverage.extend({ linkedAnswers: z.number().int().min(0), totalAnswers: z.number().int().min(0) }),
  pages: z.array(z.object({ pageId: homeworkPageIdSchema, geometryVerified: z.boolean(), frameWidth: z.number().int().positive().optional(), frameHeight: z.number().int().positive().optional(), coverage: paperCoverage, questions: z.array(homeworkPaperQuestionSchema), unassignedItemIds: z.array(homeworkItemIdSchema) })),
});
export const homeworkPageSchema = z.object({
  id: homeworkPageIdSchema, order: z.number().int().min(0), rotation: z.union([z.literal(0), z.literal(90), z.literal(180), z.literal(270)]),
  crop: homeworkRegionSchema.nullable(), width: z.number().int().positive(), height: z.number().int().positive(),
  status: z.string(), error: z.string().nullable(), assetUrl: z.string(),
});
const voiceAsset = z.object({ assetUrl: z.string(), status: z.string(), mimeType: z.string().nullable().optional() });
export const homeworkEssayReviewSchema = z.object({
  status: z.enum(["ready", "pending", "failed"]), scope: z.literal("guidance_only"), countsForAbility: z.literal(false),
  suggestions: z.array(z.object({
    id: z.string(), type: z.string(), subType: z.string(), origin: z.string(), replace: z.string(), message: z.string(),
    pageId: homeworkPageIdSchema, region: homeworkRegionSchema.nullable().optional(),
  })),
});
export const homeworkItemSchema = z.object({
  id: homeworkItemIdSchema, revision: z.number().int(), prompt: z.string(), status: z.string(),
  readyForStudent: z.boolean(), correctionStatus: z.string(), hintViewed: z.boolean(), explanationViewed: z.boolean(),
  tutorAvailable: z.boolean().optional(), questionType: z.string().optional(), assessmentMethod: z.string().optional(),
  studentCorrection: homeworkStudentCorrectionSchema.optional(), latestTutorTeachingQuality: homeworkTeachingQualitySchema.nullable().optional(),
  answerMode: z.enum(["picture_choice", "numeric", "spoken"]).nullable().optional(),
  hint: z.string().optional(), explanation: z.string().optional(),
  expectedAnswer: z.string().optional(),
  reviewContext: homeworkReviewContextSchema.optional(),
  picture: z.object({ kind: z.literal("quantity_arithmetic"), operation: z.enum(["add", "subtract"]), left: z.number().int().min(0).max(20), right: z.number().int().min(0).max(20), choices: z.array(z.object({ id: z.string(), count: z.number().int().min(0).max(20) })).min(2).max(5) }).nullable().optional(),
  voice: z.object({ prompt: voiceAsset.optional(), hint: voiceAsset.optional(), explanation: voiceAsset.optional(), success: voiceAsset.optional(), retry: voiceAsset.optional() }),
});
export const homeworkSubmissionSchema = z.object({
  id: homeworkIdSchema, title: z.string(), gradeCode: z.string(), subject: z.string(), revision: z.number().int(), status: z.string(), error: z.string().nullable().optional(),
  processing: z.boolean().optional(), retryAllowed: z.boolean().optional(), retryReason: z.string().nullable().optional(),
  source: z.string().optional(),
  analysisKind: z.enum(["questions", "essay"]).optional(),
  essayReview: homeworkEssayReviewSchema.nullable().optional(),
  originalSummary: z.object({ total: z.number(), correct: z.number(), incorrect: z.number(), blank: z.number(), pending: z.number(), unsupported: z.number() }).optional(),
  originalPaperSummary: z.object({ total: z.number().int().min(0), correct: z.number().int().min(0), incorrect: z.number().int().min(0), unknown: z.number().int().min(0), blank: z.number().int().min(0).optional(), countsForAbility: z.literal(false).optional() }).optional(),
  providerVerdictSummary: z.object({ total: z.number().int().min(0), correct: z.number().int().min(0), incorrect: z.number().int().min(0), unknown: z.number().int().min(0) }).optional(),
  provisionalPaperSummary: z.object({ total: z.number().int().min(0), correct: z.number().int().min(0), incorrect: z.number().int().min(0), unknown: z.number().int().min(0), blank: z.number().int().min(0), countsForAbility: z.literal(false) }).optional(),
  studentSummary: z.object({ ready: z.number(), awaitingMedia: z.number(), unsupportedCorrection: z.number().optional(), corrected: z.number(), selfReportedCompleted: z.number().int().min(0).optional() }).optional(),
  pages: z.array(homeworkPageSchema).default([]),
  tutorItems: z.array(homeworkTutorItemSchema).default([]),
  originalPaperItems: z.array(homeworkTutorItemSchema).optional(),
  paperStructure: homeworkPaperStructureSchema.optional(),
  items: z.array(homeworkItemSchema), summary: z.object({ total: z.number(), corrected: z.number(), incorrect: z.number(), selfReportedCompleted: z.number().int().min(0).optional() }),
  createdAt: z.number(), updatedAt: z.number(), readyForStudent: z.boolean(),
});
export const captureTaskSchema = z.object({ taskId: z.string(), title: z.string(), available: z.boolean(), unavailableReason: z.string().optional() });
export const homeworkListSchema = z.object({ ok: z.literal(true), enabled: z.boolean().optional(), submissions: z.array(homeworkSubmissionSchema), captureTasks: z.array(captureTaskSchema).default([]) });
export const homeworkDetailSchema = z.object({ ok: z.literal(true), submission: homeworkSubmissionSchema, feedback: z.object({ correct: z.boolean(), attempt: z.number(), scope: z.string(), audioKind: z.enum(["success", "retry"]) }).optional() });
export const homeworkActionSchema = z.union([
  z.object({ itemRevision: z.number().int().positive(), action: z.enum(["hint", "explanation"]) }).strict(),
  z.object({ itemRevision: z.number().int().positive(), action: z.enum(["self_complete", "reopen"]), idempotencyKey: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/) }).strict(),
]);
export const homeworkAnswerSchema = z.object({ itemRevision: z.number().int().positive(), answer: z.string().min(1).max(128), idempotencyKey: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/) }).strict();
export type HomeworkSubmission = z.infer<typeof homeworkSubmissionSchema>;
export type HomeworkItem = z.infer<typeof homeworkItemSchema>;
export type HomeworkPage = z.infer<typeof homeworkPageSchema>;
export type HomeworkDetail = z.infer<typeof homeworkDetailSchema>;
export function homeworkAudioPath(value: string | undefined, submissionId: string, itemId: string): string | null {
  const prefix = `/api/v2/student/learning/homework/${submissionId}/items/${itemId}/audio/`;
  if (!value?.startsWith(prefix) || !["prompt", "hint", "explanation", "success", "retry"].includes(value.slice(prefix.length))) return null;
  return value.replace("/api/v2/student/", "/api/");
}
export function homeworkImagePath(value: string | undefined, submissionId: string, pageId: string): string | null {
  if (!homeworkIdSchema.safeParse(submissionId).success || !homeworkPageIdSchema.safeParse(pageId).success) return null;
  const expected = `/api/v2/student/learning/homework/${submissionId}/pages/${pageId}/image`;
  return value === expected ? `/api/learning/homework/${submissionId}/pages/${pageId}/image` : null;
}
