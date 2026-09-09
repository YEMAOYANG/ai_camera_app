import { describe, expect, it } from "vitest";

import {
  learningLibraryResponseSchema,
  learningQuestionSchema,
  learningStartResponseSchema,
  learningTeacherPreferenceResponseSchema,
  learningTeachersResponseSchema,
} from "@/lib/contracts/learning";
import { lessonFixture, sessionFixture } from "@/test/fixtures/learning";

describe("student learning product contracts", () => {
  it("parses the exact backend library envelope and adds only safe defaults", () => {
    const response = learningLibraryResponseSchema.parse({
      ok: true,
      bucket: "all",
      subject: "chinese",
      catalogStatus: "complete",
      availableCourseCount: 30,
      targetCourseCount: 30,
      continueItem: null,
      items: [{
        taskId: "task-1",
        taskStatus: "scheduled",
        learningDate: "2026-08-14",
        scheduledStart: "19:30",
        slot: "core",
        course: {
          id: "course-1",
          version: "3",
          gradeCode: "primary_1",
          subject: "chinese",
          subjectLabel: "语文",
          nodeCode: "pinyin_aoe",
          title: "单韵母 a、o、e",
          objective: "听辨并认读 a、o、e",
          estimatedMinutes: 12,
          questionCount: 4,
        },
        session: {
          id: "session-1",
          status: "completed",
          currentQuestionIndex: 4,
          correctCount: 4,
          attemptedCount: 4,
          startedAt: 1_786_687_381_034,
          completedAt: 1_786_687_423_876,
          updatedAt: 1_786_687_423_876,
        },
        report: {
          id: "report-1",
          score: 100,
          masteryLevel: "mastered",
          summary: "两道独立练习首答全对。",
          nextStep: "按复习日期继续巩固。",
          createdAt: 1_786_687_423_876,
        },
        favorite: false,
        classroomAvailable: true,
        packageClassroomAvailable: true,
        fullClassroomAvailable: false,
        lastActivityAt: 1_786_687_423_876,
      }],
      nextCursor: null,
    });
    expect(response.items[0].course.nodeCode).toBe("pinyin_aoe");
    expect(response.items[0].session?.status).toBe("completed");
    expect(response.items[0].report?.score).toBe(100);
    expect(response.items[0].packageClassroomAvailable).toBe(true);
    expect(response.items[0].fullClassroomAvailable).toBe(false);
    expect(response.source).toBe("backend");
    expect(response.historyComplete).toBe(true);
  });

  it("rejects a synthesized today compatibility shelf as a formal course library", () => {
    expect(learningLibraryResponseSchema.safeParse({
      ok: true,
      bucket: "all",
      subject: null,
      catalogStatus: "complete",
      availableCourseCount: 30,
      targetCourseCount: 30,
      continueItem: null,
      items: [],
      nextCursor: null,
      source: "today_compat",
      historyComplete: false,
    }).success).toBe(false);
  });

  it("accepts the rolling pre-gate library payload but keeps both new launch gates closed", () => {
    const response = learningLibraryResponseSchema.parse({
      ok: true,
      bucket: "all",
      subject: null,
      catalogStatus: "complete",
      availableCourseCount: 30,
      targetCourseCount: 30,
      continueItem: null,
      items: [{
        taskId: "task-legacy",
        taskStatus: "completed",
        learningDate: "2026-08-14",
        scheduledStart: "19:30",
        slot: "core",
        course: {
          id: "course-legacy",
          version: "1.0.0",
          gradeCode: "primary_1",
          subject: "math",
          subjectLabel: "数学",
          nodeCode: "number_sense",
          title: "认识 1 到 5",
          objective: "认识 1 到 5 的数量",
          estimatedMinutes: 10,
          questionCount: 4,
        },
        session: null,
        report: null,
        favorite: false,
        // This is the old package-only signal.  It must not be promoted into
        // either of the explicit release/runtime gates during a rolling deploy.
        classroomAvailable: true,
        lastActivityAt: 1_786_687_423_876,
      }],
      nextCursor: null,
    });

    expect(response.items[0].classroomAvailable).toBe(true);
    expect(response.items[0].packageClassroomAvailable).toBe(false);
    expect(response.items[0].fullClassroomAvailable).toBe(false);
  });

  it("keeps match-pairs on the existing single-choice evaluator contract", () => {
    expect(learningQuestionSchema.safeParse({
      id: "match-2",
      type: "matching",
      prompt: "配成一对",
    }).success).toBe(false);
    expect(learningQuestionSchema.safeParse({
      id: "match-1",
      type: "single_choice",
      prompt: "苹果属于哪一类？",
      choices: [{ id: "fruit", label: "水果" }, { id: "star", label: "星球" }],
    }).success).toBe(true);
  });

  it("recognizes package-required preparation without weakening the ready package gate", () => {
    const base = {
      ok: true as const,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    expect(learningStartResponseSchema.safeParse({
      ...base,
      classroomRelease: { mode: "package_required", status: "preparing" },
    }).success).toBe(true);
    expect(learningStartResponseSchema.safeParse({
      ...base,
      classroomRelease: { mode: "package_required", status: "ready" },
    }).success).toBe(false);
  });

  it("uses the public versioned teacher registry as the only preference truth", () => {
    const teacher = {
      id: "mira_chinese_gentle",
      version: 2,
      displayName: "小语老师",
      avatarPath: "/teachers/mi-chinese-v1.png",
      subject: "chinese",
      languageCode: "zh-CN",
      teachingStyle: "gentle_guided",
      capabilities: ["explain_then_practice", "guided_reading"],
    };
    const list = learningTeachersResponseSchema.parse({
      ok: true,
      registryVersion: "mira.teacher-registry.v2",
      items: [teacher],
      selected: { id: teacher.id, version: 2 },
    });
    expect(list.selected).toEqual({ id: teacher.id, version: 2 });
    expect(learningTeachersResponseSchema.parse({
      ok: true,
      registryVersion: "mira.teacher-registry.v1",
      items: [{ ...teacher, version: 1 }],
      selected: { id: teacher.id, version: 1 },
    }).registryVersion).toBe("mira.teacher-registry.v1");
    expect(learningTeacherPreferenceResponseSchema.parse({
      ok: true,
      childId: "child-1",
      subject: "chinese",
      teacher,
      updatedAt: 1_787_000_000_000,
    }).teacher.avatarPath).toBe("/teachers/mi-chinese-v1.png");
    expect(learningTeachersResponseSchema.safeParse({
      ok: true,
      teachers: [teacher],
      selectedTeacherId: teacher.id,
      storage: "web_preference",
    }).success).toBe(false);
  });
});
