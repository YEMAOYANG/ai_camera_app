import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClassroomEntry } from "@/features/classroom/classroom-entry";
import { LearningClientError } from "@/features/learning/learning-client";
import type { LearningStartResponse } from "@/lib/contracts/learning";
import {
  openMaicFormalRuntimeLaunchSchema,
  type OpenMaicFormalRuntimeLaunch,
} from "@/lib/contracts/openmaic-runtime";
import { lessonFixture, sessionFixture } from "@/test/fixtures/learning";
import { formalRuntimeLaunchFixture } from "@/test/fixtures/openmaic-runtime";

vi.mock("@/features/classroom/classroom-player", async () => {
  const actual = await vi.importActual<typeof import("@/features/classroom/classroom-player")>(
    "@/features/classroom/classroom-player",
  );
  return {
    ...actual,
    ClassroomPlayer: () => <div>mira-classroom-player</div>,
  };
});

vi.mock("@/features/lesson-player/student-lesson-experience", () => ({
  StudentLessonExperience: () => <div>mira-student-lesson-experience</div>,
}));

afterEach(cleanup);

function v2Launch(): OpenMaicFormalRuntimeLaunch {
  return openMaicFormalRuntimeLaunchSchema.parse(formalRuntimeLaunchFixture);
}

describe("classroom release gate", () => {
  it("shows production preparation instead of the legacy question shell for the explicit release error", async () => {
    const startSession = async () => {
      throw new LearningClientError(
        409,
        "learning_classroom_preparing",
        "这节课还在完成课件与声音制作，请稍后再来",
      );
    };
    render(<ClassroomEntry student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }} taskId="task-1" startSession={startSession} />);
    expect(await screen.findByText("课程制作中")).toBeInTheDocument();
    expect(screen.getByText("老师正在把课件和声音准备好")).toBeInTheDocument();
    expect(screen.queryByText("提交答案")).not.toBeInTheDocument();
  });

  it("opens the pinned full OpenMAIC classroom inside the Mira and WarmSight classroom shell", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    const launch = v2Launch();
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={async () => start}
        launchRuntime={async () => launch}
      />,
    );

    const frame = await screen.findByTitle("拼音声母小侦探完整互动课堂");
    expect(frame).toHaveAttribute("src", launch.launchUrl);
    expect(frame).toHaveAttribute("allow", "microphone; autoplay; fullscreen");
    expect(frame).toHaveAttribute("allowfullscreen");
    expect(frame.closest("main")).toHaveClass("full-openmaic-shell");
    expect(frame.closest("main")).toHaveAccessibleName("完整互动课堂");
    expect(screen.getByRole("navigation", { name: "课堂导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回课程列表" })).toHaveAttribute("href", "/learning");
    expect(screen.getByText("暖瞳课堂")).toBeInTheDocument();
    expect(screen.getByLabelText("Mira 学习空间")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/open\s*maic/i);
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.queryByText(/开始学习检测/)).not.toBeInTheDocument();
  });

  it("shares one start and runtime launch while StrictMode re-runs the entry effect", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    const startSession = vi.fn(async () => start);
    const launchRuntime = vi.fn(async () => v2Launch());

    render(
      <StrictMode>
        <ClassroomEntry
          student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
          taskId="task-1"
          mode="openmaic"
          startSession={startSession}
          launchRuntime={launchRuntime}
        />
      </StrictMode>,
    );

    await screen.findByTitle("拼音声母小侦探完整互动课堂");
    expect(startSession).toHaveBeenCalledTimes(1);
    expect(launchRuntime).toHaveBeenCalledTimes(1);
  });

  it("hides the host loading overlay after the runtime iframe loads", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };

    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={async () => start}
        launchRuntime={async () => v2Launch()}
      />,
    );

    const frame = await screen.findByTitle("拼音声母小侦探完整互动课堂");
    expect(screen.getByText("正在请老师进入课堂…")).toBeInTheDocument();

    fireEvent.load(frame);

    expect(screen.queryByText("正在请老师进入课堂…")).not.toBeInTheDocument();
  });

  it("keeps the reviewed Mira player as a compatibility fallback when full runtime is disabled", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        startSession={async () => start}
        launchRuntime={async () => {
          throw new LearningClientError(404, "openmaic_runtime_disabled", "完整课堂尚未启用");
        }}
      />,
    );

    expect(await screen.findByText("mira-student-lesson-experience")).toBeInTheDocument();
  });

  it("never falls back when the dedicated full-runtime route is unavailable", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={async () => start}
        launchRuntime={async () => {
          throw new LearningClientError(404, "openmaic_runtime_not_available", "完整课堂运行服务没有就绪");
        }}
      />,
    );

    expect(await screen.findByRole("heading", { name: "完整互动课堂暂时打不开" })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/open\s*maic/i);
    expect(screen.getByText("完整课堂运行服务没有就绪")).toBeInTheDocument();
    expect(screen.queryByText("mira-classroom-player")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-student-lesson-experience")).not.toBeInTheDocument();
  });

  it("rechecks a failed formal classroom in place without reloading the page", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: true,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    const startSession = vi.fn(async () => start);
    let launchAttempt = 0;
    const launchRuntime = vi.fn(async () => {
      launchAttempt += 1;
      if (launchAttempt === 1) {
        throw new LearningClientError(
          503,
          "openmaic_runtime_not_available",
          "完整互动课堂暂时不可用",
        );
      }
      return v2Launch();
    });

    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={startSession}
        launchRuntime={launchRuntime}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "重新检查" }));

    expect(await screen.findByTitle("拼音声母小侦探完整互动课堂")).toBeInTheDocument();
    expect(startSession).toHaveBeenCalledTimes(2);
    expect(launchRuntime).toHaveBeenCalledTimes(2);
  });

  it("uses a full document transition after runtime discovery without flashing a fallback", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    const navigateToRuntime = vi.fn();
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        startSession={async () => start}
        launchRuntime={async () => v2Launch()}
        navigateToRuntime={navigateToRuntime}
      />,
    );

    await waitFor(() => expect(navigateToRuntime).toHaveBeenCalledWith("/lesson/task-1/classroom"));
    expect(screen.queryByTitle("拼音声母小侦探完整互动课堂")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-classroom-player")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-student-lesson-experience")).not.toBeInTheDocument();
  });

  it("does not downgrade a discovered classroom whose Qwen readiness contract is invalid", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        startSession={async () => start}
        launchRuntime={async () => {
          throw new LearningClientError(
            502,
            "openmaic_runtime_contract_invalid",
            "课堂暂时无法打开，请稍后重试；若仍无法打开，请联系管理员。",
          );
        }}
      />,
    );

    expect(await screen.findByRole("heading", { name: "完整互动课堂暂时打不开" })).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/open\s*maic/i);
    expect(screen.queryByText("mira-classroom-player")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-student-lesson-experience")).not.toBeInTheDocument();
  });

  it("opens a complete v2 runtime without adding Mira capability chrome", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={async () => start}
        launchRuntime={async () => v2Launch()}
      />,
    );

    expect(await screen.findByTitle("拼音声母小侦探完整互动课堂")).toBeInTheDocument();
    expect(screen.queryByText("互动游戏")).not.toBeInTheDocument();
    expect(screen.queryByText("视频课件")).not.toBeInTheDocument();
    expect(screen.queryByText("3D 探索")).not.toBeInTheDocument();
  });

  it("fails closed without an iframe while runtime review is still pending", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: false,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={async () => start}
        launchRuntime={async () => {
          throw new LearningClientError(
            409,
            "openmaic_runtime_review_pending",
            "完整课堂仍在检查老师音色和正式语音",
          );
        }}
      />,
    );

    expect(await screen.findByRole("heading", { name: "老师正在把课件和声音准备好" })).toBeInTheDocument();
    expect(screen.getByText("完整课堂仍在检查老师音色和正式语音")).toBeInTheDocument();
    expect(screen.queryByTitle("拼音声母小侦探完整互动课堂")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-classroom-player")).not.toBeInTheDocument();
    expect(screen.queryByText("mira-student-lesson-experience")).not.toBeInTheDocument();
  });

  it("automatically rechecks a preparing classroom without reloading the document", async () => {
    const start: LearningStartResponse = {
      ok: true,
      resumed: true,
      session: sessionFixture,
      lesson: lessonFixture,
    };
    const startSession = vi.fn(async () => start);
    let launchAttempt = 0;
    const launchRuntime = vi.fn(async () => {
      launchAttempt += 1;
      if (launchAttempt === 1) {
        throw new LearningClientError(
          409,
          "openmaic_runtime_review_pending",
          "完整课堂仍在检查老师音色和正式语音",
        );
      }
      return v2Launch();
    });
    const navigateToRuntime = vi.fn();

    render(
      <ClassroomEntry
        student={{ id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" }}
        taskId="task-1"
        mode="openmaic"
        startSession={startSession}
        launchRuntime={launchRuntime}
        navigateToRuntime={navigateToRuntime}
        preparingRetryMs={10}
      />,
    );

    expect(await screen.findByRole("heading", { name: "老师正在把课件和声音准备好" })).toBeInTheDocument();
    expect(await screen.findByTitle("拼音声母小侦探完整互动课堂")).toBeInTheDocument();
    expect(startSession).toHaveBeenCalledTimes(2);
    expect(launchRuntime).toHaveBeenCalledTimes(2);
    expect(navigateToRuntime).not.toHaveBeenCalled();
  });
});
