import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";

const { startLearningCourse } = vi.hoisted(() => ({ startLearningCourse: vi.fn() }));
vi.mock("@/features/learning/learning-client", () => ({ startLearningCourse }));
const response = { ok: true, taskId: "new task", created: true, courseId: "course-1", courseVersion: "2" };

describe("new shared course start", () => {
  afterEach(cleanup);
  beforeEach(() => { startLearningCourse.mockReset(); });

  it("locks repeated clicks while creating a task and navigates to the existing classroom document", async () => {
    let complete!: (value: typeof response) => void;
    startLearningCourse.mockReturnValue(new Promise(resolve => { complete = resolve; }));
    const navigate = vi.fn();
    render(<LearningCourseStartButton courseId="course-1" version="2" navigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "开始上课" }));
    const pending = screen.getByRole("button", { name: "正在进入…" });
    expect(pending).toBeDisabled();
    expect(pending).toHaveAttribute("aria-busy", "true");
    fireEvent.click(pending);
    expect(startLearningCourse).toHaveBeenCalledExactlyOnceWith("course-1", "2");
    expect(navigate).not.toHaveBeenCalled();
    await act(async () => complete(response));
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/lesson/new%20task/classroom");
  });

  it("shows a local error and can retry the same version using the backend's existing task", async () => {
    startLearningCourse.mockRejectedValueOnce(new Error("网络没有连上，请再试一次"))
      .mockResolvedValueOnce({ ...response, created: false });
    const navigate = vi.fn();
    render(<LearningCourseStartButton courseId="course-1" version="2" navigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "开始上课" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("网络没有连上，请再试一次");
    expect(screen.getByRole("button", { name: "开始上课" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "开始上课" }));
    await act(async () => undefined);
    expect(navigate).toHaveBeenCalledWith("/lesson/new%20task/classroom");
    expect(startLearningCourse).toHaveBeenCalledTimes(2);
  });

  it("returns expired authentication to unlock without trying to open a lesson", async () => {
    startLearningCourse.mockRejectedValue(Object.assign(new Error("请重新进入学习空间"), { status: 401 }));
    const navigate = vi.fn();
    render(<LearningCourseStartButton courseId="course-1" version="2" navigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "开始上课" }));
    await act(async () => undefined);
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/unlock");
  });
});
