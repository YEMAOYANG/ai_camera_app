import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { homeworkStudentCorrectionSchema } from "@/lib/contracts/homework-tutor";
import { homeworkCorrectionCompleted, homeworkCorrectionWorkflowDone, HomeworkCorrectionStatus } from "./homework-correction-status";

const record = homeworkStudentCorrectionSchema.parse({ status: "in_progress", answerEvaluationAllowed: true,
  lastAnswer: "", attempts: 0, correct: null, updatedAt: 1, hintViewed: false, explanationViewed: true, tutorViewed: true,
  independent: null, scope: "same_question_correction", countsForAbility: false, lastAnswerTurnId: null, correctedAt: null });

describe("saved same-question correction status", () => {
  afterEach(cleanup);
  it("keeps a viewed explanation separate from an actual corrected answer", () => {
    render(<HomeworkCorrectionStatus correction={record} />);
    expect(screen.getByText("听完讲解，自己试试")).toBeVisible(); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument();
  });
  it("reports the server's successful new answer as a same-question correction, never mastery", () => {
    render(<HomeworkCorrectionStatus correction={{ ...record, status: "corrected", attempts: 1, correct: true }} />);
    expect(screen.getByText("这道题已订正")).toBeVisible(); expect(screen.getByText("同一道题已经答对，还要在复习时再试试。")).toBeVisible();
    expect(screen.queryByText(/已经掌握|独立完成/)).not.toBeInTheDocument();
  });
  it("shows another try for a saved incorrect answer without exposing a false completion", () => {
    render(<HomeworkCorrectionStatus correction={{ ...record, status: "needs_practice", attempts: 1, correct: false }} />);
    expect(screen.getByText("再试一次")).toBeVisible(); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument();
  });
  it.each([
    { ...record, status: "needs_review" as const, answerEvaluationAllowed: false },
    { ...record, status: "corrected" as const, answerEvaluationAllowed: false, attempts: 1, correct: true },
    { ...record, status: "corrected" as const, attempts: 0, correct: true },
  ])("does not claim correction with an unavailable reference or contradictory record: %j", correction => {
    render(<HomeworkCorrectionStatus correction={correction} />);
    expect(screen.getByText("参考答案还没核对清楚，这次不判断对错。")).toBeVisible(); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument();
  });
  it("rejects attempts to count same-question correction as independent ability", () => {
    expect(homeworkStudentCorrectionSchema.safeParse({ ...record, countsForAbility: true }).success).toBe(false);
    expect(homeworkStudentCorrectionSchema.safeParse({ ...record, independent: true }).success).toBe(false);
  });
  it("keeps paper acknowledgement out of verified correctness and requires a current reference", () => {
    const selfReported = { ...record, status: "self_reported" as const, selfReportedCompleted: true, selfReportedCompletedAt: 2 };
    render(<HomeworkCorrectionStatus correction={selfReported} />);
    expect(screen.getByText("已标记在纸上改好")).toBeVisible(); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument();
    expect(homeworkCorrectionCompleted(selfReported)).toBe(false); expect(homeworkCorrectionWorkflowDone(selfReported)).toBe(true);
    expect(homeworkCorrectionWorkflowDone({ ...selfReported, answerEvaluationAllowed: false })).toBe(false);
    expect(homeworkCorrectionWorkflowDone({ ...selfReported, selfReportedCompleted: false })).toBe(false);
  });
});
