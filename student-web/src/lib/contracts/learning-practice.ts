import { z } from "zod";
import { learningQuestionSchema } from "./learning";

export const practiceStartSchema = z.object({
  requestId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/),
  subject: z.enum(["chinese", "math", "english"]),
  skillId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/).optional(),
  count: z.number().int().min(1).max(5).default(5),
}).strict();
export const practiceAnswerSchema = z.object({
  questionId: z.string().regex(/^[a-f0-9]{64}$/),
  response: z.union([z.string().max(4000), z.array(z.string().max(500)).max(20)]),
}).strict();
export const practiceResponseSchema = z.object({
  ok: z.literal(true), schemaVersion: z.literal("mira.learning.practice.v1"),
  fallbackPath: z.literal("/learning"), availableCount: z.number().int().nonnegative().optional(),
  message: z.string().optional(),
  session: z.object({
    id: z.string().regex(/^practice_[a-f0-9]{32}$/), gradeCode: z.string(),
    subject: z.enum(["chinese", "math", "english"]), skillId: z.string().nullable(),
    status: z.enum(["in_progress", "completed"]), currentQuestionIndex: z.number().int().min(0).max(5),
    totalQuestions: z.number().int().min(1).max(5), correctCount: z.number().int().min(0).max(5),
    currentQuestion: learningQuestionSchema.nullable(), completedAt: z.number().nullable(),
  }).nullable(),
  evaluation: z.object({
    questionId: z.string().regex(/^[a-f0-9]{64}$/), correct: z.boolean(), status: z.enum(["correct", "incorrect"]),
    message: z.string(), explanation: z.string(), evaluatorVersion: z.string(),
  }).optional(),
});
export type PracticeResponse = z.infer<typeof practiceResponseSchema>;
