import { z } from "zod";

import {
  classroomCursorSchema,
  classroomDescriptorSchema,
  lessonPackageV2Schema,
} from "@/lib/contracts/lesson-package";

export const learningChoiceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
});

export const learningQuestionSchema = z.object({
  id: z.string().min(1),
  index: z.number().int().nonnegative().optional(),
  type: z.enum(["numeric", "exact_text", "accepted_text", "single_choice", "sequence"]),
  prompt: z.string().min(1),
  skill: z.string().optional().default(""),
  attemptNumber: z.number().int().positive().optional(),
  inputMode: z.string().optional().default("text"),
  choices: z.array(learningChoiceSchema).optional().default([]),
});

export const teachingFlowSchema = z.object({
  schemaVersion: z.literal("mira.learning.teaching-flow.v1"),
  teach: z.object({
    title: z.string().default(""),
    sayText: z.string().default(""),
    keyPoints: z.array(z.string()).default([]),
  }),
  workedExample: learningQuestionSchema.safeExtend({
    answerDisplayText: z.string().min(1),
    explanation: z.string().default(""),
  }),
  guidedQuestionIds: z.array(z.string()).default([]),
  independentQuestionIds: z.array(z.string()).default([]),
  recap: z.object({ sayText: z.string().default("") }),
});

export const learningLessonSchema = z.object({
  courseId: z.string().min(1),
  version: z.string().optional(),
  courseVersion: z.string().optional(),
  gradeCode: z.string().optional(),
  title: z.string().min(1),
  subject: z.string().min(1),
  subjectLabel: z.string().min(1),
  nodeCode: z.string().optional(),
  objective: z.string().default(""),
  intro: z.string().default(""),
  estimatedMinutes: z.number().int().positive().default(10),
  questionCount: z.number().int().nonnegative().default(0),
  sessionKind: z.string().default("lesson"),
  outcomeMode: z.string().default("scored_deterministic"),
  teachingFlow: teachingFlowSchema.optional(),
});

export const learningTaskSchema = z.object({
  id: z.string().min(1),
  status: z.string().default("scheduled"),
  scheduledStart: z.string().nullable().optional(),
  scheduledDate: z.string().nullable().optional(),
  learningSlot: z.string().optional(),
});

export const learningSessionSchema = z.object({
  id: z.string().min(1),
  taskId: z.string().min(1),
  courseId: z.string().min(1),
  courseVersion: z.string(),
  status: z.string(),
  currentQuestionIndex: z.number().int().nonnegative(),
  totalQuestions: z.number().int().nonnegative(),
  correctCount: z.number().int().nonnegative(),
  attemptedCount: z.number().int().nonnegative(),
  hintCount: z.number().int().nonnegative(),
  currentQuestion: learningQuestionSchema.nullable(),
  startedAt: z.number(),
  completedAt: z.number().nullable().optional(),
  teachingFlow: teachingFlowSchema.optional(),
});

export const learningReportSchema = z.object({
  id: z.string().min(1),
  subject: z.string(),
  subjectLabel: z.string(),
  score: z.number().int().min(0).max(100),
  correctCount: z.number().int().nonnegative(),
  independentCorrectCount: z.number().int().nonnegative(),
  hintCount: z.number().int().nonnegative(),
  totalQuestions: z.number().int().nonnegative(),
  masteryLevel: z.string(),
  summary: z.string(),
  strengths: z.array(z.string()).default([]),
  nextStep: z.string(),
  createdAt: z.number(),
});

export const learningTodayItemSchema = z.object({
  slot: z.enum(["core", "rotation", "extension"]),
  state: z.enum(["recommended", "scheduled", "in_progress", "completed"]),
  subject: z.string(),
  recommendation: learningLessonSchema,
  task: learningTaskSchema.nullable(),
  session: learningSessionSchema.nullable(),
  latestReport: learningReportSchema.nullable(),
  dayBucket: z.enum(["today", "carryover"]).optional(),
  originDate: z.string().optional(),
  carryover: z.object({
    id: z.string().min(1),
    reason: z.enum(["started_incomplete", "missed_unstarted"]),
    originDate: z.string(),
    targetDate: z.string(),
    daysOverdue: z.number().int().positive(),
  }).nullable().optional(),
});

export const courseSupplySummarySchema = z.object({
  schemaVersion: z.literal("learning.course-supply-summary.v1"),
  version: z.string(),
  requestedCount: z.number().int().nonnegative(),
  readyCount: z.number().int().nonnegative(),
  paused: z.boolean(),
  delayed: z.boolean().optional(),
  lastProgressAt: z.number().int().nullable(),
  retryAfterMs: z.number().int().min(2500).max(30000),
  message: z.string(),
});

export const learningCatalogStatusSchema = z.enum(["preparing", "complete", "failed"]);

export const learningTodayResponseSchema = z.object({
  ok: z.literal(true),
  date: z.string(),
  items: z.array(learningTodayItemSchema),
  itemCount: z.number().int().nonnegative(),
  completedCount: z.number().int().nonnegative(),
  carryoverCount: z.number().int().nonnegative().optional(),
  newCount: z.number().int().nonnegative().optional(),
  backlogCount: z.number().int().nonnegative().optional(),
  preparationProgressPercent: z.number().int().min(0).max(100).nullable().optional(),
  courseSupply: courseSupplySummarySchema.optional(),
  catalogStatus: learningCatalogStatusSchema,
  availableCourseCount: z.number().int().nonnegative(),
  targetCourseCount: z.number().int().positive(),
});

export const learningLibraryBucketSchema = z.enum(["continue", "makeup", "all", "completed", "favorites"]);
export const learningLibrarySourceSchema = z.literal("backend");

export const learningSubjectSchema = z.enum(["chinese", "math", "english"]);

export const learningLibraryCourseSchema = z.object({
  id: z.string().min(1),
  version: z.string().min(1),
  gradeCode: z.string().min(1),
  subject: learningSubjectSchema,
  subjectLabel: z.string().min(1),
  nodeCode: z.string().min(1).nullable(),
  title: z.string().min(1),
  objective: z.string().default(""),
  estimatedMinutes: z.number().int().positive(),
  questionCount: z.number().int().nonnegative(),
});

// Library/history responses intentionally carry compact immutable snapshots,
// not the active lesson runner's answer-bearing session contract.
export const learningLibrarySessionSchema = z.object({
  id: z.string().min(1),
  status: z.string().min(1),
  currentQuestionIndex: z.number().int().nonnegative(),
  correctCount: z.number().int().nonnegative(),
  attemptedCount: z.number().int().nonnegative(),
  startedAt: z.number().int().nonnegative(),
  completedAt: z.number().int().nonnegative().nullable(),
  updatedAt: z.number().int().nonnegative(),
});

export const learningLibraryReportSchema = z.object({
  id: z.string().min(1),
  score: z.number().int().min(0).max(100),
  masteryLevel: z.string().min(1),
  summary: z.string(),
  nextStep: z.string(),
  createdAt: z.number().int().nonnegative(),
});

export const learningLibraryItemSchema = z.object({
  taskId: z.string().min(1).nullable(),
  taskStatus: z.string().min(1),
  learningDate: z.string().min(1),
  scheduledStart: z.string().nullable(),
  slot: z.string().min(1),
  course: learningLibraryCourseSchema,
  session: learningLibrarySessionSchema.nullable(),
  report: learningLibraryReportSchema.nullable(),
  favorite: z.boolean(),
  classroomAvailable: z.boolean(),
  // Optional only for a rolling deployment from the pre-release-gate
  // backend.  Missing explicit gates fail closed; the old, weaker
  // classroomAvailable value is never promoted into either new capability.
  packageClassroomAvailable: z.boolean().optional().default(false),
  fullClassroomAvailable: z.boolean().optional().default(false),
  lastActivityAt: z.number().nullable(),
});

export const learningCourseDetailItemSchema = learningLibraryItemSchema.safeExtend({
  course: learningLibraryCourseSchema.safeExtend({
    intro: z.string().default(""),
  }),
});

export const learningLibraryResponseSchema = z.object({
  ok: z.literal(true),
  bucket: learningLibraryBucketSchema,
  subject: learningSubjectSchema.nullable(),
  continueItem: learningLibraryItemSchema.nullable(),
  items: z.array(learningLibraryItemSchema),
  nextCursor: z.string().min(1).nullable(),
  source: learningLibrarySourceSchema.optional().default("backend"),
  historyComplete: z.boolean().optional().default(true),
  preparationProgressPercent: z.number().int().min(0).max(100).nullable().optional(),
  courseSupply: courseSupplySummarySchema.optional(),
  catalogStatus: learningCatalogStatusSchema,
  availableCourseCount: z.number().int().nonnegative(),
  targetCourseCount: z.number().int().positive(),
});

export const learningCourseDetailResponseSchema = z.object({
  ok: z.literal(true),
  item: learningCourseDetailItemSchema,
  source: learningLibrarySourceSchema.optional().default("backend"),
});

export const learningFavoriteRequestSchema = z.object({
  courseId: z.string().trim().min(1).max(160),
  courseVersion: z.string().trim().min(1).max(80),
  favorite: z.boolean(),
}).strict();

export const learningFavoriteResponseSchema = z.object({
  ok: z.literal(true),
  courseId: z.string().min(1),
  courseVersion: z.string().min(1),
  favorite: z.boolean(),
  storage: z.enum(["backend", "web_preference"]),
});

export const learningTeacherProfileSchema = z.object({
  id: z.string().trim().min(1).max(80),
  version: z.number().int().positive(),
  displayName: z.string().trim().min(1).max(80),
  avatarPath: z.string().startsWith("/teachers/").max(200),
  subject: learningSubjectSchema,
  languageCode: z.string().trim().min(2).max(24),
  teachingStyle: z.string().trim().min(1).max(80),
  capabilities: z.array(z.string().trim().min(1).max(80)).min(1).max(32),
}).strict();

export const learningTeacherSelectionSchema = z.object({
  id: z.string().trim().min(1).max(80),
  version: z.number().int().positive(),
}).strict();

export const learningTeachersResponseSchema = z.object({
  ok: z.literal(true),
  registryVersion: z.enum([
    "mira.teacher-registry.v1",
    "mira.teacher-registry.v2",
  ]),
  items: z.array(learningTeacherProfileSchema),
  selected: learningTeacherSelectionSchema.nullable(),
}).strict();

export const learningTeacherPreferenceRequestSchema = z.object({
  subject: learningSubjectSchema,
  teacherProfileId: z.string().trim().min(1).max(80),
  teacherProfileVersion: z.number().int().positive(),
}).strict();

export const learningTeacherPreferenceResponseSchema = z.object({
  ok: z.literal(true),
  childId: z.string().trim().min(1).max(160),
  subject: learningSubjectSchema,
  teacher: learningTeacherProfileSchema,
  updatedAt: z.number().int().nonnegative(),
}).strict();

export const classroomReleaseSchema = z.object({
  mode: z.enum(["package_required", "legacy_compatible"]),
  status: z.enum(["ready", "preparing", "unavailable"]),
  retryAfterSeconds: z.number().int().positive().max(86_400).nullable().optional(),
}).strict();

export const learningStartResponseSchema = z.object({
  ok: z.literal(true),
  resumed: z.boolean(),
  session: learningSessionSchema,
  lesson: learningLessonSchema,
  classroom: lessonPackageV2Schema.optional(),
  package: classroomDescriptorSchema.optional(),
  cursor: classroomCursorSchema.optional(),
  classroomRelease: classroomReleaseSchema.optional(),
}).superRefine((value, context) => {
  const classroomFields = [value.classroom, value.package, value.cursor];
  const presentCount = classroomFields.filter((field) => field !== undefined).length;
  if (presentCount !== 0 && presentCount !== classroomFields.length) {
    context.addIssue({
      code: "custom",
      path: ["classroom"],
      message: "课堂包、版本描述和播放游标必须一起返回",
    });
  }
  if (value.classroom && value.package) {
    if (value.classroom.id !== value.package.id || value.classroom.version !== value.package.version) {
      context.addIssue({
        code: "custom",
        path: ["package"],
        message: "课堂包版本与课程内容不一致",
      });
    }
  }
  if (value.classroom && value.cursor && !value.classroom.scenes.some((scene) => scene.id === value.cursor?.sceneId)) {
    context.addIssue({
      code: "custom",
      path: ["cursor", "sceneId"],
      message: "播放游标指向了不存在的场景",
    });
  }
  if (value.classroomRelease?.status === "ready" && presentCount !== classroomFields.length) {
    context.addIssue({
      code: "custom",
      path: ["classroomRelease", "status"],
      message: "课堂声明已就绪时必须返回完整课堂包",
    });
  }
});

export const learningAnswerResponseSchema = z.object({
  ok: z.literal(true),
  correct: z.boolean().nullable(),
  feedback: z.string(),
  hint: z.string().nullable(),
  canRetry: z.boolean(),
  hintLevel: z.number().int().nonnegative(),
  nextQuestion: learningQuestionSchema.nullable(),
  completed: z.boolean(),
  session: learningSessionSchema,
  report: learningReportSchema.nullable(),
});

export type LearningChoice = z.infer<typeof learningChoiceSchema>;
export type LearningQuestion = z.infer<typeof learningQuestionSchema>;
export type TeachingFlow = z.infer<typeof teachingFlowSchema>;
export type LearningLesson = z.infer<typeof learningLessonSchema>;
export type LearningSession = z.infer<typeof learningSessionSchema>;
export type LearningReport = z.infer<typeof learningReportSchema>;
export type LearningTodayItem = z.infer<typeof learningTodayItemSchema>;
export type LearningTodayResponse = z.infer<typeof learningTodayResponseSchema>;
export type LearningLibraryBucket = z.infer<typeof learningLibraryBucketSchema>;
export type LearningSubject = z.infer<typeof learningSubjectSchema>;
export type LearningLibraryItem = z.infer<typeof learningLibraryItemSchema>;
export type LearningLibraryResponse = z.infer<typeof learningLibraryResponseSchema>;
export type LearningCourseDetailResponse = z.infer<typeof learningCourseDetailResponseSchema>;
export type LearningTeacherProfile = z.infer<typeof learningTeacherProfileSchema>;
export type LearningTeachersResponse = z.infer<typeof learningTeachersResponseSchema>;
export type LearningTeacherPreferenceResponse = z.infer<typeof learningTeacherPreferenceResponseSchema>;
export type LearningAnswerResponse = z.infer<typeof learningAnswerResponseSchema>;
export type LearningStartResponse = z.infer<typeof learningStartResponseSchema>;
