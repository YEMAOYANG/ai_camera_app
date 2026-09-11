import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LearningPractice } from "./learning-practice";
import { practiceAnswerSchema, practiceResponseSchema, practiceStartSchema } from "@/lib/contracts/learning-practice";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const student = { id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" };
const questionId = "a".repeat(64), sessionId = `practice_${"b".repeat(32)}`;
const question = { id: questionId, type: "numeric", prompt: "十个一和两个一，合起来是多少？", choices: [] };
const active = { ok: true, schemaVersion: "mira.learning.practice.v1", fallbackPath: "/learning", session: {
  id: sessionId, gradeCode: "primary_1", subject: "math", skillId: null, status: "in_progress",
  currentQuestionIndex: 0, totalQuestions: 1, correctCount: 0, currentQuestion: question, completedAt: null,
} };
const completed = { ...active, session: { ...active.session, status: "completed", currentQuestionIndex: 1,
  correctCount: 1, currentQuestion: null, completedAt: 1000 }, evaluation: { questionId, correct: true,
  status: "correct", message: "答对啦！", explanation: "一个十和两个一合起来是十二。", evaluatorVersion: "deterministic-v1" } };
const respond = (value: unknown) => Promise.resolve({ ok: true, json: async () => value });

describe("completed-course revision", () => {
  beforeEach(() => { replace.mockReset(); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("takes a bounded set, submits only the response, and displays authoritative feedback and completion", async () => {
    const fetch = vi.fn().mockImplementationOnce(() => respond(active)).mockImplementationOnce(() => respond(completed));
    vi.stubGlobal("fetch", fetch);
    const view = render(<LearningPractice student={student} />);
    fireEvent.click(screen.getByRole("button", { name: "开始复习" }));
    expect(await screen.findByRole("heading", { name: question.prompt })).toBeInTheDocument();
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ subject: "math", count: 5 });
    expect(replace).toHaveBeenCalledWith(`/learning/practice?session=${sessionId}`);
    view.rerender(<LearningPractice student={student} sessionId={sessionId} />);
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("你的答案"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(await screen.findByRole("heading", { name: "答对啦！" })).toBeInTheDocument();
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ questionId, response: "12" });
    expect(screen.getByText(completed.evaluation.explanation)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "看看这次练习" }));
    expect(screen.getByRole("heading", { name: "这次复习完成啦！" })).toBeInTheDocument();
    expect(screen.getByText("完成 1 题，答对 1 题。")).toBeInTheDocument();
  });

  it("resumes the saved session without drawing or generating more questions", async () => {
    const fetch = vi.fn().mockImplementation(() => respond(active));
    vi.stubGlobal("fetch", fetch);
    render(<LearningPractice student={student} sessionId={sessionId} />);
    expect(await screen.findByRole("heading", { name: question.prompt })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe(`/api/learning/practice/sessions/${sessionId}`);
    expect(fetch.mock.calls[0][1].method).toBe("GET");
  });

  it("links back to completed lessons when no unseen approved questions remain", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => respond({ ...active, session: null, availableCount: 0,
      message: "暂时没有新的复习题，先回学习书架复习学过的课程吧。" })));
    render(<LearningPractice student={student} />);
    fireEvent.click(screen.getByRole("button", { name: "开始复习" }));
    expect(await screen.findByRole("link", { name: "先复习学过的课程" })).toHaveAttribute("href", "/learning");
    expect(screen.queryByRole("heading", { name: question.prompt })).not.toBeInTheDocument();
  });

  it("keeps the same request identity after an uncertain admission and keeps answers on failed submission", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error("连接中断，请重试"))
      .mockImplementationOnce(() => respond(active)).mockRejectedValueOnce(new Error("答案暂未保存"));
    vi.stubGlobal("fetch", fetch);
    render(<LearningPractice student={student} />);
    fireEvent.click(screen.getByRole("button", { name: "开始复习" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
    fireEvent.click(screen.getByRole("button", { name: "开始复习" }));
    expect(await screen.findByRole("heading", { name: question.prompt })).toBeInTheDocument();
    expect(JSON.parse(fetch.mock.calls[0][1].body).requestId).toBe(JSON.parse(fetch.mock.calls[1][1].body).requestId);
    fireEvent.change(screen.getByLabelText("你的答案"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("答案暂未保存"));
    expect(screen.getByLabelText("你的答案")).toHaveValue("12");
  });

  it("rejects caller-supplied identity and grades and strips private answer fields from public questions", () => {
    expect(practiceStartSchema.safeParse({ requestId: "test", subject: "math", childId: "other" }).success).toBe(false);
    expect(practiceStartSchema.safeParse({ requestId: "test", subject: "math", count: 6 }).success).toBe(false);
    expect(practiceAnswerSchema.safeParse({ questionId, response: "12", correct: true }).success).toBe(false);
    const parsed = practiceResponseSchema.parse({ ...active, session: { ...active.session,
      currentQuestion: { ...question, answer: "12", evaluation: { acceptedAnswers: ["12"] } } } });
    expect(parsed.session?.currentQuestion).not.toHaveProperty("answer");
    expect(parsed.session?.currentQuestion).not.toHaveProperty("evaluation");
  });
});
