import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningLibrary } from "@/features/learning/learning-library";
import type { LearningLibraryResponse } from "@/lib/contracts/learning";

const { getLearningLibrary, replace, refresh } = vi.hoisted(() => ({
  getLearningLibrary: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));
vi.mock("@/features/learning/learning-client", () => ({
  getLearningLibrary,
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

describe("LearningLibrary full runtime links", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  beforeEach(() => {
    getLearningLibrary.mockReset();
    getLearningLibrary.mockResolvedValue(library);
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

  it("keeps the first available course in the catalog while it is also the continuation", async () => {
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

    expect(await screen.findByRole("link", { name: /开始上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
    expect(screen.getByRole("link", { name: /继续上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-runtime-1/classroom",
    );
    expect(screen.queryByText("第一门课程正在准备")).not.toBeInTheDocument();
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

    expect(screen.getByText(/已有 1 门可用/)).toBeInTheDocument();
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
