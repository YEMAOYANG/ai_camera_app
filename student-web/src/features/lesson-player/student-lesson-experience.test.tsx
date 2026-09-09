import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudentLessonExperience } from "@/features/lesson-player/student-lesson-experience";
import { lessonFixture, sessionFixture } from "@/test/fixtures/learning";

const { startLearningSession, submitLearningAnswer, getLatestLearningReport } = vi.hoisted(() => ({
  startLearningSession: vi.fn(),
  submitLearningAnswer: vi.fn(),
  getLatestLearningReport: vi.fn(),
}));

vi.mock("@/features/learning/learning-client", () => ({
  startLearningSession,
  submitLearningAnswer,
  getLatestLearningReport,
}));

describe("StudentLessonExperience", () => {
  beforeEach(() => {
    startLearningSession.mockReset();
    submitLearningAnswer.mockReset();
    getLatestLearningReport.mockReset();
    startLearningSession.mockResolvedValue({ ok: true, resumed: false, lesson: lessonFixture, session: sessionFixture });
  });

  it("runs teach, worked example and guided practice in order", async () => {
    submitLearningAnswer.mockResolvedValue({
      ok: true,
      correct: true,
      feedback: "答对了！p 是“苹”开头的声母。",
      hint: null,
      canRetry: false,
      hintLevel: 0,
      nextQuestion: { ...sessionFixture.currentQuestion, id: "q3", prompt: "下一题" },
      completed: false,
      session: { ...sessionFixture, currentQuestionIndex: 1, correctCount: 1, attemptedCount: 1 },
      report: null,
    });

    render(<StudentLessonExperience student={{ id: "student-1", childId: "child-1", displayName: "乐乐" }} taskId="task-1" />);

    expect(await screen.findByText("声母住在音节的最前面")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /一起看个例子/ }));
    expect(screen.getByText("“妈妈”的“妈”开头是什么声母？")).toBeInTheDocument();
    expect(screen.getByText("答案是")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /轮到我来试试/ }));
    expect(screen.getByText("“苹果”的“苹”开头是什么声母？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "A.p" }));
    fireEvent.click(screen.getByRole("button", { name: /提交答案/ }));
    expect(await screen.findByText("答对了！p 是“苹”开头的声母。")).toBeInTheDocument();
    expect(submitLearningAnswer).toHaveBeenCalledWith("session-1", {
      response: { kind: "single_choice", optionId: "choice-p" },
    });
  });
});
