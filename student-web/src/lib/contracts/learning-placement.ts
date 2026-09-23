import { z } from "zod";

import { learningChoiceSchema, learningQuestionSchema, learningSubjectSchema } from "@/lib/contracts/learning";
import { progressiveGradeSchema } from "@/lib/contracts/progressive-learning";

export const placementAttemptIdSchema = z.string().regex(/^placement_[a-f0-9]{32}$/);
const questionIdSchema = z.string().regex(/^placementq_[a-f0-9]{32}$/);
const lessonIdSchema = z.string().regex(/^(?:ZH|EN|M)[1-6][AB]\d{2}\.\d{2,}$/);
export const placementQuerySchema = z.object({ subject: learningSubjectSchema }).strict();
export const placementStartSchema = z.object({ lessonId: lessonIdSchema }).strict();
export const placementAnswerSchema = z.object({
  questionId: questionIdSchema,
  answer: z.union([z.string().min(1).max(4000), z.array(z.string().min(1).max(500)).min(1).max(20)]),
}).strict();

// Reject private answer, feedback and hint fields instead of silently passing
// them through a diagnostic response. The server alone evaluates each answer.
const placementQuestionSchema = learningQuestionSchema.extend({
  id: questionIdSchema,
  choices: z.array(learningChoiceSchema.strict()),
  objects: z.array(z.object({
    id: z.string().min(1),
    shape: z.enum(["circle", "square", "triangle"]),
    color: z.enum(["red", "blue", "yellow", "green"]),
  }).strict()).max(20).optional(),
}).strict();

export const placementResponseSchema = z.object({
  ok: z.literal(true),
  schemaVersion: z.literal("mira.learning.placement.v1"),
  subject: learningSubjectSchema,
  status: z.enum(["available", "preparing", "observation_required", "not_required", "needs_learning", "in_progress", "completed"]),
  message: z.string(),
  lesson: z.object({
    lessonId: lessonIdSchema,
    title: z.string().min(1),
    gradeCode: progressiveGradeSchema,
    subject: learningSubjectSchema,
    assessmentMode: z.enum(["objective", "observed"]),
  }).strict().nullable(),
  canStart: z.boolean(),
  attempt: z.object({
    id: placementAttemptIdSchema,
    status: z.enum(["in_progress", "completed"]),
    currentQuestionIndex: z.number().int().nonnegative(),
    totalQuestions: z.number().int().min(5),
    answeredCount: z.number().int().nonnegative(),
    currentQuestion: placementQuestionSchema.nullable(),
    result: z.object({
      passed: z.boolean(),
      correctCount: z.number().int().nonnegative(),
      totalQuestions: z.number().int().min(5),
      accuracy: z.number().min(0).max(1),
      masteryStatus: z.enum(["mastered", "needs_practice"]),
    }).strict().nullable(),
  }).strict().nullable(),
  fallbackPath: z.string().regex(/^\/learning\/path\?subject=(?:chinese|math|english)$/),
}).strict().superRefine((response, context) => {
  const attempt = response.attempt;
  if (response.lesson && response.lesson.subject !== response.subject
    || response.fallbackPath !== `/learning/path?subject=${response.subject}`) {
    context.addIssue({ code: "custom", message: "Placement subject mismatch" });
  }
  if (response.canStart && (response.status !== "available" || response.lesson?.assessmentMode !== "objective")) {
    context.addIssue({ code: "custom", path: ["canStart"], message: "Placement cannot start from this state" });
  }
  if (attempt && (attempt.status === "in_progress"
    ? !attempt.currentQuestion || attempt.result !== null || attempt.currentQuestionIndex !== attempt.answeredCount || attempt.answeredCount >= attempt.totalQuestions
    : attempt.currentQuestion !== null || !attempt.result || attempt.answeredCount !== attempt.totalQuestions || attempt.currentQuestionIndex !== attempt.totalQuestions)) {
    context.addIssue({ code: "custom", path: ["attempt"], message: "Invalid placement cursor" });
  }
  if (attempt?.result && (attempt.result.totalQuestions !== attempt.totalQuestions || attempt.result.correctCount > attempt.totalQuestions
    || Math.abs(attempt.result.accuracy - attempt.result.correctCount / attempt.result.totalQuestions) > 0.0001
    || attempt.result.passed !== (attempt.result.masteryStatus === "mastered"))) {
    context.addIssue({ code: "custom", path: ["attempt", "result"], message: "Invalid placement outcome" });
  }
});

export type PlacementResponse = z.infer<typeof placementResponseSchema>;
