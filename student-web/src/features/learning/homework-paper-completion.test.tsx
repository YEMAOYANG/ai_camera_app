import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { homeworkActionSchema, homeworkDetailSchema } from "@/lib/contracts/homework";
import { homeworkStudentCorrectionSchema } from "@/lib/contracts/homework-tutor";
import { HomeworkPaperCompletion } from "./homework-paper-completion";
import { homeworkTutorQuestions } from "./homework-paper-overview";

const submissionId = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`, pageId = `hwp_${"c".repeat(32)}`;
const correction = homeworkStudentCorrectionSchema.parse({ status: "in_progress", answerEvaluationAllowed: true, lastAnswer: "", attempts: 0, correct: null, updatedAt: 1, hintViewed: false, explanationViewed: false, tutorViewed: false, independent: null, scope: "same_question_correction", countsForAbility: false, lastAnswerTurnId: null, correctedAt: null, selfReportedCompleted: false, selfReportedCompletedAt: null });
function detail(saved = correction) {
  return homeworkDetailSchema.parse({ ok: true, submission: { id: submissionId, title: "树上的苹果", gradeCode: "primary_1", subject: "math", revision: 3, status: "ready", items: [], tutorItems: [{ id: itemId, revision: 1, prompt: "数苹果", status: "incorrect", tutorAvailable: true, studentCorrection: saved, reviewContext: { pageId, region: { x: .1, y: .1, width: .5, height: .2 }, originalAnswer: "5", originalOrdinal: 1, grading: { status: "incorrect", referenceAnswer: "3", analysis: "数第二棵树的苹果。", knowledgePoints: [], geometryVerified: true, referenceGate: { available: true, method: "tencent_reference.v1", status: "provider_consistent" } } } }], summary: { total: 1, corrected: 0, incorrect: 1, selfReportedCompleted: saved.selfReportedCompleted ? 1 : 0 }, createdAt: 1, updatedAt: 1, readyForStudent: false } });
}
const acknowledged = homeworkStudentCorrectionSchema.parse({ ...correction, status: "self_reported", selfReportedCompleted: true, selfReportedCompletedAt: 2, updatedAt: 2 });
const initial = detail(), submission = initial.submission, item = homeworkTutorQuestions(submission)[0];
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
describe("paper correction acknowledgement", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("saves and reopens only a separate acknowledgement with no answer or tutor call", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(detail(acknowledged))).mockResolvedValueOnce(json(initial)), onData = vi.fn(); vi.stubGlobal("fetch", fetch);
    render(<HomeworkPaperCompletion submission={submission} item={item} onData={onData} />);
    fireEvent.click(screen.getByRole("button", { name: "我在纸上改好了" })); await screen.findByRole("button", { name: "继续订正" });
    const request = JSON.parse(fetch.mock.calls[0][1].body); expect(request).toEqual({ itemRevision: 1, action: "self_complete", idempotencyKey: expect.any(String) }); expect(fetch.mock.calls[0][0]).toBe(`/api/learning/homework/${submissionId}/items/${itemId}/actions`);
    expect(onData).toHaveBeenCalledWith(detail(acknowledged)); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续订正" })); await screen.findByRole("button", { name: "我在纸上改好了" });
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ action: "reopen" }); expect(JSON.parse(fetch.mock.calls[1][1].body).idempotencyKey).not.toBe(request.idempotencyKey);
    expect(fetch.mock.calls.every(([url]) => !String(url).includes("tutor") && !String(url).includes("answers"))).toBe(true);
  });
  it("disables double-click and after response loss only reads current state", async () => {
    let release!: (value: Response) => void; const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { release = resolve; })).mockResolvedValueOnce(json(initial)).mockResolvedValueOnce(json(detail(acknowledged))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkPaperCompletion submission={submission} item={item} />); const complete = screen.getByRole("button", { name: "我在纸上改好了" }); fireEvent.click(complete); fireEvent.click(complete); expect(fetch).toHaveBeenCalledTimes(1);
    release(json({ message: "响应暂未确认" }, 502)); await screen.findByRole("button", { name: "查看订正标记" }); expect(screen.getByRole("button", { name: "我在纸上改好了" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "查看订正标记" })); await screen.findByRole("button", { name: "继续订正" });
    expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1); expect(fetch.mock.calls.slice(1).every(([url, options]) => url === `/api/learning/homework/${submissionId}` && options.cache === "no-store" && !options.method)).toBe(true);
  });
  it("clears the response-loss message when a read confirms the saved acknowledgement", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error("响应暂未确认")).mockResolvedValueOnce(json(detail(acknowledged))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkPaperCompletion submission={submission} item={item} />); fireEvent.click(screen.getByRole("button", { name: "我在纸上改好了" })); await screen.findByRole("button", { name: "继续订正" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "查看订正标记" })).not.toBeInTheDocument(); expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1);
  });
  it("never lets a fresh correct answer remain hidden by an old paper acknowledgement", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(detail(acknowledged))));
    const view = render(<HomeworkPaperCompletion submission={submission} item={item} />); fireEvent.click(screen.getByRole("button", { name: "我在纸上改好了" })); await screen.findByRole("button", { name: "继续订正" });
    view.rerender(<HomeworkPaperCompletion submission={submission} item={{ ...item, studentCorrection: { ...correction, status: "corrected", attempts: 1, correct: true, updatedAt: 2 } }} />);
    expect(screen.queryByRole("button", { name: "继续订正" })).not.toBeInTheDocument();
  });
  it("uses a refreshed reopen state even when the actual answer timestamp does not change", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(detail(acknowledged))));
    const view = render(<HomeworkPaperCompletion submission={submission} item={item} />); fireEvent.click(screen.getByRole("button", { name: "我在纸上改好了" })); await screen.findByRole("button", { name: "继续订正" });
    view.rerender(<HomeworkPaperCompletion submission={submission} item={{ ...item, studentCorrection: { ...correction, updatedAt: acknowledged.updatedAt } }} />);
    expect(screen.getByRole("button", { name: "我在纸上改好了" })).toBeEnabled(); expect(screen.queryByRole("button", { name: "继续订正" })).not.toBeInTheDocument();
  });
  it("rejects stale question data instead of applying another revision's acknowledgement", async () => {
    const stale = detail(acknowledged); stale.submission.revision = 4; const onData = vi.fn(), fetch = vi.fn().mockResolvedValue(json(stale)); vi.stubGlobal("fetch", fetch);
    render(<HomeworkPaperCompletion submission={submission} item={item} onData={onData} />); fireEvent.click(screen.getByRole("button", { name: "我在纸上改好了" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("原题已更新")); expect(screen.queryByRole("button", { name: "继续订正" })).not.toBeInTheDocument(); expect(fetch.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1);
  });
  it.each([
    { ...item, studentCorrection: { ...correction, answerEvaluationAllowed: false } },
    { ...item, studentCorrection: { ...correction, status: "corrected" as const, correct: true, attempts: 1 } },
    { ...item, reviewContext: { ...item.reviewContext!, grading: { ...item.reviewContext!.grading!, referenceGate: { available: false, method: "blocked", status: "needs_review" as const } } } },
    { ...item, reviewContext: { ...item.reviewContext!, grading: { ...item.reviewContext!.grading!, status: "correct" as const } } },
  ])("does not offer an acknowledgement for unavailable references, right answers or actual correction", question => {
    render(<HomeworkPaperCompletion submission={submission} item={question} />); expect(screen.queryByRole("button", { name: "我在纸上改好了" })).not.toBeInTheDocument();
  });
  it("requires idempotency for workflow writes and rejects self scoring fields", () => {
    expect(homeworkActionSchema.safeParse({ action: "self_complete", itemRevision: 1 }).success).toBe(false);
    expect(homeworkActionSchema.safeParse({ action: "self_complete", itemRevision: 1, idempotencyKey: "one", correct: true }).success).toBe(false);
    expect(homeworkActionSchema.safeParse({ action: "reopen", itemRevision: 1, idempotencyKey: "one" }).success).toBe(true);
    expect(homeworkActionSchema.safeParse({ action: "hint", itemRevision: 1 }).success).toBe(true);
  });
});
