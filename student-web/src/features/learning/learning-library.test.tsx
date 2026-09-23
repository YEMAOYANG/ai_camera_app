import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningLibrary } from "@/features/learning/learning-library";
import { groupLearningLibraryItems } from "@/features/learning/learning-library-groups";
import type { LearningLibraryItem, LearningLibraryResponse, LearningProgression } from "@/lib/contracts/learning";

const { getLearningLibrary, startLearningCourse, replace, refresh } = vi.hoisted(() => ({
  getLearningLibrary: vi.fn(),
  startLearningCourse: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));
vi.mock("@/features/learning/learning-client", () => ({
  getLearningLibrary,
  startLearningCourse,
  setLearningFavorite: vi.fn(),
}));

const library: LearningLibraryResponse = {
  ok: true,
  bucket: "all",
  subject: null,
  catalogStatus: "complete",
  availableCourseCount: 30,
  targetCourseCount: 30,
  continueItem: null,
  nextCursor: null,
  source: "backend",
  historyComplete: true,
  items: [{
    taskId: "task-runtime-1",
    taskStatus: "scheduled",
    learningDate: "2026-08-18",
    scheduledStart: "19:30",
    slot: "core",
    course: {
      id: "course-runtime-1",
      version: "1",
      gradeCode: "primary_1",
      subject: "chinese",
      subjectLabel: "语文",
      nodeCode: "pinyin",
      title: "拼音声母进阶课",
      objective: "在完整互动课堂中认识拼音",
      estimatedMinutes: 10,
      questionCount: 4,
    },
    session: null,
    report: null,
    favorite: false,
    classroomAvailable: true,
    packageClassroomAvailable: true,
    fullClassroomAvailable: true,
    lastActivityAt: null,
  }],
};
const lockedProgression: LearningProgression = {
  schemaVersion: "mira.learning.progression.v1",
  curriculumVersion: "primary-progressive.v1",
  granularity: "skill_boundary",
  skillId: "chinese.pinyin.initials",
  sequence: 2,
  learningStatus: "locked",
  canStart: false,
  blockedBySkillIds: ["chinese.pinyin.vowels"],
  message: "先学会单韵母，再来认识声母。",
};

describe("LearningLibrary full runtime links", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  beforeEach(() => {
    getLearningLibrary.mockReset();
    getLearningLibrary.mockResolvedValue(library);
    startLearningCourse.mockReset();
  });

  it("keeps the newer completed attempt above an old reopened task without completing another exercise set", async () => {
    const old: LearningLibraryItem = { ...library.items[0], taskId: "old-task", taskStatus: "in_progress",
      course: { ...library.items[0].course, id: "english-set-1", questionCount: 6, title: "常见主宾形式", nodeCode: "EN6A01.01" },
      progression: { ...lockedProgression, granularity: "lesson", lessonId: "EN6A01.01", canStart: true, canResume: true, learningStatus: "needs_practice" },
      session: { id: "old-session", status: "in_progress", startedAt: 1000, updatedAt: 9000,
        completedAt: null, currentQuestionIndex: 1, attemptedCount: 1, correctCount: 1 }, lastActivityAt: 9000 };
    const completed: LearningLibraryItem = { ...old, taskId: "completed-task", taskStatus: "completed",
      session: { ...old.session!, id: "completed-session", status: "completed", startedAt: 2000, updatedAt: 3000,
        completedAt: 3000, currentQuestionIndex: 6, attemptedCount: 6, correctCount: 6 }, lastActivityAt: 3000 };
    const anotherSet: LearningLibraryItem = { ...old, taskId: null, taskStatus: "available", session: null,
      course: { ...old.course, id: "english-set-2" }, lastActivityAt: null };
    const nextAttempt: LearningLibraryItem = { ...old, taskId: "restart-task",
      session: { ...old.session!, id: "restart-session", startedAt: 4000, updatedAt: 4000 }, lastActivityAt: 4000 };
    expect(groupLearningLibraryItems([old, completed, anotherSet])[0]).toMatchObject({ item: anotherSet, exerciseSetCount: 2, completedExerciseSetCount: 1, historyCount: 2 });
    expect(groupLearningLibraryItems([old, completed, nextAttempt])[0].item).toBe(nextAttempt);
    // Catalog and history may both return the exact completed session.
    getLearningLibrary.mockResolvedValue({ ...library, continueItem: old, items: [old, completed, completed] });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_6" }} />);
    expect(await screen.findByText("已完成 100%")).toBeInTheDocument();
    expect(screen.queryByText("已完成 17%")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("学习记录 · 2 次学习记录"));
    expect(screen.getByRole("link", { name: /继续这次学习/ })).toHaveAttribute("href", "/lesson/old-task/classroom");
  });

  it("groups exact lesson sets and duplicate history tasks while keeping existing sessions reachable", async () => {
    const session = (id: string) => ({ id, status: "in_progress", currentQuestionIndex: 0,
      correctCount: 0, attemptedCount: 0, startedAt: 1, completedAt: null, updatedAt: 2 });
    const first: LearningLibraryItem = { ...library.items[0], taskId: "task-fine-active", taskStatus: "in_progress",
      session: session("session-fine"), lastActivityAt: 1,
      progression: { ...lockedProgression, curriculumVersion: "mira.primary.progressive.v1", granularity: "lesson",
        lessonId: "ZH6A01.01", canStart: true, canResume: true, learningStatus: "needs_practice" },
      course: { ...library.items[0].course, gradeCode: "primary_6", id: "fine-1", title: "区分信息性质", nodeCode: "ZH6A01.01" } };
    const second = { ...first, taskId: null, taskStatus: "available", session: null, lastActivityAt: 10,
      progression: { ...first.progression!, canResume: false }, course: { ...first.course, id: "fine-2" } };
    const differentLesson = { ...second, course: { ...second.course, id: "fine-other", nodeCode: "ZH6A01.02" },
      progression: { ...second.progression, lessonId: "ZH6A01.02" } };
    const legacy = { ...library.items[0], taskId: "task-old-newer", session: session("legacy-newer"), lastActivityAt: 20,
      progression: { ...lockedProgression, canResume: true } };
    const older = { ...legacy, taskId: "task-old-earlier", session: session("legacy-earlier"), lastActivityAt: 5 };
    getLearningLibrary.mockResolvedValue({ ...library, items: [second, first, legacy, older, differentLesson] });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_6" }} />);
    expect(await screen.findAllByRole("heading", { name: "区分信息性质" })).toHaveLength(2);
    expect(screen.getAllByRole("heading", { name: "拼音声母进阶课" })).toHaveLength(1);
    expect(screen.getByText("2 组练习")).toBeInTheDocument();
    expect(screen.getByText("学习记录 · 2 次学习记录")).toBeInTheDocument();
    const launchUrls = screen.getAllByRole("link", { name: /继续上课/ }).map(link => link.getAttribute("href"));
    expect(launchUrls).toContain("/lesson/task-fine-active/classroom");
    expect(launchUrls).toContain("/lesson/task-old-newer/classroom");
    fireEvent.click(screen.getByText("学习记录 · 2 次学习记录"));
    expect(screen.getByRole("link", { name: /继续这次学习/ })).toHaveAttribute("href", "/lesson/task-old-earlier/classroom");
  });

  it.each(["task-runtime-1", null])("keeps a future course visible while closing both scheduled and new launch paths", async (taskId) => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      items: [{ ...library.items[0], taskId, progression: lockedProgression }],
    });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByRole("link", { name: "拼音声母进阶课" })).toHaveAttribute("href", "/learning/course-runtime-1?version=1");
    expect(screen.getByText(`知识点学习顺序 2 · ${lockedProgression.message}`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "收藏拼音声母进阶课" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "暂未解锁" }));
    expect(screen.queryByRole("link", { name: /开始上课|继续上课/ })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("does not bypass progression through the continuation hero", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      continueItem: { ...library.items[0], progression: lockedProgression },
      items: [],
    });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByRole("heading", { name: "拼音声母进阶课" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂未解锁" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /继续上课/ })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("resumes only an existing in-progress session explicitly allowed by the backend", async () => {
    const resumeItem = {
      ...library.items[0],
      progression: { ...lockedProgression, canResume: true },
      session: { id: "session-1", status: "in_progress", currentQuestionIndex: 1, correctCount: 1, attemptedCount: 1, startedAt: 1, completedAt: null, updatedAt: 1 },
    };
    getLearningLibrary.mockResolvedValue({ ...library, items: [resumeItem] });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByRole("link", { name: /继续上课/ })).toHaveAttribute("href", "/lesson/task-runtime-1/classroom");
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("does not treat canResume as authority to create a task or invent a session", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      items: [{ ...library.items[0], progression: { ...lockedProgression, canResume: true } }],
    });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByRole("button", { name: "暂未解锁" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /开始上课|继续上课/ })).not.toBeInTheDocument();
  });

  it("does not reopen a completed task even if it is returned as the continuation", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      continueItem: { ...library.items[0], taskStatus: "completed", progression: { ...lockedProgression, canStart: true, learningStatus: "needs_practice" } },
      items: [],
    });
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByText("学完啦")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /开始上课|继续上课/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /开始上课|继续上课/ })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("routes a ready full-runtime course directly to the trusted document route", async () => {
    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
      />,
    );

    expect(await screen.findByText("拼音声母进阶课")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /开始上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
    expect(screen.queryByRole("heading", { name: "今天想和谁一起学？" })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/open\s*maic/i);
  });

  it("offers a taskless formal course immediately and keeps its card visible after a failed start", async () => {
    getLearningLibrary.mockResolvedValue({ ...library, items: [{ ...library.items[0], taskId: null, taskStatus: "available" }] });
    startLearningCourse.mockRejectedValue(Object.assign(new Error("课程发布已变化"), { code: "learning_classroom_release_changed" }));
    render(<LearningLibrary student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    fireEvent.click(await screen.findByRole("button", { name: "开始上课" }));
    expect(startLearningCourse).toHaveBeenCalledExactlyOnceWith("course-runtime-1", "1");
    expect(await screen.findByRole("alert")).toHaveTextContent("这节课刚刚更新，请刷新后再试。");
    expect(screen.getByText("拼音声母进阶课")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始上课" })).toBeEnabled();
  });

  it("does not present a legacy package as a ready formal classroom", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      items: [{
        ...library.items[0],
        fullClassroomAvailable: false,
        packageClassroomAvailable: true,
      }],
    });

    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
      />,
    );

    expect(await screen.findByText("拼音声母进阶课")).toBeInTheDocument();
    expect(screen.getAllByText("完整课堂准备中")).toHaveLength(2);
    expect(screen.queryByRole("link", { name: /开始上课/ })).not.toBeInTheDocument();
  });

  it("uses the continuation as the lesson's single main entrance", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      catalogStatus: "preparing",
      availableCourseCount: 1,
      continueItem: library.items[0],
    });

    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
      />,
    );

    expect(await screen.findByRole("link", { name: /继续上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
    expect(screen.queryByRole("link", { name: /开始上课/ })).not.toBeInTheDocument();
    expect(screen.queryByText("第一门课程正在准备")).not.toBeInTheDocument();
    const continuationLink = screen.getByRole("link", { name: /继续上课/ });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "继续学习" }));
    });
    expect(getLearningLibrary).toHaveBeenLastCalledWith({ bucket: "continue", subject: undefined });
    expect(screen.getByRole("link", { name: /继续上课/ })).toBe(continuationLink);
  });

  it("silently turns a preparing course into a ready action without a page refresh", async () => {
    getLearningLibrary
      .mockResolvedValueOnce({
        ...library,
        availableCourseCount: 0,
        items: [{ ...library.items[0], fullClassroomAvailable: false }],
      })
      .mockResolvedValue(library);

    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
        pollIntervalMs={10}
      />,
    );

    expect((await screen.findAllByText("完整课堂准备中")).length).toBeGreaterThan(0);
    expect(await screen.findByRole("link", { name: /开始上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
    expect(getLearningLibrary).toHaveBeenCalledTimes(2);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("stops preparation polling once a course is playable and silently refreshes on focus", async () => {
    vi.useFakeTimers();
    const secondCourse = {
      ...library.items[0],
      taskId: null,
      taskStatus: "available",
      course: {
        ...library.items[0].course,
        id: "course-runtime-2",
        title: "第二门已完成的数学课",
        subject: "math" as const,
        subjectLabel: "数学",
      },
    };
    getLearningLibrary
      .mockResolvedValueOnce({
        ...library,
        catalogStatus: "preparing",
        availableCourseCount: 1,
      })
      .mockResolvedValue({
        ...library,
        catalogStatus: "complete",
        availableCourseCount: 2,
        targetCourseCount: 2,
        items: [...library.items, secondCourse],
      });

    await act(async () => { render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
        pollIntervalMs={10}
      />,
    ); });

    expect(screen.getByText(/已有 1 节课程/)).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(getLearningLibrary).toHaveBeenCalledTimes(1);
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByText("第二门已完成的数学课")).toBeInTheDocument();
    expect(getLearningLibrary).toHaveBeenCalledTimes(2);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("stops polling after a terminal catalog failure while keeping ready courses visible", async () => {
    vi.useFakeTimers();
    getLearningLibrary.mockResolvedValue({
      ...library,
      catalogStatus: "failed",
      availableCourseCount: 1,
      items: [{ ...library.items[0], fullClassroomAvailable: false }],
    });

    await act(async () => {
      render(
        <LearningLibrary
          student={{
            id: "student-1",
            childId: "child-1",
            displayName: "乐乐",
            gradeCode: "primary_1",
          }}
          pollIntervalMs={10}
        />,
      );
    });

    expect(screen.getByText(/本轮更新未全部完成/)).toBeInTheDocument();
    expect(screen.getByText("拼音声母进阶课")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    expect(getLearningLibrary).toHaveBeenCalledTimes(1);
  });

  it("keeps missed lessons visible as makeup work", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      bucket: "makeup",
      items: [{ ...library.items[0], taskStatus: "missed" }],
    });

    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
      />,
    );

    expect(await screen.findByText("未完成，待补课")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待补课" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /补上这节课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
  });

  it("labels an in-progress historical lesson as makeup inside the makeup bucket", async () => {
    getLearningLibrary.mockResolvedValue({
      ...library,
      bucket: "makeup",
      continueItem: null,
      items: [{ ...library.items[0], taskStatus: "in_progress" }],
    });

    render(
      <LearningLibrary
        student={{
          id: "student-1",
          childId: "child-1",
          displayName: "乐乐",
          gradeCode: "primary_1",
        }}
      />,
    );

    (await screen.findByRole("button", { name: "待补课" })).click();
    expect(await screen.findByText("未完成，待补课")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /补上这节课/ })).toBeInTheDocument();
  });
});
