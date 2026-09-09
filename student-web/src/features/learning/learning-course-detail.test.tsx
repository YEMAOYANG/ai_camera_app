import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningCourseDetail } from "@/features/learning/learning-course-detail";
import type { LearningCourseDetailResponse } from "@/lib/contracts/learning";

const { getLearningCourse } = vi.hoisted(() => ({
  getLearningCourse: vi.fn(),
}));

vi.mock("@/features/learning/learning-client", () => ({
  getLearningCourse,
  setLearningFavorite: vi.fn(),
}));

const detail: LearningCourseDetailResponse = {
  ok: true,
  source: "backend",
  item: {
    taskId: "task-package-only",
    taskStatus: "scheduled",
    learningDate: "2026-08-25",
    scheduledStart: "19:30",
    slot: "core",
    course: {
      id: "course-formal-1",
      version: "1",
      gradeCode: "primary_1",
      subject: "math",
      subjectLabel: "数学",
      nodeCode: "number_sense_20",
      title: "20以内数量关系",
      objective: "理解20以内数量关系",
      intro: "跟着老师一起观察数量变化。",
      estimatedMinutes: 10,
      questionCount: 5,
    },
    session: null,
    report: null,
    favorite: false,
    classroomAvailable: true,
    packageClassroomAvailable: true,
    fullClassroomAvailable: false,
    lastActivityAt: null,
  },
};

describe("LearningCourseDetail formal classroom gate", () => {
  afterEach(cleanup);
  beforeEach(() => {
    getLearningCourse.mockReset();
    getLearningCourse.mockResolvedValue(detail);
  });

  it("keeps package-only content in preparation instead of opening a fallback player", async () => {
    render(
      <LearningCourseDetail
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        courseId="course-formal-1"
        version="1"
      />,
    );

    expect(await screen.findByRole("heading", { name: "20以内数量关系" })).toBeInTheDocument();
    expect(screen.getByText("完整课堂准备中")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "今天想和谁一起学？" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /开始上课/ })).not.toBeInTheDocument();
  });

  it("silently opens the action when the formal classroom becomes ready", async () => {
    getLearningCourse
      .mockResolvedValueOnce(detail)
      .mockResolvedValue({
        ...detail,
        item: { ...detail.item, fullClassroomAvailable: true },
      });

    render(
      <LearningCourseDetail
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        courseId="course-formal-1"
        version="1"
        pollIntervalMs={10}
      />,
    );

    expect(await screen.findByText("完整课堂准备中")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /开始上课/ })).toHaveAttribute(
      "href",
      "/lesson/task-package-only/classroom",
    );
    expect(getLearningCourse).toHaveBeenCalledTimes(2);
  });

  it("shows the saved completion without treating a closed launch as generation", async () => {
    getLearningCourse.mockResolvedValue({
      ...detail,
      item: { ...detail.item, taskStatus: "completed", fullClassroomAvailable: false },
    });
    render(
      <LearningCourseDetail
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        courseId="course-formal-1"
        pollIntervalMs={10}
      />,
    );
    expect(await screen.findByText("这节课学完啦")).toBeInTheDocument();
    expect(screen.queryByText("完整课堂准备中")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /开始上课/ })).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 35));
    expect(getLearningCourse).toHaveBeenCalledTimes(1);
  });
});
