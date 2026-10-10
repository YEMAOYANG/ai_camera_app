import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StudentSessionGate } from "./student-session-gate";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn(), refresh: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/learning/learning-textbooks", () => ({ LearningTextbooks: () => <div>已授权的教材课程库</div> }));
vi.mock("@/features/learning/learning-schoolbag", () => ({ LearningSchoolbag: () => <div>已授权的书包首页</div> }));
vi.mock("@/features/today/student-dashboard", () => ({ StudentDashboard: () => <div>已授权的今日课程</div> }));
vi.mock("@/features/learning/learning-library", () => ({ LearningLibrary: () => <div>已授权的课程库</div> }));
vi.mock("@/features/learning/learning-course-detail", () => ({ LearningCourseDetail: () => <div>已授权的课程详情</div> }));
vi.mock("@/features/learning/learning-practice", () => ({ LearningPractice: () => <div>已授权的练习</div> }));
vi.mock("@/features/learning/learning-path", () => ({ LearningPath: () => <div>已授权的学习路线</div> }));
vi.mock("@/features/classroom/classroom-entry", () => ({ ClassroomEntry: () => <div>已授权的课堂</div> }));

describe("StudentSessionGate", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it.each([[true, "/unlock"], [false, "/pair"]] as const)("keeps the 401 redirect when canUnlock is %s", async (canUnlock, destination) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ canUnlock }), { status: 401 }));
    vi.stubGlobal("fetch", fetch);
    render(<StudentSessionGate />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("main")).toHaveClass("student-session-screen");
    expect(screen.getByRole("main")).toHaveClass("mira-ui-surface");
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(destination));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.queryByText("已授权的今日课程")).not.toBeInTheDocument();
  });

  it("shows the real error without revealing protected content or account controls", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: "学习身份服务暂时不可用" }), { status: 503 })));
    render(<StudentSessionGate learningView="practice" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("学习身份服务暂时不可用");
    expect(screen.getByRole("alert")).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "休息一下" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "再试一次" })).toBeEnabled();
    expect(screen.queryByText("已授权的练习")).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("waits for a valid identity response before revealing the destination", async () => {
    let resolveIdentity!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { resolveIdentity = resolve; })));
    render(<StudentSessionGate learningView="course" courseId="math-1" />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("已授权的课程详情")).not.toBeInTheDocument();
    resolveIdentity(new Response(JSON.stringify({
      ok: true,
      student: { id: "student-1", childId: "child-1", displayName: "小米", gradeCode: "primary_6" },
      device: { id: "device-1", label: "学习设备" },
    })));
    expect(await screen.findByText("已授权的课程详情")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it.each([
    { lessonTaskId: "task-1", classroomMode: "openmaic" as const },
    { learningView: "reviews" as const, reviewId: "review-1" },
    { learningView: "homework" as const, submissionId: "homework-1" },
  ])("uses the same quiet loading state for destination %j", (props) => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<StudentSessionGate {...props} />);
    expect(screen.getByText("正在打开学习空间")).toBeInTheDocument();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("main")).toHaveClass("student-session-screen");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("rechecks identity on retry without reloading or revealing content early", async () => {
    let resolveRetry!: (response: Response) => void;
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ message: "连接断开" }), { status: 503 }))
      .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveRetry = resolve; }));
    vi.stubGlobal("fetch", fetch);
    render(<StudentSessionGate learningView="course" courseId="math-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "再试一次" }));
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("已授权的课程详情")).not.toBeInTheDocument();
    resolveRetry(new Response(JSON.stringify({
      ok: true, student: { id: "student-1", childId: "child-1", displayName: "小米", gradeCode: "primary_6" },
      device: { id: "device-1", label: "学习设备" },
    })));
    expect(await screen.findByText("已授权的课程详情")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(router.replace).not.toHaveBeenCalled();
  });

  it.each([undefined, "path", "library", "practice", "textbooks"] as const)("opens only the textbook library for entry %s after authentication", async (learningView) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true, student: { id: "student-1", childId: "child-1", displayName: "小米", gradeCode: "primary_1" },
      device: { id: "device-1", label: "学习设备" },
    }))));
    render(<StudentSessionGate learningView={learningView} />);
    expect(screen.queryByText("已授权的学习路线")).not.toBeInTheDocument();
    expect(await screen.findByText(learningView === "textbooks" ? "已授权的教材课程库" : "已授权的书包首页")).toBeInTheDocument();
    expect(screen.queryByText("已授权的今日课程")).not.toBeInTheDocument();
    expect(screen.queryByText("已授权的课程库")).not.toBeInTheDocument();
    expect(screen.queryByText("已授权的练习")).not.toBeInTheDocument();
  });
});
