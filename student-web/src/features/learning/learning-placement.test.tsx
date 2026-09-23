import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LearningPlacement } from "@/features/learning/learning-placement";
import { placementResponseSchema, type PlacementResponse } from "@/lib/contracts/learning-placement";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const attemptId = `placement_${"a".repeat(32)}`;
const questionId = (index: number) => `placementq_${String(index).padStart(32, "0")}`;
const lesson = { lessonId: "M1A01.01", title: "逐个点数 1—5 个物体", gradeCode: "primary_1", subject: "math", assessmentMode: "objective" } as const;
const available: PlacementResponse = {
  ok: true, schemaVersion: "mira.learning.placement.v1", subject: "math", status: "available", message: "先独立试一试。",
  lesson, canStart: true, attempt: null, fallbackPath: "/learning/path?subject=math",
};
function progress(index: number, passed = true): PlacementResponse {
  return { ...available, status: index === 5 ? "completed" : "in_progress", canStart: false, attempt: {
    id: attemptId, status: index === 5 ? "completed" : "in_progress", currentQuestionIndex: index, totalQuestions: 5, answeredCount: index,
    currentQuestion: index === 5 ? null : { id: questionId(index), index, type: "numeric", prompt: `第 ${index + 1} 个问题`, skill: "点数", attemptNumber: 1, inputMode: "numeric_text", choices: [] },
    result: index === 5 ? { passed, correctCount: passed ? 5 : 2, totalQuestions: 5, accuracy: passed ? 1 : 0.4, masteryStatus: passed ? "mastered" : "needs_practice" } : null,
  } };
}
const reply = (payload: unknown) => new Response(JSON.stringify(payload));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("基础摸底的学生流程", () => {
  it("waits for explicit start, submits only answers and refreshes the path after completion", async () => {
    let cursor = 0;
    const fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method !== "POST") return reply(available);
      return reply(JSON.parse(String(init.body)).lessonId ? progress(0) : progress(++cursor));
    });
    vi.stubGlobal("fetch", fetch);
    const onResolved = vi.fn();
    render(<LearningPlacement subject="math" onResolved={onResolved} onReturnToLesson={vi.fn()} />);
    const start = await screen.findByRole("button", { name: "先试一试" });
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(start);
    for (let index = 0; index < 5; index++) {
      await screen.findByRole("heading", { name: `第 ${index + 1} 个问题` });
      fireEvent.change(screen.getByRole("textbox", { name: "你的答案" }), { target: { value: "3" } });
      fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    }
    await screen.findByRole("heading", { name: "这一步已经学会了" });
    expect(fetch.mock.calls.slice(2).map(([, init]) => JSON.parse(String(init?.body)))).toEqual(
      Array.from({ length: 5 }, (_, index) => ({ questionId: questionId(index), answer: "3" })),
    );
    expect(onResolved).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "继续下一步" }));
    expect(onResolved).toHaveBeenCalledOnce();
    const privateQuestion = progress(0);
    expect(placementResponseSchema.safeParse({ ...privateQuestion, attempt: { ...privateQuestion.attempt,
      currentQuestion: { ...privateQuestion.attempt!.currentQuestion, answer: "3" } } }).success).toBe(false);
  });

  it("resumes the saved cursor and preserves the same answer after an uncertain network response", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply(progress(4)))
      .mockRejectedValueOnce(new Error("连接中断"))
      .mockResolvedValueOnce(reply(progress(5, false)));
    vi.stubGlobal("fetch", fetch);
    const onResolved = vi.fn();
    render(<LearningPlacement subject="math" onResolved={onResolved} onReturnToLesson={vi.fn()} />);
    await screen.findByRole("heading", { name: "第 5 个问题" });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1].method).toBe("GET");
    fireEvent.change(screen.getByRole("textbox", { name: "你的答案" }), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
    expect(screen.getByRole("textbox", { name: "你的答案" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "重新保存这个答案" }));
    await screen.findByRole("heading", { name: "找到需要再练的地方了" });
    expect(fetch.mock.calls[1][1].body).toBe(fetch.mock.calls[2][1].body);
    fireEvent.click(screen.getByRole("button", { name: "回到基础课" }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledOnce());
  });
});
