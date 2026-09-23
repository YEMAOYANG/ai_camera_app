import type { ProgressiveLesson, ProgressivePath } from "@/lib/contracts/progressive-learning";

export function progressiveLesson(overrides: Partial<ProgressiveLesson> = {}): ProgressiveLesson {
  return {
    lessonId: "ZH1A01.01", title: "认读单韵母 a", unitTitle: "听音与单韵母", unitId: "ZH1A01",
    gradeCode: "primary_1", subject: "chinese", phase: "upper", sequence: 1,
    assessmentMode: "objective", prerequisiteLessonIds: [], status: "available", canStart: true,
    message: "从入门课程开始学习。", blockedByLessonIds: [], difficultyCode: "basic",
    independentEvidenceCount: 0, independentCorrectCount: 0, distinctAssessmentSets: 0,
    accuracy: null, masteredAt: null, stabilityStatus: "not_due", stableAt: null,
    course: null, courseId: null, courseVersion: null, ...overrides,
  };
}

export function progressivePath(overrides: Partial<ProgressivePath> = {}): ProgressivePath {
  const first = progressiveLesson();
  const second = progressiveLesson({ lessonId: "ZH1A01.02", title: "认读单韵母 o", sequence: 2,
    prerequisiteLessonIds: [first.lessonId], blockedByLessonIds: [first.lessonId], canStart: false, status: "locked" });
  return {
    ok: true, schemaVersion: "mira.learning.progressive-path.v1", curriculumVersion: "mira.primary.progressive.v1",
    gradeCode: "primary_1", subject: "chinese", currentGradeLessons: [first, second], prerequisites: [], nextLesson: first,
    assessment: { required: false, missingLessonIds: [], tasks: [], nextTask: null },
    masteryPolicy: { independentQuestionCount: 5, distinctAssessmentSets: 2, minimumAccuracy: 0.8,
      delayedReviewAfterHours: 24, observedRequiresAuthorizedConfirmation: true }, ...overrides,
  };
}
