import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StudentSessionGate } from "./student-session-gate";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn(), refresh: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/student/space-shell", () => ({
  SpaceShell: ({ children, active, scenic }: { children: ReactNode; active: string; scenic: boolean }) => (
    <div data-testid="session-shell" data-active={active} data-scenic={String(scenic)}><main>{children}</main></div>
  ),
}));
vi.mock("@/features/today/student-dashboard", () => ({ StudentDashboard: () => <div>已授权的今日课程</div> }));
vi.mock("@/features/learning/learning-library", () => ({ LearningLibrary: () => <div>已授权的课程库</div> }));
vi.mock("@/features/learning/learning-course-detail", () => ({ LearningCourseDetail: () => <div>已授权的课程详情</div> }));
vi.mock("@/features/learning/learning-practice", () => ({ LearningPractice: () => <div>已授权的练习</div> }));
vi.mock("@/features/classroom/classroom-entry", () => ({ ClassroomEntry: () => <div>已授权的课堂</div> }));

describe("StudentSessionGate", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it.each([[true, "/unlock"], [false, "/pair"]] as const)("keeps the 401 redirect when canUnlock is %s", async (canUnlock, destination) => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ canUnlock }), { status: 401 }));
    vi.stubGlobal("fetch", fetch);
    render(<StudentSessionGate />);
    expect(screen.getByTestId("session-shell")).toHaveAttribute("data-active", "today");
    expect(screen.getByTestId("session-shell")).toHaveAttribute("data-scenic", "true");
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(destination));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(screen.queryByText("已授权的今日课程")).not.toBeInTheDocument();
  });

  it("keeps the selected navigation and the real error without revealing protected content", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: "学习身份服务暂时不可用" }), { status: 503 })));
    render(<StudentSessionGate learningView="practice" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("学习身份服务暂时不可用");
    expect(screen.getByTestId("session-shell")).toHaveAttribute("data-active", "practice");
    expect(screen.getByTestId("session-shell")).toHaveAttribute("data-scenic", "false");
    expect(screen.getByRole("button", { name: "再试一次" })).toBeEnabled();
    expect(screen.queryByText("已授权的练习")).not.toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("waits for a valid identity response before revealing the destination", async () => {
    let resolveIdentity!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { resolveIdentity = resolve; })));
    render(<StudentSessionGate learningView="course" courseId="math-1" />);
    expect(screen.getByTestId("session-shell")).toHaveAttribute("data-active", "learning");
    expect(screen.queryByText("已授权的课程详情")).not.toBeInTheDocument();
    resolveIdentity(new Response(JSON.stringify({
      ok: true,
      student: { id: "student-1", childId: "child-1", displayName: "小米", gradeCode: "primary_6" },
      device: { id: "device-1", label: "学习设备" },
    })));
    expect(await screen.findByText("已授权的课程详情")).toBeInTheDocument();
  });

  it("keeps classroom identity loading outside the sidebar shell", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    render(<StudentSessionGate lessonTaskId="task-1" classroomMode="openmaic" />);
    expect(screen.getByText("正在打开学习空间")).toBeInTheDocument();
    expect(screen.queryByTestId("session-shell")).not.toBeInTheDocument();
  });
});
