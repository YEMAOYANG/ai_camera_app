import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningPath } from "@/features/learning/learning-path";
import { progressiveLesson, progressivePath } from "@/test/fixtures/progressive-learning";

const { router, startLearningCourse } = vi.hoisted(() => ({ router: { replace: vi.fn(), refresh: vi.fn() }, startLearningCourse: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/learning/learning-client", async importOriginal => ({ ...await importOriginal<typeof import("@/features/learning/learning-client")>(), startLearningCourse }));
vi.mock("@/components/student/space-shell", () => ({
  SpaceShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  SpacePageHeading: ({ title, children }: { title: string; children: ReactNode }) => <header><h1>{title}</h1>{children}</header>,
}));

const student = { id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" };
const reply = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), { status });

describe("LearningPath", () => {
  beforeEach(() => { vi.clearAllMocks(); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("shows exact missing prerequisites and never starts locked or unprepared lessons", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(progressivePath())));
    render(<LearningPath student={student} />);
    expect(await screen.findByRole("heading", { name: "认读单韵母 a", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("先完成：认读单韵母 a")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "认读单韵母 o：暂未解锁" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "课程准备中" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "开始这一步" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("starts only a ready eligible course using the existing classroom document flow", async () => {
    const course = { courseId: "course-1", courseVersion: "2" };
    const first = progressiveLesson({ course, ...course });
    const data = progressivePath();
    data.currentGradeLessons[0] = first; data.nextLesson = first;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(data)));
    startLearningCourse.mockResolvedValue({ ok: true, ...course, taskId: "task-approved", created: true });
    const navigate = vi.fn();
    render(<LearningPath student={student} navigate={navigate} />);
    fireEvent.click(await screen.findByRole("button", { name: "开始这一步" }));
    await waitFor(() => expect(startLearningCourse).toHaveBeenCalledExactlyOnceWith("course-1", "2"));
    expect(navigate).toHaveBeenCalledWith("/lesson/task-approved/classroom");
  });

  it("labels actual-performance lessons without claiming objective questions prove mastery", async () => {
    const first = progressiveLesson({ title: "单韵母朗读", assessmentMode: "observed", independentEvidenceCount: 5, independentCorrectCount: 5 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(progressivePath({ currentGradeLessons: [first], nextLesson: first }))));
    render(<LearningPath student={student} />);
    expect(await screen.findByText("这节课需要实际表现确认，答对选择题不代表已经掌握。")).toBeInTheDocument();
    expect(screen.queryByText("已掌握")).not.toBeInTheDocument();
  });

  it("shows higher-grade selection as a preview even if a response contains an eligible course", async () => {
    const course = { courseId: "future-course", courseVersion: "1" };
    const later = progressiveLesson({ lessonId: "ZH6A01.01", unitId: "ZH6A01", gradeCode: "primary_6", title: "观点事实证据", unitTitle: "观点事实证据", course, ...course });
    const fetch = vi.fn().mockResolvedValueOnce(reply(progressivePath())).mockResolvedValueOnce(reply(progressivePath({ gradeCode: "primary_6", currentGradeLessons: [later], nextLesson: later })));
    vi.stubGlobal("fetch", fetch);
    render(<LearningPath student={student} />);
    await screen.findByRole("heading", { name: "认读单韵母 a", level: 2 });
    fireEvent.change(screen.getByRole("combobox", { name: "查看年级" }), { target: { value: "primary_6" } });
    expect(await screen.findByText(/正在预览六年级课程目录/)).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("button", { name: "开始这一步" })).not.toBeInTheDocument();
    const summary = await screen.findByText("观点事实证据", { selector: ".learning-path-unit__title" });
    fireEvent.click(summary.closest("summary")!);
    expect(screen.getByRole("button", { name: "观点事实证据：目录预览" })).toBeDisabled();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("clears a failed state on retry without making up a ready route", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply({ message: "学习服务暂时不可用" }, 503)).mockResolvedValueOnce(reply(progressivePath()));
    vi.stubGlobal("fetch", fetch);
    render(<LearningPath student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("学习服务暂时不可用");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByRole("heading", { name: "认读单韵母 a", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("redirects an expired student session to unlock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ error: "student_session_required" }, 401)));
    render(<LearningPath student={student} />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/unlock"));
  });
});
