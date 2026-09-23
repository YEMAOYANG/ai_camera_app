import { z } from "zod";

import { learningSubjectSchema } from "@/lib/contracts/learning";

export const progressiveGradeSchema = z.enum(["primary_1", "primary_2", "primary_3", "primary_4", "primary_5", "primary_6"]);
const lessonId = z.string().regex(/^(?:ZH|EN|M)[1-6][AB]\d{2}\.\d{2,}$/);
const identifiers = z.array(lessonId).max(1500);
const count = z.number().int().nonnegative();
const timestamp = z.number().nonnegative().nullable();
const courseSchema = z.object({ courseId: z.string().min(1), courseVersion: z.string().min(1) }).strict();

// This endpoint describes the path only. Strict objects at every level reject
// accidental question, answer, rubric, provider and token payloads at the BFF.
export const progressiveLessonSchema = z.object({
  lessonId,
  title: z.string().min(1),
  unitTitle: z.string().min(1),
  unitId: z.string().regex(/^(?:ZH|EN|M)[1-6][AB]\d{2}$/),
  gradeCode: progressiveGradeSchema,
  subject: learningSubjectSchema,
  phase: z.enum(["upper", "lower"]),
  sequence: z.number().int().positive(),
  assessmentMode: z.enum(["objective", "observed"]),
  observation: z.object({
    criteria: z.array(z.string().min(1)).min(1),
    canConfirm: z.boolean(),
    confirmationId: z.string().regex(/^obs_[a-f0-9]{64}$/).nullable(),
  }).strict().optional(),
  prerequisiteLessonIds: identifiers,
  status: z.enum(["locked", "available", "needs_practice", "mastered"]),
  canStart: z.boolean(),
  message: z.string(),
  blockedByLessonIds: identifiers,
  difficultyCode: z.enum(["basic", "standard", "challenge"]),
  independentEvidenceCount: count,
  independentCorrectCount: count,
  distinctAssessmentSets: count,
  accuracy: z.number().min(0).max(1).nullable(),
  masteredAt: timestamp,
  stabilityStatus: z.enum(["stable", "due", "not_due"]),
  stableAt: timestamp,
  course: courseSchema.nullable(),
  courseId: z.string().min(1).nullable(),
  courseVersion: z.string().min(1).nullable(),
}).strict().superRefine((lesson, context) => {
  if (lesson.canStart && (lesson.status === "locked" || lesson.blockedByLessonIds.length > 0)) {
    context.addIssue({ code: "custom", path: ["canStart"], message: "Locked lessons cannot be started" });
  }
  if (lesson.independentCorrectCount > lesson.independentEvidenceCount) {
    context.addIssue({ code: "custom", path: ["independentCorrectCount"], message: "Invalid independent evidence count" });
  }
  if ((lesson.course?.courseId ?? null) !== lesson.courseId || (lesson.course?.courseVersion ?? null) !== lesson.courseVersion) {
    context.addIssue({ code: "custom", path: ["course"], message: "Course identity mismatch" });
  }
});

const assessmentTaskSchema = z.object({
  lessonId,
  title: z.string().min(1),
  gradeCode: progressiveGradeSchema,
  subject: learningSubjectSchema,
  assessmentMode: z.enum(["objective", "observed"]),
  canAssess: z.boolean(),
  blockedByLessonIds: identifiers,
  kind: z.literal("prerequisite_assessment"),
}).strict();

export const progressivePathSchema = z.object({
  ok: z.literal(true).optional(),
  schemaVersion: z.literal("mira.learning.progressive-path.v1"),
  curriculumVersion: z.literal("mira.primary.progressive.v1"),
  gradeCode: progressiveGradeSchema,
  subject: learningSubjectSchema,
  lessons: z.array(progressiveLessonSchema).max(1500).optional(),
  currentGradeLessons: z.array(progressiveLessonSchema).max(1500),
  prerequisites: z.array(progressiveLessonSchema).max(1500),
  nextLesson: progressiveLessonSchema.nullable(),
  assessment: z.object({
    required: z.boolean(),
    missingLessonIds: identifiers,
    tasks: z.array(assessmentTaskSchema).max(1500),
    nextTask: assessmentTaskSchema.nullable(),
  }).strict(),
  masteryPolicy: z.object({
    independentQuestionCount: z.number().int().min(1),
    distinctAssessmentSets: z.number().int().min(1),
    minimumAccuracy: z.number().min(0).max(1),
    delayedReviewAfterHours: z.number().positive(),
    observedRequiresAuthorizedConfirmation: z.literal(true),
  }).strict(),
}).strict().superRefine((path, context) => {
  // Selecting a grade establishes its entry level. Missing lower-grade history
  // must never become a mandatory remedial route or fabricated mastery.
  if (path.prerequisites.length || path.assessment.required || path.assessment.missingLessonIds.length
    || path.assessment.tasks.length || path.assessment.nextTask !== null) {
    context.addIssue({ code: "custom", path: ["prerequisites"], message: "Grade paths cannot require lower-grade remediation" });
  }
  const rows = path.currentGradeLessons;
  const byId = new Map(rows.map(row => [row.lessonId, row]));
  if (byId.size !== rows.length || path.currentGradeLessons.some(row => row.gradeCode !== path.gradeCode || row.subject !== path.subject)) {
    context.addIssue({ code: "custom", path: ["currentGradeLessons"], message: "Path scope mismatch" });
  }
  if (rows.some(row => row.subject !== path.subject || row.blockedByLessonIds.some(id => !byId.has(id)))) {
    context.addIssue({ code: "custom", path: ["prerequisites"], message: "Missing prerequisite identity" });
  }
  if (path.nextLesson && (path.nextLesson.gradeCode !== path.gradeCode || !byId.has(path.nextLesson.lessonId)
    || !path.nextLesson.canStart || !["available", "needs_practice"].includes(path.nextLesson.status)
    || JSON.stringify(path.nextLesson) !== JSON.stringify(byId.get(path.nextLesson.lessonId)))) {
    context.addIssue({ code: "custom", path: ["nextLesson"], message: "Recommendation is not an eligible path lesson" });
  }
});

export type ProgressiveGrade = z.infer<typeof progressiveGradeSchema>;
export type ProgressiveLesson = z.infer<typeof progressiveLessonSchema>;
export type ProgressivePath = z.infer<typeof progressivePathSchema>;

export function progressiveLessonHasClassroom(lesson: ProgressiveLesson) {
  return lesson.canStart && lesson.status !== "locked" && lesson.blockedByLessonIds.length === 0
    && Boolean(lesson.course?.courseId && lesson.course?.courseVersion);
}
