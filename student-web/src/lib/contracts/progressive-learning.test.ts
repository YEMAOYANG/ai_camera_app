import { describe, expect, it } from "vitest";

import { progressiveLessonHasClassroom, progressivePathSchema } from "@/lib/contracts/progressive-learning";
import { progressiveLesson, progressivePath } from "@/test/fixtures/progressive-learning";

describe("answer-free progressive learning path", () => {
  it("keeps eligibility separate from a prepared classroom", () => {
    const data = progressivePathSchema.parse(progressivePath());
    expect(data.nextLesson?.canStart).toBe(true);
    expect(progressiveLessonHasClassroom(data.nextLesson!)).toBe(false);
    const course = { courseId: "prepared-course", courseVersion: "1" };
    expect(progressiveLessonHasClassroom(progressiveLesson({ course, ...course }))).toBe(true);
    expect(progressiveLessonHasClassroom(progressiveLesson({ course, ...course, status: "locked", canStart: false }))).toBe(false);
  });

  it.each(["answer", "questions", "privateRubric", "providerApiKey", "accessToken"])("rejects unexpected private field %s at every response boundary", field => {
    const source = progressivePath();
    for (const value of [
      { ...source, [field]: "private" },
      { ...source, currentGradeLessons: [{ ...source.currentGradeLessons[0], [field]: "private" }] },
      { ...source, nextLesson: { ...source.nextLesson, [field]: "private" } },
      { ...source, assessment: { ...source.assessment, [field]: "private" } },
    ]) expect(progressivePathSchema.safeParse(value).success).toBe(false);
  });

  it("rejects contradictory locks, missing prerequisites, scope and course identity drift", () => {
    const source = progressivePath();
    expect(progressivePathSchema.safeParse({ ...source, nextLesson: { ...source.nextLesson, status: "locked", canStart: true } }).success).toBe(false);
    expect(progressivePathSchema.safeParse({ ...source, currentGradeLessons: [source.currentGradeLessons[1]] }).success).toBe(false);
    expect(progressivePathSchema.safeParse({ ...source, gradeCode: "primary_6" }).success).toBe(false);
    expect(progressivePathSchema.safeParse({ ...source, nextLesson: { ...source.nextLesson, course: { courseId: "other", courseVersion: "1" } } }).success).toBe(false);
  });
});
