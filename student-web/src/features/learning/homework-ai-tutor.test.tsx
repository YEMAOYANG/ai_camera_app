import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
import { homeworkStudentQualitySchema, homeworkTutorAudioPath, homeworkTutorResponseSchema } from "@/lib/contracts/homework-tutor";
import { HomeworkAiTutor } from "./homework-ai-tutor";
import { HomeworkPaperOverview, homeworkTutorQuestions, homeworkPaperJudgment, practiceReady } from "./homework-paper-overview";
import { homeworkPaperStructureFixture } from "@/test/fixtures/homework-paper-structure";

// Recorder transport has its own tests; this suite exercises the tutor's
// intent, receipt and trust rules with a child's completed spoken question.
const spoken = vi.hoisted(() => ({ text: "为什么要这样做？请看着原题再解释一下。" }));
vi.mock("./homework-question-recorder", () => ({
  HomeworkQuestionRecorder: ({ disabled, onQuestion, actionLabel, intent }: { disabled?: boolean; actionLabel?: string; intent?: string; onQuestion: (text: string) => void }) => <form onSubmit={event => { event.preventDefault(); onQuestion((event.currentTarget.elements.namedItem("message") as HTMLTextAreaElement).value); }}><button type="button" disabled={disabled} onClick={() => onQuestion(spoken.text)}>说出我的问题</button><label htmlFor="mock-tutor-message">{intent === "answer" ? "写下你的答案和想法" : "写下你想问的"}</label><textarea id="mock-tutor-message" name="message" disabled={disabled} /><button type="submit" disabled={disabled}>{actionLabel}</button></form>,
}));

const id = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`, pageId = `hwp_${"c".repeat(32)}`, turnId = `hwt_${"d".repeat(32)}`;
const original = { id: itemId, revision: 1, prompt: "找出长方形", status: "unsupported", type: "geometry", tutorAvailable: true, assessmentMethod: "not_verified", reviewContext: { pageId, region: { x: .1, y: .1, width: .8, height: .3 }, originalAnswer: "A", originalOrdinal: 1 } };
const submission = homeworkDetailSchema.parse({ ok: true, submission: { id, title: "几何原作业", gradeCode: "primary_1", subject: "math", revision: 3, status: "needs_confirmation", items: [], tutorItems: [original], pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1200, height: 1600, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${pageId}/image` }], summary: { total: 0, corrected: 0, incorrect: 0 }, originalSummary: { total: 1, correct: 0, incorrect: 0, pending: 0, blank: 0, unsupported: 1 }, createdAt: 1, updatedAt: 1, readyForStudent: false } }).submission;
const item = homeworkTutorQuestions(submission)[0];
const turn = { id: turnId, mode: "explain", message: "", status: "ready", teacherText: "我们看看这两个图。", steps: [{ id: "1", text: "看看长方形的两条长边。", visual: { kind: "shapes", shapes: [{ shape: "rectangle", count: 2 }] } }, { id: "2", text: "再看看圆形。", visual: { kind: "shapes", shapes: [{ shape: "circle", count: 2 }] } }], assessment: { status: "guidance_only", method: "ai_guidance", countsForAbility: false }, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${turnId}/audio` }, errorCode: null, createdAt: 1 };
const snapshot = (turns: unknown[] = [], correction?: unknown) => ({ ok: true, tutor: { itemId, itemRevision: 1, enabled: true, voiceAvailable: true, turns, ...(correction ? { correction } : {}) } });
const startedCorrection = { status: "in_progress", answerEvaluationAllowed: true, lastAnswer: "", attempts: 0, correct: null, updatedAt: 1,
  hintViewed: false, explanationViewed: true, tutorViewed: true, independent: null, scope: "same_question_correction", countsForAbility: false, lastAnswerTurnId: null, correctedAt: null };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const postReply = (value: ReturnType<typeof snapshot>) => (_url: string, init: RequestInit) => {
  const request = JSON.parse(String(init.body));
  const turns = value.tutor.turns.map((saved, index) => index === value.tutor.turns.length - 1 ? { ...(saved as Record<string, unknown>), requestKey: request.idempotencyKey, mode: request.mode, message: request.message } : saved);
  return Promise.resolve(json({ ...value, tutor: { ...value.tutor, turns } }));
};
async function askTeacher(text = "为什么要这样做？请看着原题再解释一下。") {
  spoken.text = text;
  fireEvent.click(await screen.findByRole("button", { name: "问老师" }));
  fireEvent.click(screen.getByRole("button", { name: "说出我的问题" }));
}

describe("original-paper AI tutor", () => {
  beforeEach(() => vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() }; })));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("keeps the composer collapsed beside one listen action until asked, without starting recording or numbered history", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findByRole("button", { name: "听老师完整讲解" });
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled(); expect(screen.getByRole("button", { name: "提交订正答案" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "问老师" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); expect(screen.queryByRole("log", { name: "和老师的对话" })).not.toBeInTheDocument();
    for (const name of ["我没听懂", "为什么", "换个方法", "原题讲解"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); expect(screen.getByRole("button", { name: "说出我的问题" })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("records correction only after a new spoken answer receipt, keeps the original reference and does not turn listening into mastery", async () => {
    const quality = { status: "guidance", reason: "按原题参考讲解", method: "tencent_reference.v1", countsForAbility: false };
    const reference = { status: "unknown" as const, referenceAnswer: "5", analysis: "先数左边，再接着数。", knowledgePoints: ["数的合并"], geometryVerified: true, source: "tencent", studentQuality: { ...quality, status: "needs_review" as const, countsForAbility: false as const }, referenceGate: { available: true, method: "tencent_reference.v1", status: "provider_consistent" as const } };
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, grading: reference } };
    const lesson = { ...turn, teachingQuality: quality };
    const answerId = `hwt_${"f".repeat(32)}`, answered = { ...lesson, id: answerId, mode: "answer", message: "5", assessment: { ...turn.assessment, status: "correct" } };
    const corrected = { ...startedCorrection, status: "corrected", lastAnswer: "5", attempts: 1, correct: true, lastAnswerTurnId: answerId, correctedAt: 2, updatedAt: 2 };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([lesson], startedCorrection))).mockImplementationOnce(postReply(snapshot([lesson, answered], corrected))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "听老师完整讲解" }));
    expect(screen.getByText("听完讲解，自己试试")).toBeVisible(); expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("原题参考与解析")); expect(screen.getByText("原题参考答案")).toBeVisible(); expect(screen.getByText("先数左边，再接着数。")).toBeVisible();
    spoken.text = "5"; fireEvent.click(screen.getByRole("button", { name: "提交订正答案" })); fireEvent.click(screen.getByRole("button", { name: "说出我的问题" }));
    expect(await screen.findByText("这道题已订正")).toBeVisible();
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "answer", message: "5" });
    expect(reference.referenceAnswer).toBe("5"); expect(reference.analysis).toBe("先数左边，再接着数。"); expect(homeworkPaperJudgment(sourceItem)).toBe("unknown"); expect(practiceReady(submission, sourceItem)).toBe(false);
    expect(screen.queryByText(/已经掌握|独立完成/)).not.toBeInTheDocument();
  });
  it("uses the correction aggregate instead of a teacher assessment to decide whether an answer was corrected", async () => {
    const rejected = { ...startedCorrection, status: "needs_review", answerEvaluationAllowed: false };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([{ ...turn, assessment: { ...turn.assessment, status: "correct" } }], rejected))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByText("参考答案还没核对清楚，这次不判断对错。")).toBeVisible();
    expect(screen.queryByText("这道题已订正")).not.toBeInTheDocument(); expect(screen.queryByText("老师看过你的回答了，记得自己再想一遍")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交订正答案" })).toBeEnabled(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("formats a saved verified teacher step and picture labels without replaying audio or generating another lesson", async () => {
    const quality = { status: "verified", reason: "已核对原题", method: "original_image_quality.v1", countsForAbility: false };
    const saved = { ...turn, teachingQuality: quality, steps: [{ id: "comparison", text: String.raw`看图比较 $\boxed{4} \bigcirc \boxed{1}$。`, visual: { kind: "choices", choices: [{ id: "left", label: String.raw`$\boxed{>}$`, region: { x: .1, y: .1, width: .2, height: .1 } }, { id: "right", label: String.raw`$\boxed{<}$`, region: { x: .4, y: .1, width: .2, height: .1 } }] } }] };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([saved]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findByRole("button", { name: "选择第 1 张原题图片" });
    const stepFormula = container.querySelector(".homework-tutor-step figcaption .katex-html");
    expect(stepFormula).toBeVisible(); expect(stepFormula?.querySelectorAll(".fbox")).toHaveLength(2); expect(stepFormula?.textContent).toMatch(/[○◯]/);
    expect(stepFormula?.textContent).not.toMatch(/boxed|bigcirc|\\/);
    expect(container.querySelectorAll(".homework-tutor-picture-choice .fbox")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("keeps the complete original essay visible before any teacher call without inventing a question crop", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot())); vi.stubGlobal("fetch", fetch);
    const essay = { ...submission, analysisKind: "essay" as const, subject: "chinese", tutorItems: [{ ...original, type: "writing", assessmentMethod: "tencent_essay.v1", reviewContext: { ...original.reviewContext, region: null, originalAnswer: "", answerState: "unclear" as const } }] };
    render(<HomeworkAiTutor submission={essay} item={homeworkTutorQuestions(essay)[0]} onBack={vi.fn()} />);
    expect(await screen.findByRole("img", { name: "老师正在看的原作文照片" })).toBeVisible();
    await screen.findByRole("button", { name: "老师看看我的作文" });
    expect(screen.queryByText("原图位置还没确认")).not.toBeInTheDocument();
    expect(screen.queryByText("OCR识别，待核对")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("keeps server-verified essay guidance and audio available even when the source contains no located handwritten answer", async () => {
    const verified = { ...turn, reviewState: "not_required", reviewRetryAllowed: false, teachingQuality: { status: "verified", reason: "原作文讲解已核对", method: "original_image_quality.v1", countsForAbility: false }, sourceCheck: { status: "matched", basis: "original_image", questionReadable: true, answerLocated: false }, assessment: { ...turn.assessment, status: "needs_confirmation" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([verified]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={{ ...submission, analysisKind: "essay", subject: "chinese" }} item={item} onBack={vi.fn()} startOnOpen />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "原题暂未核实" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("shows arbitrary original questions without marking unverified work as wrong or starting paid AI", () => {
    const onTutor = vi.fn(); const { container } = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onRefresh={vi.fn()} onTutor={onTutor} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    expect(container.querySelector(".homework-paper-marker")).toBeNull();
    expect(screen.getByText("老师会直接看这张原图，再陪你讲解和解答")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "请老师看原题" })); expect(onTutor).toHaveBeenCalledWith(itemId);
    expect(screen.queryByText("暂不支持自动讲解")).not.toBeInTheDocument();
  });
  it("restores saved explanation quietly, presents one picture step at a time, and confines teacher audio to the current item", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(screen.queryByRole("img", { name: "2 个圆形" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "问老师" }));
    expect(screen.getByRole("textbox", { name: "写下你想问的" })).toBeEnabled(); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "下一步" })); expect(screen.getByRole("img", { name: "2 个圆形" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "听老师完整讲解" })); expect(globalThis.Audio).toHaveBeenCalledWith(`/api/learning/homework/${id}/items/${itemId}/tutor/${turnId}/audio`);
    expect(homeworkTutorAudioPath(turn.audio.assetUrl, id, `hwi_${"e".repeat(56)}`, turnId)).toBeNull();
    expect(homeworkTutorAudioPath("https://external.invalid/audio", id, itemId, turnId)).toBeNull();
  });
  it("fails closed for a legacy Tencent reference and lecture without a server quality decision", async () => {
    const sourceItem = { ...item, status: "pending", reviewContext: { ...item.reviewContext!, originalAnswer: "4", answerState: "written" as const, grading: { status: "incorrect" as const, referenceAnswer: "2", knowledgePoints: [], geometryVerified: true, source: "tencent" } } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible();
    expect(container.querySelectorAll(".homework-tutor-original-content .homework-paper-image")).toHaveLength(1);
    expect(container.querySelector(".homework-tutor-lesson .homework-paper-image")).toBeNull();
    expect(screen.queryByText("原图识别到的作答：")).not.toBeInTheDocument(); expect(screen.queryByText("4")).not.toBeInTheDocument(); expect(container.querySelector(".homework-tutor-original s")).toBeNull();
    expect(screen.queryByText("这是作业检查的参考结果，请听老师核对后再试试。")).not.toBeInTheDocument(); expect(screen.queryByText("2")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "问老师" })).not.toBeInTheDocument();
    expect(sourceItem.reviewContext.grading.status).toBe("incorrect"); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("keeps a completed unverified lecture as a terminal single-photo review, never repeating a paid request", async () => {
    const quality = { status: "needs_review", reason: "视觉人物位置尚未确认", method: "original_image_quality.v1", countsForAbility: false };
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, originalAnswer: "4", grading: { status: "incorrect" as const, referenceAnswer: "2", analysis: "雪雪排第二，答案是2。", knowledgePoints: [], geometryVerified: true, source: "tencent", providerVerdict: { status: "incorrect" as const, source: "tencent" as const, provisional: true as const, countsForAbility: false as const }, studentQuality: { ...quality, status: "needs_review" as const, countsForAbility: false as const } } } };
    const old = { ...turn, teachingQuality: quality, gradingReferenceComparison: { status: "consistent", reason: "两模型一致", referenceAnswer: "2", teacherAnswer: "2" }, teacherText: "答案就是2。", steps: [{ id: "bad", text: "答案就是2。", visual: { kind: "quantity", count: 2 } }] };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([old]))); vi.stubGlobal("fetch", fetch);
    const onBack = vi.fn(); const view = render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={onBack} startOnOpen />);
    await screen.findByRole("region", { name: "原题暂未核实" });
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(screen.getByText("这道题暂时不能确认，先看原图或换一道题；照片看不清时可以补拍。")).toBeVisible(); expect(screen.queryByText("答案就是2。")).not.toBeInTheDocument(); expect(screen.queryByText("雪雪排第二，答案是2。")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument(); expect(screen.queryByRole("group", { name: "接着问老师" })).not.toBeInTheDocument();
    expect(screen.queryByText("4")).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(view.container.querySelector(".homework-tutor-lesson .homework-paper-image")).toBeNull();
    expect(screen.queryByRole("button", { name: /^原题讲解(?: 1)?$/ })).not.toBeInTheDocument();
    fireEvent.load(screen.getByRole("img", { name: "可以点图做临时标记的原题照片" }));
    fireEvent.click(await screen.findByRole("button", { name: "点原图做临时标记" }));
    expect(screen.getByRole("button", { name: "临时标记，点一下移除" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "放大原图" }));
    expect(screen.getByRole("dialog", { name: "放大原图和临时圈记" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "回到题目" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(sourceItem.reviewContext.grading.status).toBe("incorrect");
    expect(screen.queryByText("老师正在看这道原题，准备图片讲解和声音…")).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "换一道题" })); expect(onBack).toHaveBeenCalledTimes(1);
    view.rerender(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={onBack} startOnOpen />); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("keeps a saved server review terminal free of status loops and restores verified steps only after a new opening reads them", async () => {
    const pending = { ...turn, reviewState: "required", reviewRetryAllowed: false, reviewReasonCode: "original_image_quality.v1", teachingQuality: { status: "needs_review", reason: "答案尚未核对", method: "original_image_quality.v1", countsForAbility: false }, audio: { status: "pending" } };
    const verified = { ...turn, reviewState: "not_required", reviewRetryAllowed: false, teachingQuality: { ...pending.teachingQuality, status: "verified", reason: "原题已核对" } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([pending]))).mockResolvedValue(json(snapshot([verified]))); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible();
    expect(screen.getByRole("region", { name: "老师原题讲解和接着问" })).toHaveAttribute("aria-busy", "false");
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "换一道题" })).toBeEnabled();
    view.unmount(); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("clears a definitively rejected new explanation, reads the saved review, and does not leave a waiting loop", async () => {
    const retryable = { ...turn, reviewState: "required", reviewRetryAllowed: true, sourceConfirmationOnly: true };
    const terminal = { ...retryable, reviewRetryAllowed: false };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([retryable]))).mockResolvedValueOnce(json({ ok: false, error: "homework_tutor_review_required", message: "这道原题还需核对" }, 409)).mockResolvedValue(json(snapshot([terminal]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "请老师再看看" }));
    expect(await screen.findByText("这道原题还需核对")).toBeVisible();
    expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "老师原题讲解和接着问" })).toHaveAttribute("aria-busy", "false");
    expect(fetch).toHaveBeenCalledTimes(3); expect(fetch.mock.calls[2][1].method).toBeUndefined();
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "查看准备情况" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("ends a lost retry receipt at the server's terminal review without inventing another paid key", async () => {
    const retryable = { ...turn, reviewState: "required", reviewRetryAllowed: true, sourceConfirmationOnly: true };
    const terminal = { ...retryable, reviewRetryAllowed: false };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([retryable]))).mockRejectedValueOnce(new Error("响应丢失")).mockResolvedValue(json(snapshot([terminal]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "请老师再看看" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "老师原题讲解和接着问" })).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByRole("button", { name: "查看准备情况" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it.each(["unknown", "failed"])("checks a saved %s receipt only with GET, never turning followups into another paid attempt", async status => {
    const receipt = { ...turn, status, reviewRetryAllowed: true, errorCode: status === "failed" ? "homework_tutor_response_invalid" : "homework_provider_unknown", teacherText: "", steps: [], assessment: null, audio: { status: "unavailable" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([receipt]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    await screen.findByRole("button", { name: "查看讲解状态" });
    expect(screen.queryByRole("button", { name: "问老师" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "提交订正答案" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "查看讲解状态" })); await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it.each(["unknown", "failed"])("does not submit a new paid followup by selecting verified history while the latest receipt is %s", async status => {
    const receipt = { ...turn, id: `hwt_${"f".repeat(32)}`, status, teacherText: "", steps: [], assessment: null, audio: { status: "unavailable" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn, { ...turn, id: `hwt_${"e".repeat(32)}`, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/hwt_${"e".repeat(32)}/audio` } }, receipt]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findByRole("button", { name: "查看讲解状态" });
    expect(screen.getByText("看看长方形的两条长边。")).toBeVisible();
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "问老师" })).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: "问老师" }));
    expect(screen.getByRole("button", { name: "问老师" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "问老师" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("textbox", { name: "写下你想问的" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "说出我的问题" })).toBeDisabled();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: "听老师完整讲解" }).filter(button => !button.hasAttribute("disabled"))).toHaveLength(1);
  });
  it("does not let a historical failed receipt block a later server-authorized ready guidance", async () => {
    const failed = { ...turn, id: `hwt_${"f".repeat(32)}`, status: "failed", teacherText: "", steps: [], assessment: null, audio: { status: "unavailable" } };
    const guidance = { ...turn, reviewState: "not_required", teachingQuality: { status: "guidance", reason: "这次讲解已检查", method: "source_guidance.v1", countsForAbility: false } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([failed, guidance]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "听老师完整讲解" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled();
    await askTeacher(); await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("shows a server-verified correction of four without using agreement with the old provider as proof", async () => {
    const quality = { status: "verified" as const, reason: "核对原图人物及顺序", method: "operator_confirmed", countsForAbility: false as const };
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, originalAnswer: "4", grading: { status: "correct" as const, referenceAnswer: "4", analysis: "原来从左向右第二，转身后从右向左第四。", knowledgePoints: [], geometryVerified: true, source: "tencent", studentQuality: quality } } };
    const verified = { ...turn, teachingQuality: quality, gradingReferenceComparison: { status: "conflict", reason: "腾讯旧答案2", referenceAnswer: "2", teacherAnswer: "4" }, steps: [{ id: "corrected", text: "五位同学，雪雪原来第二；转身后从右往左数，是第四。", visual: { kind: "paper_region" } }] };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([verified]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} startOnOpen />);
    expect(await screen.findByText("五位同学，雪雪原来第二；转身后从右往左数，是第四。")).toBeVisible();
    fireEvent.click(screen.getByText("核对后的答案与讲解")); expect(screen.getByText("核对后的答案")).toBeVisible();
    expect(screen.queryByText("2")).not.toBeInTheDocument(); expect(screen.queryByText("腾讯旧答案2")).not.toBeInTheDocument(); expect(screen.queryByText("参考结果有不同，老师陪你看原图核实")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("allows server-authorized picture guidance and followups without certifying the original paper grade", async () => {
    const pending = { status: "needs_review" as const, reason: "原作业检查还需核对", method: "original_image_quality.v1", countsForAbility: false as const };
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, originalAnswer: "4", grading: { status: "unknown" as const, referenceAnswer: "2", analysis: "未核实的旧答案2。", knowledgePoints: [], geometryVerified: true, source: "tencent", studentQuality: pending } } };
    const guidance = { ...turn, reviewState: "not_required", reviewRetryAllowed: false, teachingQuality: { ...pending, status: "guidance", reason: "当前题目定位和解题指导已检查" }, sourceConfirmationOnly: true, sourceImageReviewRequired: true, sourceCheck: { status: "matched", basis: "original_image", questionReadable: true, answerLocated: false }, assessment: { ...turn.assessment, status: "guidance_only" } };
    const followup = { ...guidance, id: `hwt_${"f".repeat(32)}`, mode: "followup", message: "为什么要这样做？请看着原题再解释一下。" };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([guidance]))).mockImplementationOnce(postReply(snapshot([guidance, followup]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} startOnOpen />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled(); expect(screen.getByRole("button", { name: "提交订正答案" })).toBeEnabled();
    expect(screen.queryByRole("region", { name: "原题暂未核实" })).not.toBeInTheDocument(); expect(screen.queryByText("未核实的旧答案2。")).not.toBeInTheDocument();
    expect(homeworkPaperJudgment(sourceItem)).toBe("unknown"); expect(practiceReady(submission, sourceItem)).toBe(false);
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    await askTeacher(); await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "followup" });
    expect(homeworkTutorResponseSchema.safeParse(snapshot([{ ...guidance, assessment: { ...guidance.assessment, countsForAbility: true } }])).success).toBe(false);
  });
  it("only offers playable lecture history after guidance, leaving quarantined old records inaccessible", async () => {
    const pause = vi.fn(); vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause }; }));
    const reviewed = { status: "verified", reason: "已核对", method: "original_image_quality.v1", countsForAbility: false };
    const old = { ...turn, reviewState: "required", reviewRetryAllowed: true, teachingQuality: { ...reviewed, status: "needs_review" }, steps: [{ id: "bad", text: "错误旧讲解答案2。", visual: { kind: "quantity", count: 2 } }] };
    const currentId = `hwt_${"f".repeat(32)}`;
    const current = { ...turn, id: currentId, teachingQuality: { ...reviewed, status: "guidance" }, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${currentId}/audio` } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([old, current]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "听老师完整讲解" })); expect(globalThis.Audio).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: /核对记录/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "已经保存的学习记录" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂停老师完整讲解" })).toBeEnabled(); expect(screen.queryByText("错误旧讲解答案2。")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "第 1 次追问" })).not.toBeInTheDocument();
    expect(globalThis.Audio).toHaveBeenCalledTimes(1); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("stops old audio when the current item's server quality changes to needs review", async () => {
    const pause = vi.fn(); vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause }; }));
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, grading: { status: "correct" as const, knowledgePoints: [], geometryVerified: true, source: "tencent", studentQuality: { status: "verified" as const, reason: "已核对", method: "original_image_quality.v1", countsForAbility: false as const } } } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn]))); vi.stubGlobal("fetch", fetch);
    // No teaching decision is a legacy Tencent lecture even when the paper was reviewed.
    const view = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "听老师完整讲解" }));
    view.rerender(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible(); expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(pause).toHaveBeenCalled(); expect(globalThis.Audio).toHaveBeenCalledTimes(1);
  });
  it("keeps reviewed diagram presets and numeric answers without offering an unsupported free question or recording", async () => {
    const reviewed = { ...turn, teachingQuality: { status: "verified", reason: "原图事实已核对", method: "operator_reviewed_order_reversal.v1", countsForAbility: false } };
    const answer = { ...reviewed, id: `hwt_${"f".repeat(32)}`, mode: "answer", message: "4" };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([reviewed]))).mockImplementationOnce(postReply(snapshot([reviewed, answer]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findByRole("button", { name: "听老师完整讲解" });
    fireEvent.click(screen.getByRole("button", { name: "问老师" }));
    expect(screen.getByRole("button", { name: "再讲简单一点" })).toBeEnabled();
    for (const label of ["我没听懂", "为什么", "换个方法"]) expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled(); expect(screen.queryByRole("button", { name: "说出我的问题" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "提交订正答案" }));
    const input = screen.getByRole("textbox", { name: "填一个数字给老师" }); expect(input).toHaveAttribute("inputmode", "numeric");
    fireEvent.change(input, { target: { value: "为什么" } }); expect(input).toHaveValue(""); expect(screen.getByRole("button", { name: "告诉老师我的数字" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "4" } }); fireEvent.click(screen.getByRole("button", { name: "告诉老师我的数字" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2)); expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "answer", message: "4" }); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("sends an approved diagram preset and preserves free questions for other verified lesson methods", async () => {
    const reviewed = { ...turn, teachingQuality: { status: "verified", reason: "原图事实已核对", method: "operator_reviewed_order_reversal.v1", countsForAbility: false } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([reviewed]))).mockImplementationOnce(postReply(snapshot([reviewed, { ...reviewed, id: `hwt_${"f".repeat(32)}`, mode: "followup" }]))); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "问老师" }));
    fireEvent.click(await screen.findByRole("button", { name: "再讲简单一点" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2)); expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "followup", message: "我还没有听懂，请用更简单的图片和短句再讲一次。" });
    view.unmount(); fetch.mockReset().mockResolvedValue(json(snapshot([{ ...turn, teachingQuality: { ...reviewed.teachingQuality, method: "verified_arithmetic.v1" } }])));
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "问老师" })); expect(screen.getByRole("button", { name: "说出我的问题" })).toBeEnabled(); expect(screen.queryByText("这道看图题的自由追问还需核实，先听核对好的讲解，也可以回答数字。")).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("uses the shared source context for a teacher paper step and qualifies a reference conflict without changing the paper verdict", async () => {
    const referenceComparison = { status: "conflict", reason: "private comparison detail", referenceAnswer: "2", teacherAnswer: "4" };
    const explanation = { ...turn, gradingReferenceComparison: referenceComparison, steps: [{ id: "look", text: "先看看题干上面的图。", visual: { kind: "paper_region", region: { x: .1, y: .48, width: .6, height: .04 } } }] };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([explanation]))); vi.stubGlobal("fetch", fetch);
    const structured = { ...submission, paperStructure: homeworkPaperStructureFixture(itemId, pageId) };
    render(<HomeworkAiTutor submission={structured} item={item} onBack={vi.fn()} />);
    const image = await screen.findByRole("img", { name: "老师正在讲解的原题图片" });
    expect(Number.parseFloat(image.style.top)).toBeCloseTo(-.078 / .574 * 100);
    expect(screen.getByText("参考结果有不同，老师陪你看原图核实")).toBeVisible();
    expect(screen.queryByText("private comparison detail")).not.toBeInTheDocument();
    expect(homeworkTutorResponseSchema.parse(snapshot([explanation])).tutor.turns[0].gradingReferenceComparison).toEqual(referenceComparison);
    expect(item.status).toBe("unsupported"); expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("does not treat a saved unclear explanation as a continuing preparation or a new paid review", async () => {
    const saved = { ...turn, sourceImageReviewRequired: false, sourceConfirmationOnly: true, assessment: { ...turn.assessment, status: "needs_confirmation" }, gradingReferenceComparison: { status: "unverified", reason: "" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([saved]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    await screen.findByRole("region", { name: "原题暂未核实" });
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("批改参考暂时无法核实，老师陪你看原图。")).not.toBeInTheDocument(); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument();
    expect(screen.queryByText("老师正在看这道原题，准备图片讲解和声音…")).not.toBeInTheDocument();
  });
  it.each(["answerLocated", "questionReadable"])("keeps a saved unclear source with %s false at the original photo without a status loop", async field => {
    const saved = { ...turn, sourceImageReviewRequired: false, sourceConfirmationOnly: false, teachingScope: "original_image_guidance", sourceCheck: { status: "unclear", basis: "original_image", questionLocated: true, questionReadable: true, answerLocated: true, [field]: false }, gradingReferenceComparison: { status: "unverified", reason: "当前答案位置尚未看清。" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([saved]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    await screen.findByRole("region", { name: "原题暂未核实" });
    expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });
  it("does not add a review action to an ordinary consistent saved explanation", async () => {
    const saved = { ...turn, sourceImageReviewRequired: false, sourceCheck: { status: "matched", basis: "original_image", questionLocated: true, questionReadable: true, answerLocated: true }, gradingReferenceComparison: { status: "consistent", reason: "参考一致。" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([saved]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} startOnOpen />);
    await screen.findByRole("button", { name: "听老师完整讲解" });
    expect(screen.queryByRole("button", { name: "请老师再看看原题" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("queues explanation only after a gesture and allows picture-supported followups without browser grading", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot())).mockResolvedValueOnce(json(snapshot([{ ...turn, status: "queued", steps: [], audio: { status: "pending" } }]), 202));
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "老师讲讲这道题" }));
    await screen.findByText("老师正在看这道原题，准备图片讲解和声音…");
    expect(fetch).toHaveBeenCalledTimes(2); const body = JSON.parse(fetch.mock.calls[1][1].body);
    expect(body).toEqual({ itemRevision: 1, mode: "explain", message: "", idempotencyKey: expect.any(String) }); expect(body).not.toHaveProperty("answer"); expect(body).not.toHaveProperty("correct");
    expect(globalThis.Audio).not.toHaveBeenCalled(); expect(screen.queryByRole("button", { name: "问老师" })).not.toBeInTheDocument();
  });
  it("reconciles a lost paid POST response with GET and does not dispatch another analysis", async () => {
    let requestKey = "";
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot())).mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") { requestKey = JSON.parse(String(init.body)).idempotencyKey; return Promise.reject(new Error("网络中断")); }
      return Promise.resolve(json(snapshot([{ ...turn, requestKey, status: "working", createdAt: 1, steps: [], audio: { status: "pending" } }])));
    });
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "老师讲讲这道题" }));
    await screen.findByText("老师正在看这道原题，准备图片讲解和声音…");
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(fetch.mock.calls.at(-1)?.[1].method).toBeUndefined();
  });
  it("opens the recovered new followup instead of leaving the already selected old lecture on screen", async () => {
    const message = "为什么要这样做？请看着原题再解释一下。", followup = { ...turn, id: `hwt_${"f".repeat(32)}`, mode: "followup", message, createdAt: 1, steps: [{ id: "followup-step", text: "因为长方形的对边长度相等。", visual: { kind: "shapes", shapes: [{ shape: "rectangle", count: 1, color: "blue" }] } }] };
    let requestKey = "";
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn]))).mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") { requestKey = JSON.parse(String(init.body)).idempotencyKey; return Promise.reject(new Error("响应丢失")); }
      return Promise.resolve(json(snapshot([turn, { ...followup, requestKey }])));
    });
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await askTeacher();
    expect(await screen.findByText("因为长方形的对边长度相等。")).toBeVisible(); expect(screen.getByText("看看长方形的两条长边。")).toBeVisible(); expect(screen.getByRole("log", { name: "和老师的对话" })).not.toContainElement(screen.getByText("看看长方形的两条长边。"));
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(screen.queryByRole("navigation", { name: "已经保存的学习记录" })).not.toBeInTheDocument();
  });
  it("matches the exact second request key when the same followup is asked again, independent of server clock and historical missing keys", async () => {
    const message = "为什么要这样做？请看着原题再解释一下。", previous = { ...turn, requestKey: "first-request", mode: "followup", message, createdAt: Date.now() + 60_000 };
    let requestKey = "", includeNewReceipt = false;
    const fresh = { ...turn, id: `hwt_${"f".repeat(32)}`, mode: "followup", message, createdAt: 1, steps: [{ id: "new-step", text: "这是第二次追问的新回答。", visual: { kind: "shapes", shapes: [{ shape: "rectangle", count: 1 }] } }] };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([previous, { ...previous, id: `hwt_${"e".repeat(32)}`, requestKey: undefined }]))).mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") { requestKey = JSON.parse(String(init.body)).idempotencyKey; return Promise.reject(new Error("响应丢失")); }
      return Promise.resolve(json(snapshot(includeNewReceipt ? [previous, { ...fresh, requestKey }] : [previous, { ...previous, id: `hwt_${"e".repeat(32)}`, requestKey: undefined }])));
    });
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findAllByText("看看长方形的两条长边。"); await askTeacher();
    await screen.findByText("响应丢失"); expect(screen.getByRole("button", { name: "问老师" })).toBeDisabled(); expect(screen.queryByRole("button", { name: "第 1 次追问" })).not.toBeInTheDocument();
    expect(requestKey).not.toBe("first-request"); includeNewReceipt = true;
    fireEvent.click(screen.getByRole("button", { name: "查看回答状态" }));
    expect(await screen.findByText("这是第二次追问的新回答。")).toBeVisible(); expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
  it("identifies the displayed step when picture options have repeated ids across steps", async () => {
    const options = [{ id: "choice-1", label: "A", region: { x: .1, y: .1, width: .2, height: .1 } }, { id: "choice-2", label: "B", region: { x: .4, y: .1, width: .2, height: .1 } }];
    const choices = { ...turn, steps: [{ id: "step-a", text: "先看第一组。", visual: { kind: "choices", choices: options } }, { id: "step-b", text: "再看第二组。", visual: { kind: "choices", choices: options } }] };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([choices]))).mockImplementationOnce(postReply(snapshot([choices, { ...turn, id: `hwt_${"f".repeat(32)}`, mode: "answer", message: "在第 2 步（step-b），我选择第 2 张图，选项 B。" }])));
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    await screen.findByRole("button", { name: "选择第 2 张原题图片" }); fireEvent.click(screen.getByRole("button", { name: "下一步" })); fireEvent.click(screen.getByRole("button", { name: "选择第 2 张原题图片" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2)); expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "answer", message: "在第 2 步（step-b），我选择第 2 张图，选项 B。" });
  });
  it("supports a child's own answer and unrestricted typed followup in higher grades using distinct server modes", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn]))).mockImplementationOnce(postReply(snapshot([turn, { ...turn, id: `hwt_${"e".repeat(32)}`, mode: "answer", message: "因为对边一样长", createdAt: 2 }])));
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={{ ...submission, gradeCode: "primary_4" }} item={item} onBack={vi.fn()} />);
    await screen.findByText("看看长方形的两条长边。"); fireEvent.click(screen.getByRole("button", { name: "提交订正答案" }));
    fireEvent.change(screen.getByRole("textbox", { name: "写下你的答案和想法" }), { target: { value: "因为对边一样长" } });
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "answer", message: "因为对边一样长", itemRevision: 1 });
  });
  it("never turns AI guidance into confirmed ability evidence", () => {
    const guidance = { status: "guidance", reason: "只用于老师讲解", method: "source_guidance.v1", countsForAbility: false };
    expect(homeworkTutorResponseSchema.safeParse(snapshot([turn])).success).toBe(true);
    expect(homeworkTutorResponseSchema.safeParse(snapshot([{ ...turn, teachingQuality: guidance }])).success).toBe(true);
    expect(homeworkStudentQualitySchema.safeParse(guidance).success).toBe(false);
    expect(homeworkTutorResponseSchema.safeParse(snapshot([{ ...turn, assessment: { ...turn.assessment, countsForAbility: true } }])).success).toBe(false);
    expect(homeworkTutorResponseSchema.safeParse(snapshot([{ ...turn, teachingQuality: { status: "verified", reason: "已核对", method: "operator_confirmed", countsForAbility: true } }])).success).toBe(false);
  });
  it("starts one explanation only after an explicit workspace teacher click and keeps ordinary entry read-only", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot())).mockResolvedValueOnce(json(snapshot([turn]))); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "explain", itemRevision: 1 });
    view.rerender(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(fetch).toHaveBeenCalledTimes(2); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("uses an explicit teacher entry for one server-allowed source review and reopens the resulting guidance with GET only", async () => {
    const pending = { status: "needs_review", reason: "旧来源需要核对", method: "original_image_quality.v1", countsForAbility: false };
    const legacy = { ...turn, reviewState: "required", reviewRetryAllowed: true, teachingQuality: pending, sourceConfirmationOnly: true, sourceImageReviewRequired: true, teacherText: "未核实的旧答案2。" };
    const guidanceId = `hwt_${"f".repeat(32)}`;
    const guidance = { ...turn, id: guidanceId, reviewState: "not_required", reviewRetryAllowed: false, teachingQuality: { ...pending, status: "guidance", reason: "当前题目讲解已检查" }, sourceConfirmationOnly: false, sourceImageReviewRequired: false, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${guidanceId}/audio` } };
    let accepted = false;
    const fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") accepted = true;
      return Promise.resolve(json(snapshot(accepted ? [legacy, guidance] : [legacy])));
    }); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled(); expect(screen.queryByText("未核实的旧答案2。")).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    view.rerender(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />); expect(fetch).toHaveBeenCalledTimes(2);
    view.unmount(); render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible(); expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("keeps normal entry into a server-allowed source review read-only until another explicit teacher gesture", async () => {
    const legacy = { ...turn, reviewState: "required", reviewRetryAllowed: true, sourceConfirmationOnly: true };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([legacy]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "请老师再看看" })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("reuses saved image guidance without a second paid explanation when opening from the workspace", async () => {
    const observed = { ...turn, teachingScope: "original_image_guidance", sourceCheck: { status: "mismatch", basis: "original_image", questionLocated: true, questionReadable: true, answerLocated: true, studentAnswerReadable: false, answerOrdinal: 1 } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([observed]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(await screen.findByText("老师重新看原图，发现和先前识别有不同；这次按原图讲解。")).toBeVisible();
    expect(screen.getByRole("img", { name: "2 个长方形" })).toBeVisible(); expect(fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("follows the accepted queue through working to ready with read-only checks and one paid submission", async () => {
    const queued = { ...turn, requestKey: "accepted-one", status: "queued", teacherText: "", steps: [], assessment: null, audio: { status: "pending", errorCode: null } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot())).mockResolvedValueOnce(json(snapshot([queued]), 202))
      .mockResolvedValueOnce(json(snapshot([{ ...queued, status: "working" }]))).mockResolvedValueOnce(json(snapshot([turn])));
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "看看准备情况" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(screen.getByText("老师正在看这道原题，准备图片讲解和声音…")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "看看准备情况" }));
    expect(await screen.findByRole("img", { name: "2 个长方形" })).toBeVisible();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("replaces a legacy confirmation only on a new explicit click allowed by the server", async () => {
    const legacy = { ...turn, reviewRetryAllowed: true, sourceConfirmationOnly: true, teacherText: "先让家长核对", assessment: { ...turn.assessment, status: "needs_confirmation" } };
    const observed = { ...turn, id: `hwt_${"f".repeat(32)}`, teachingScope: "original_image_guidance", sourceCheck: { status: "matched", basis: "original_image" } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([legacy]))).mockResolvedValueOnce(json(snapshot([legacy, observed]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "请老师再看看" }));
    expect(await screen.findByText("老师直接看原图讲解，原作业的批改记录仍保留。")).toBeVisible();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("does not charge to re-open a legacy confirmation when the server has not allowed a retry", async () => {
    const legacy = { ...turn, sourceConfirmationOnly: true, assessment: { ...turn.assessment, status: "needs_confirmation" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([legacy]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible(); expect(screen.queryByRole("button", { name: "看看核对状态" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("blocks an old full-page image lecture and its audio when a zoom review is required, even with original-image basis", async () => {
    const old = { ...turn, reviewRetryAllowed: true, sourceImageReviewRequired: true, teachingScope: "original_image_guidance", sourceCheck: { status: "matched", basis: "original_image" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([old]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible();
    expect(screen.getByRole("button", { name: "请老师再看看" })).toBeEnabled(); expect(screen.queryByRole("button", { name: "问老师" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument(); expect(screen.queryByRole("img", { name: "2 个长方形" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("requests one allowed zoom explanation after a gesture and stops at a new unclear result", async () => {
    const old = { ...turn, reviewRetryAllowed: true, sourceImageReviewRequired: true, teachingScope: "original_image_guidance", sourceCheck: { status: "matched", basis: "original_image" } };
    const unclear = { ...turn, id: `hwt_${"f".repeat(32)}`, sourceImageReviewRequired: false, sourceConfirmationOnly: true, assessment: { ...turn.assessment, status: "needs_confirmation" }, sourceCheck: { status: "unclear", basis: "original_image", questionLocated: true, questionReadable: false }, audio: { status: "unavailable", errorCode: "homework_tutor_source_unconfirmed" }, steps: [{ id: "look", text: "有些字还没看清，先不猜答案。", visual: { kind: "paper_region", region: { x: .1, y: .1, width: .8, height: .3 } } }] };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([old]))).mockResolvedValueOnce(json(snapshot([old, unclear]))); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "请老师再看看" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("region", { name: "原题暂未核实" })).toBeVisible();
    expect(screen.queryByText("有些字还没看清，先不猜答案。")).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(screen.queryByRole("button", { name: "请老师再看看" })).not.toBeInTheDocument();
    view.rerender(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />); expect(fetch).toHaveBeenCalledTimes(2);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("does not charge again when re-opening an already completed but unclear zoom review", async () => {
    const unclear = { ...turn, sourceImageReviewRequired: false, sourceConfirmationOnly: true, assessment: { ...turn.assessment, status: "needs_confirmation" }, audio: { status: "unavailable", errorCode: "homework_tutor_source_unconfirmed" } };
    const fetch = vi.fn().mockResolvedValue(json(snapshot([unclear]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(await screen.findByRole("region", { name: "原题暂未核实" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "请老师重新看原图" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("queries a lost zoom-review receipt without resubmitting the older full-page lecture", async () => {
    const old = { ...turn, reviewRetryAllowed: true, sourceImageReviewRequired: true, teachingScope: "original_image_guidance", sourceCheck: { status: "matched", basis: "original_image" } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([old]))).mockRejectedValueOnce(new Error("响应丢失")).mockResolvedValue(json(snapshot([old]))); vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "请老师再看看" }));
    expect(await screen.findByText("响应丢失")).toBeVisible(); expect(screen.getByRole("button", { name: "请老师再看看" })).toBeDisabled();
    view.rerender(<HomeworkAiTutor submission={submission} item={item} startOnOpen onBack={vi.fn()} />);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(fetch.mock.calls.at(-1)?.[1].method).toBeUndefined();
    expect(screen.queryByRole("button", { name: "听老师完整讲解" })).not.toBeInTheDocument(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("exposes only the explicit unconfigured-audio recovery, without restarting vision on entry", async () => {
    const missing = { ...turn, audio: { status: "unavailable", errorCode: "homework_audio_unconfigured" } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([missing]))).mockResolvedValueOnce(json(snapshot([{ ...missing, audio: { status: "pending" } }])));
    vi.stubGlobal("fetch", fetch); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "准备老师语音" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2)); expect(fetch.mock.calls[1][0]).toBe(`/api/learning/homework/${id}/items/${itemId}/tutor/${turnId}/audio`);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ itemRevision: 1, idempotencyKey: expect.any(String) });
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
});
