import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StudentDashboard } from "@/features/today/student-dashboard";
import { todayFixture } from "@/test/fixtures/learning";

const { getTodayLearning, assignTodayLearning, replace, refresh } = vi.hoisted(() => ({
  getTodayLearning: vi.fn(),
  assignTodayLearning: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));
vi.mock("@/features/learning/learning-client", () => ({ getTodayLearning, assignTodayLearning }));

describe("StudentDashboard", () => {
  afterEach(cleanup);

  beforeEach(() => {
    getTodayLearning.mockReset();
    assignTodayLearning.mockReset();
    getTodayLearning.mockResolvedValue(todayFixture);
  });

  it("shows three real daily courses with child-friendly start actions", async () => {
    render(<StudentDashboard student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);

    expect(await screen.findByText("拼音声母小侦探")).toBeInTheDocument();
    expect(screen.getByText("20以内加法小实验")).toBeInTheDocument();
    expect(screen.getByText("Hello! 见面问好")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /开始这节课/ })[0]).toHaveAttribute("href", "/lesson/task-1/classroom");
    expect(screen.getByText("一年级 · 今天有 3 节小课。老师会先讲清楚，再陪你一起练。")).toBeInTheDocument();
  });

  it("updates preparation progress and hides it automatically when the first lesson is ready", async () => {
    getTodayLearning.mockResolvedValueOnce({
      ...todayFixture, items: [], itemCount: 0, completedCount: 0,
      catalogStatus: "preparing", availableCourseCount: 0, preparationProgressPercent: 10,
    }).mockResolvedValueOnce({
      ...todayFixture, items: [], itemCount: 0, completedCount: 0,
      catalogStatus: "preparing", availableCourseCount: 0, preparationProgressPercent: 35,
    }).mockResolvedValue({
      ...todayFixture, items: todayFixture.items.slice(0, 1), itemCount: 1, completedCount: 0,
      catalogStatus: "preparing", availableCourseCount: 1, preparationProgressPercent: 35,
    });
    render(<StudentDashboard student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} pollIntervalMs={50} />);
    expect(await screen.findByText("10%")).toBeInTheDocument();
    const progress = screen.getByRole("progressbar", { name: "新课准备进度" });
    expect(progress).toHaveAttribute("aria-valuenow", "10");
    expect(screen.getByText("老师正在认真备课")).toBeInTheDocument();
    expect(screen.queryByText(/Mira 正在/)).not.toBeInTheDocument();
    expect(await screen.findByText("35%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "新课准备进度" })).toBe(progress);
    expect(progress).toHaveAttribute("aria-valuenow", "35");
    expect(await screen.findByRole("link", { name: /开始这节课/ })).toHaveAttribute("href", "/lesson/task-1/classroom");
    expect(screen.queryByRole("progressbar", { name: "新课准备进度" })).not.toBeInTheDocument();
    expect(screen.queryByText("35%")).not.toBeInTheDocument();
  });

  it("keeps ready courses usable and explains paused supply without spinning placeholders", async () => {
    getTodayLearning.mockResolvedValue({
      ...todayFixture, items: todayFixture.items.slice(0, 1), itemCount: 1,
      catalogStatus: "preparing", availableCourseCount: 1, preparationProgressPercent: 35,
      courseSupply: { schemaVersion: "learning.course-supply-summary.v1", version: "v1", requestedCount: 3, readyCount: 1,
        paused: true, retryAfterMs: 30000, lastProgressAt: 1, message: "新课需要调整，已有课程可以继续学。" },
    });
    render(<StudentDashboard student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByText("拼音声母小侦探")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar", { name: "新课准备进度" })).not.toBeInTheDocument();
    expect(screen.queryByText("35%")).not.toBeInTheDocument();
    expect(screen.getAllByText("小课堂还需要一点调整")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /开始这节课/ })).toHaveAttribute("href", "/lesson/task-1/classroom");
    expect(screen.queryByText("老师正在认真备课")).not.toBeInTheDocument();
  });

  it("does not invent a percentage while progress is unavailable", async () => {
    getTodayLearning.mockResolvedValue({
      ...todayFixture, items: [], itemCount: 0, catalogStatus: "preparing",
      availableCourseCount: 0, preparationProgressPercent: null,
    });
    render(<StudentDashboard student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);
    expect(await screen.findByText("正在获取进度")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "新课准备进度" })).not.toHaveAttribute("aria-valuenow");
  });

  it("explains a bounded carryover and offers a clear continue action", async () => {
    getTodayLearning.mockResolvedValue({
      ...todayFixture,
      carryoverCount: 1,
      newCount: 2,
      backlogCount: 2,
      items: todayFixture.items.map((item, index) => index === 0 ? {
        ...item,
        dayBucket: "carryover" as const,
        originDate: "2026-08-12",
        carryover: {
          id: "carry-1",
          reason: "missed_unstarted" as const,
          originDate: "2026-08-12",
          targetDate: "2026-08-13",
          daysOverdue: 1,
        },
      } : item),
    });

    render(<StudentDashboard student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} />);

    expect(await screen.findByText("昨天未完成 · 继续学")).toBeInTheDocument();
    expect(screen.getByText(/今天只顺延一节/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /继续未完成的课/ })).toHaveAttribute(
      "href",
      "/lesson/task-1/classroom",
    );
    expect(screen.getByText(/先补上 1 节没学完的课/)).toBeInTheDocument();
  });

  it("shows the first ready lesson immediately and fills later slots without flicker", async () => {
    getTodayLearning
      .mockResolvedValueOnce({
        ...todayFixture,
        catalogStatus: "preparing",
        availableCourseCount: 1,
        itemCount: 1,
        items: todayFixture.items.slice(0, 1),
      })
      .mockResolvedValue(todayFixture);

    render(
      <StudentDashboard
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        pollIntervalMs={10}
      />,
    );

    expect(await screen.findByText("拼音声母小侦探")).toBeInTheDocument();
    expect(screen.getByText(/今天已有 1 节小课可以学/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar", { name: "新课准备进度" })).not.toBeInTheDocument();
    expect(screen.getAllByText("完成后自动出现")).toHaveLength(2);
    expect(await screen.findByText("20以内加法小实验")).toBeInTheDocument();
    expect(getTodayLearning).toHaveBeenCalledTimes(2);
  });
});
