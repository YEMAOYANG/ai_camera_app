import { z } from "zod";
import { homeworkIdSchema, homeworkItemIdSchema, homeworkPageIdSchema, homeworkPageSchema } from "./homework";

export const reviewId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/);
const requestId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
const pictureArt = z.object({ src: z.string(), alt: z.string().default("") });
export const quantityVisual = z.object({ kind: z.literal("quantity_arithmetic"), operation: z.enum(["add", "subtract"]), left: z.number().int().min(0).max(20), right: z.number().int().min(0).max(20), choices: z.array(z.object({ id: z.string(), count: z.number().int().min(0).max(20) })) });
export const homeworkOriginalVisual = z.object({
  kind: z.literal("homework_original"), submissionId: homeworkIdSchema, pageId: homeworkPageIdSchema,
  width: z.number().int().positive(), height: z.number().int().positive(),
  region: homeworkPageSchema.shape.crop, answerRegion: homeworkPageSchema.shape.crop,
});
export const reviewVisual = z.union([
  homeworkOriginalVisual,
  quantityVisual,
  z.object({ art: pictureArt }),
  z.object({ setting: z.string(), skyObject: z.string(), ground: z.string(), cast: z.array(z.string()), speaker: z.string().optional(), listener: z.string().optional(), activity: z.string().optional() }),
]);
export const reviewQuestionSchema = z.object({
  id: z.string(), renderer: z.enum(["tiandiren", "picture_choices", "quantity_arithmetic", "homework_original"]),
  prompt: z.string(), visual: reviewVisual,
  options: z.array(z.object({ value: z.string(), label: z.string(), picture: z.union([z.string(), pictureArt, z.object({ count: z.number().int().min(0).max(20) })]) })),
  promptAudioUrl: z.string(), hint: z.string().nullable().default(null), hintAudioUrl: z.string().nullable().default(null),
  explanation: z.string().nullable().default(null), explanationAudioUrl: z.string().nullable().default(null),
  selectedResponse: z.string().nullable().default(null), helpUsed: z.boolean().default(false),
  evidenceMode: z.string().optional(),
  target: z.string().optional(),
  homeworkSource: z.object({ submissionId: homeworkIdSchema, itemId: homeworkItemIdSchema, itemRevision: z.number().int().positive() }).optional(),
}).superRefine((value, context) => {
  if (value.renderer === "homework_original" || ("kind" in value.visual && value.visual.kind === "homework_original")) {
    if (value.renderer !== "homework_original" || !("kind" in value.visual) || value.visual.kind !== "homework_original" || !value.homeworkSource || value.visual.submissionId !== value.homeworkSource.submissionId || value.options.length !== 0) {
      context.addIssue({ code: "custom", message: "原图复习缺少一致的作业来源" });
    }
  }
});
export const reviewSummarySchema = z.object({
  id: reviewId, taskId: z.string().nullable().optional(), title: z.string(), status: z.string(),
  weekStart: z.string(), appointmentRevision: z.number().int(), revision: z.number().int(),
  scheduledAt: z.number().nullable(), estimatedMinutes: z.number(),
  coverage: z.object({ lessonCount: z.number(), questionCount: z.number(), contentGap: z.boolean(), notes: z.array(z.string()).default([]) }),
  totalQuestions: z.number(), currentIndex: z.number(), correctCount: z.number(), independentCorrectCount: z.number(),
  completedAt: z.number().nullable(),
});
export const reviewListSchema = z.object({ ok: z.literal(true), reviews: z.array(reviewSummarySchema) });
export const reviewResponseSchema = z.object({
  ok: z.literal(true), review: reviewSummarySchema, currentQuestion: reviewQuestionSchema.nullable(),
  feedback: z.object({ correct: z.boolean().optional(), independent: z.boolean().optional(), message: z.string().default(""), audioUrl: z.string().nullable().optional(), hint: z.string().optional(), explanation: z.string().optional(), explanationAudioUrl: z.string().nullable().optional(), answered: z.boolean().optional() }).nullable().default(null),
});
export const reviewActionSchema = z.object({
  action: z.enum(["start", "hint", "explanation", "pause", "snooze", "next", "defer_today"]),
  requestId, revision: z.number().int().nonnegative(), minutes: z.literal(20).optional(),
}).strict();
export const reviewAnswerSchema = z.object({ questionId: z.string().min(1).max(160), response: z.string().max(4000), requestId, revision: z.number().int().nonnegative() }).strict();
export type ReviewSummary = z.infer<typeof reviewSummarySchema>;
export type ReviewResponse = z.infer<typeof reviewResponseSchema>;

/** Media always stays on the student cookie boundary; never accept remote URLs. */
export function reviewAudioPath(value: string | undefined | null, id: string): string | null {
  if (!value) return null;
  const escaped = id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (new RegExp(`^/api/(?:v2/student/)?learning/reviews/${escaped}/media/[a-zA-Z0-9_.-]+$`).test(value)) {
    return value.replace("/api/v2/student/", "/api/");
  }
  return null;
}
