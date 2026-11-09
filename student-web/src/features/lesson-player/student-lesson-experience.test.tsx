import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

afterEach(cleanup);

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

  const student = { id: "student-1", childId: "child-1", displayName: "乐乐" };
  const answeredCorrectly = {
    ok: true,
    correct: true,
    feedback: "答对了！",
    hint: null,
    canRetry: false,
    hintLevel: 0,
    nextQuestion: null,
    completed: false,
    session: { ...sessionFixture, correctCount: 1, attemptedCount: 1 },
    report: null,
  };
  const practiceWith = (currentQuestion: Record<string, unknown>) => ({
    ok: true,
    resumed: true,
    lesson: lessonFixture,
    session: { ...sessionFixture, currentQuestionIndex: 1, currentQuestion: { ...sessionFixture.currentQuestion, ...currentQuestion } },
  });
  // An icon is out of the reading order when it, or any element around it, is aria-hidden.
  const unhiddenIcons = (container: HTMLElement) =>
    Array.from(container.querySelectorAll("svg.lucide")).filter((icon) => !icon.closest("[aria-hidden='true']")).length;

  it("tells assistive technology which choice is picked and how far the lesson has gone", async () => {
    submitLearningAnswer.mockResolvedValue(answeredCorrectly);

    render(<StudentLessonExperience student={student} taskId="task-1" />);
    fireEvent.click(await screen.findByRole("button", { name: /一起看个例子/ }));
    fireEvent.click(screen.getByRole("button", { name: /轮到我来试试/ }));

    const choiceP = screen.getByRole("button", { name: "A.p" });
    const choiceB = screen.getByRole("button", { name: "B.b" });
    expect(choiceP).toHaveAttribute("aria-pressed", "false");
    expect(choiceB).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(choiceP);
    expect(choiceP).toHaveAttribute("aria-pressed", "true");
    expect(choiceB).toHaveAttribute("aria-pressed", "false");

    const progress = screen.getByRole("progressbar", { name: "答题进度" });
    expect(progress).toHaveAttribute("aria-valuemin", "0");
    expect(progress).toHaveAttribute("aria-valuemax", "4");
    expect(progress).toHaveAttribute("aria-valuenow", "0");
    expect(progress).toHaveAttribute("aria-valuetext", "已完成 0 题，共 4 题");

    fireEvent.click(screen.getByRole("button", { name: /提交答案/ }));
    expect(await screen.findByText("答对了！")).toBeInTheDocument();
    const answered = screen.getByRole("progressbar", { name: "答题进度" });
    expect(answered).toHaveAttribute("aria-valuenow", "1");
    expect(answered).toHaveAttribute("aria-valuetext", "已完成 1 题，共 4 题");
  });

  it("submits a typed answer with Enter, but not while a Chinese keyboard is still composing", async () => {
    startLearningSession.mockResolvedValue(practiceWith({ type: "numeric", inputMode: "numeric", choices: [] }));
    submitLearningAnswer.mockResolvedValue(answeredCorrectly);

    render(<StudentLessonExperience student={student} taskId="task-1" />);
    const input = await screen.findByLabelText("我的答案");
    expect(input).toHaveAttribute("enterkeyhint", "done");
    expect(input).toHaveAttribute("autocomplete", "off");

    fireEvent.keyDown(input, { key: "Enter" });
    expect(submitLearningAnswer).not.toHaveBeenCalled();

    fireEvent.change(input, { target: { value: "7" } });
    fireEvent.keyDown(input, { key: "7" });
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    expect(submitLearningAnswer).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("答对了！")).toBeInTheDocument();
    expect(submitLearningAnswer).toHaveBeenCalledTimes(1);
    expect(submitLearningAnswer).toHaveBeenCalledWith("session-1", { answer: "7" });
  });

  it("keeps decorative icons out of the reading order and names the finished steps", async () => {
    submitLearningAnswer.mockResolvedValue({
      ...answeredCorrectly,
      completed: true,
      session: { ...answeredCorrectly.session, status: "completed", currentQuestionIndex: 3 },
    });

    const { container } = render(<StudentLessonExperience student={student} taskId="task-1" />);
    const start = await screen.findByRole("button", { name: /一起看个例子/ });
    expect(unhiddenIcons(container)).toBe(0);

    fireEvent.click(start);
    expect(unhiddenIcons(container)).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: /轮到我来试试/ }));
    expect(screen.getByText("老师讲，已完成")).toBeInTheDocument();
    expect(screen.getByText("看示范，已完成")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "A.p" }));
    expect(unhiddenIcons(container)).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: /提交答案/ }));
    const summary = await screen.findByRole("button", { name: /看看我的小总结/ });
    expect(unhiddenIcons(container)).toBe(0);

    fireEvent.click(summary);
    expect(await screen.findByText("这节课完成啦")).toBeInTheDocument();
    expect(unhiddenIcons(container)).toBe(0);
  });

  it("hides the eraser icon on the reorder button of a sequence question", async () => {
    startLearningSession.mockResolvedValue(practiceWith({
      type: "sequence",
      inputMode: "sequence",
      choices: [{ id: "s1", label: "先" }, { id: "s2", label: "后" }],
    }));

    const { container } = render(<StudentLessonExperience student={student} taskId="task-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "先" }));
    expect(screen.getByRole("button", { name: /重新排列/ })).toBeInTheDocument();
    expect(unhiddenIcons(container)).toBe(0);
  });
});
