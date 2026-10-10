import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { homeworkDetailSchema, type HomeworkDetail, type HomeworkItem, type HomeworkPage } from "@/lib/contracts/homework";
import { HomeworkWorkspace } from "./learning-homework";
import { HomeworkCollection, HomeworkGradingDetails, HomeworkOriginalQuestion, HomeworkPaperImage, HomeworkPaperOverview, HomeworkQuestionPicture, homeworkPaperJudgment, homeworkPaperDisplayJudgment, practiceReady } from "./homework-paper-overview";
import { homeworkPaperStructureFixture } from "@/test/fixtures/homework-paper-structure";

const id = `hw_${"a".repeat(32)}`;
const pageId = `hwp_${"b".repeat(32)}`;
const secondPageId = `hwp_${"c".repeat(32)}`;
const page = (identity: string, order: number): HomeworkPage => ({ id: identity, order, rotation: 0, crop: null, width: 1200, height: 1600, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${identity}/image` });
const picture = { kind: "quantity_arithmetic" as const, operation: "add" as const, left: 3, right: 2, choices: [{ id: "n4", count: 4 }, { id: "n5", count: 5 }, { id: "n6", count: 6 }] };
function item(digit: string, ordinal: number, originalAnswer: string, y: number, patch: Partial<HomeworkItem> = {}): HomeworkItem {
  const identity = `hwi_${digit.repeat(56)}`;
  return {
    id: identity, revision: 1, prompt: ordinal === 7 ? "4 + 3 =" : "3 + 2 =", status: "incorrect", readyForStudent: true, correctionStatus: "pending", hintViewed: false, explanationViewed: false,
    picture: ordinal === 7 ? { ...picture, left: 4, right: 3, choices: [{ id: "n6", count: 6 }, { id: "n7", count: 7 }, { id: "n8", count: 8 }] } : picture,
    reviewContext: { pageId, region: { x: .1, y, width: .45, height: .12 }, originalAnswer, originalOrdinal: ordinal, sourceQuestionLabel: String(ordinal), answerState: "written", recognitionConfirmed: true, recognitionNeedsConfirmation: false },
    voice: Object.fromEntries(["prompt", "hint", "explanation", "success", "retry"].map(kind => [kind, { assetUrl: `/api/v2/student/learning/homework/${id}/items/${identity}/audio/${kind}`, status: "ready" }])),
    ...patch,
  };
}
const first = item("1", 3, "4", .1);
const seventh = item("2", 7, "6", .4);
const corrected = item("3", 10, "4", .7, { correctionStatus: "corrected" });
const waiting = item("4", 12, "4", .1, { readyForStudent: false, reviewContext: { pageId: secondPageId, region: null, originalAnswer: "4", originalOrdinal: 12, sourceQuestionLabel: "12", answerState: "written", recognitionConfirmed: true, recognitionNeedsConfirmation: false } });
function snapshot(): HomeworkDetail {
  return homeworkDetailSchema.parse({ ok: true, submission: {
    id, title: "q", gradeCode: "primary_1", subject: "math", source: "parent_app", revision: 5, status: "ready", processing: false, readyForStudent: true,
    pages: [page(pageId, 0), page(secondPageId, 1)], items: [first, seventh, corrected, waiting],
    summary: { total: 4, corrected: 1, incorrect: 4 }, originalSummary: { total: 9, correct: 4, incorrect: 4, blank: 0, pending: 0, unsupported: 1 }, studentSummary: { ready: 3, awaitingMedia: 1, unsupportedCorrection: 0, corrected: 1 },
    createdAt: Date.UTC(2026, 8, 30, 6), updatedAt: Date.UTC(2026, 8, 30, 6),
  } });
}
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
function expectPhotoPath(image: HTMLElement, identity: string) {
  const url = new URL(image.getAttribute("src")!, window.location.origin);
  expect(url.origin).toBe(window.location.origin);
  expect(url.pathname).toBe(`/api/learning/homework/${id}/pages/${identity}/image`);
  expect(url.search).toBe("");
}

describe("original homework before teacher correction", () => {
  beforeEach(() => vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn(), removeAttribute: vi.fn() }; })));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("excludes paper acknowledgements from pending work without changing original wrong marks or verified correction", () => {
    const correction = { status: "self_reported" as const, answerEvaluationAllowed: true, lastAnswer: "", attempts: 0, correct: null, updatedAt: 1, hintViewed: false, explanationViewed: false, tutorViewed: false, independent: null, scope: "same_question_correction" as const, countsForAbility: false as const, lastAnswerTurnId: null, correctedAt: null, selfReportedCompleted: true, selfReportedCompletedAt: 2 };
    const source = { ...first, tutorAvailable: true, studentCorrection: correction };
    const submission = { ...snapshot().submission, items: [source, seventh], summary: { total: 2, corrected: 0, incorrect: 2, selfReportedCompleted: 1 }, originalPaperSummary: { total: 2, correct: 0, incorrect: 2, unknown: 0 } };
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onTutor={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText("再看看 2")).toBeVisible(); expect(screen.getByText("纸上改好 1")).toBeVisible(); expect(screen.getByRole("button", { name: "先看错题 1" })).toBeEnabled();
    expect(practiceReady(submission, source)).toBe(false); expect(homeworkPaperJudgment(source)).toBe("incorrect");
    fireEvent.click(screen.getByRole("button", { name: "全部原题 2" })); fireEvent.click(screen.getByRole("button", { name: "看看原题 3" }));
    expect(screen.getByText("纸上已改好，未复测")).toBeVisible(); expect(screen.getByRole("button", { name: "继续订正" })).toBeEnabled(); expect(container.querySelector(".homework-selected-judgment")).toHaveAttribute("data-status", "incorrect"); expect(screen.queryByText("已订正")).not.toBeInTheDocument();
  });

  it("refreshes saved correction with GET when leaving the teacher and preserves the selected original page and question", async () => {
    const correction = { status: "in_progress", answerEvaluationAllowed: true, lastAnswer: "", attempts: 0, correct: null, updatedAt: 1, hintViewed: false, explanationViewed: true, tutorViewed: true, independent: null, scope: "same_question_correction", countsForAbility: false, lastAnswerTurnId: null, correctedAt: null };
    const source = { ...waiting, tutorAvailable: true, answerMode: "spoken", studentCorrection: correction };
    const before = homeworkDetailSchema.parse({ ...snapshot(), submission: { ...snapshot().submission, items: [first, seventh, corrected, source] } });
    const after = homeworkDetailSchema.parse({ ...before, submission: { ...before.submission, items: before.submission.items.map(item => item.id === source.id ? { ...item, studentCorrection: { ...correction, status: "corrected", attempts: 1, correct: true, lastAnswer: "5", updatedAt: 2, correctedAt: 2, lastAnswerTurnId: `hwt_${"d".repeat(32)}` } } : item), summary: { ...before.submission.summary, corrected: 2 } } });
    const lesson = { id: `hwt_${"e".repeat(32)}`, mode: "explain", message: "", status: "ready", teacherText: "看看原图，再试一次。", steps: [{ id: "one", text: "看看原图，再试一次。", visual: { kind: "paper_region" } }], teachingQuality: { status: "guidance", reason: "同题参考讲解", method: "tencent_reference.v1", countsForAbility: false }, audio: { status: "unavailable" }, createdAt: 1 };
    const fetch = vi.fn().mockResolvedValueOnce(json(before)).mockResolvedValueOnce(json({ ok: true, tutor: { itemId: source.id, itemRevision: source.revision, enabled: true, voiceAvailable: false, correction, turns: [lesson] } })).mockResolvedValueOnce(json(after)); vi.stubGlobal("fetch", fetch);
    render(<HomeworkWorkspace id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "第 2 页" }));
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByText("原题 12")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "老师带我订正原题" }));
    await screen.findByText("听完讲解，自己试试");
    expect(screen.queryByRole("button", { name: "第 2 页" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "回到原作业" }));
    expect(await screen.findByText("已订正")).toBeVisible();
    expect(screen.getByRole("button", { name: "第 2 页" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByText("原题 12")).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(3); expect(fetch.mock.calls.every(([, init]) => !init.method && init.cache === "no-store")).toBe(true);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("shows a server-gated same-question reference verbatim without certifying the paper grade or independent practice", () => {
    const source = { ...first, reviewContext: { ...first.reviewContext!, grading: { status: "unknown" as const, referenceAnswer: String.raw`$\boxed{5}$`, analysis: "原题解析：先数左边，再接着数。", knowledgePoints: ["数的合并"], geometryVerified: true, source: "tencent", studentQuality: { status: "needs_review" as const, reason: "正式评分尚未核对", method: "original_image_quality.v1", countsForAbility: false as const }, referenceGate: { available: true, method: "tencent_reference.v1", status: "provider_consistent" as const } } } };
    const { container } = render(<HomeworkGradingDetails item={source} />);
    fireEvent.click(screen.getByText("原题参考与解析"));
    expect(screen.getByText("原题参考答案")).toBeVisible(); expect(screen.getByText("原题解析：先数左边，再接着数。")).toBeVisible();
    expect(container.querySelector(".katex-html")).toHaveTextContent("5"); expect(container.querySelector(".fbox")).toBeVisible(); expect(container.textContent).not.toMatch(/腾讯|Tencent|provider_consistent|AI老师/);
    expect(homeworkPaperJudgment(source)).toBe("unknown"); expect(practiceReady(snapshot().submission, source)).toBe(false);
  });
  it.each([
    { available: false, method: "direction_reversal_requires_review", status: "needs_review" as const },
    { available: true, method: "contradictory_metadata", status: "needs_review" as const },
  ])("keeps an explicitly blocked original reference hidden even if an old quality field was verified: %j", referenceGate => {
    const source = { ...first, reviewContext: { ...first.reviewContext!, grading: { status: "correct" as const, referenceAnswer: "2", analysis: "不能展示的旧解析", knowledgePoints: [], geometryVerified: true, source: "tencent", studentQuality: { status: "verified" as const, reason: "旧核对", method: "old.v1", countsForAbility: false as const }, referenceGate } } };
    const { container } = render(<HomeworkGradingDetails item={source} />);
    expect(container).toBeEmptyDOMElement(); expect(screen.queryByText("2")).not.toBeInTheDocument(); expect(screen.queryByText("不能展示的旧解析")).not.toBeInTheDocument();
  });

  it("renders Tencent's boxed comparison in the source path and original answer while hiding unverified references", () => {
    const formula = String.raw`$\boxed{4} \bigcirc \boxed{1} = \boxed{\quad}$`;
    const source = { ...first, tutorAvailable: true, reviewContext: { ...first.reviewContext!, originalAnswer: String.raw`$\boxed{4}$`, sourcePath: ["5. 我聪明，我会填", formula], grading: { status: "unknown" as const, source: "tencent", geometryVerified: true, referenceAnswer: String.raw`$\boxed{2}$`, analysis: "未核实的解析", knowledgePoints: [], studentQuality: { status: "needs_review" as const, reason: "原题需核对", method: "original_image_quality.v1", countsForAbility: false as const }, providerVerdict: { status: "correct" as const, source: "tencent" as const, provisional: true as const, countsForAbility: false as const } } } };
    const submission = { ...snapshot().submission, items: [source], tutorItems: [] };
    const onTutor = vi.fn(), onStart = vi.fn();
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={onStart} onTutor={onTutor} onRefresh={vi.fn()} />);
    const sourceMath = container.querySelector(".homework-question-path .katex-html");
    expect(sourceMath).toBeVisible(); expect(sourceMath?.querySelectorAll(".fbox")).toHaveLength(3);
    expect(sourceMath?.textContent).toMatch(/[○◯]/); expect(sourceMath?.textContent).not.toMatch(/boxed|bigcirc|\\/);
    expect(container.querySelector(".homework-original-question figcaption .fbox")).toBeVisible();
    expect(screen.getByText("老师还要核实原题")).toBeVisible(); expect(container.querySelector(".homework-grading-details")).toBeNull();
    expect(screen.queryByText("未核实的解析")).not.toBeInTheDocument(); expect(practiceReady(submission, source)).toBe(false);
    expectPhotoPath(screen.getByRole("img", { name: "原题 3" }), pageId);
    expect(onTutor).not.toHaveBeenCalled(); expect(onStart).not.toHaveBeenCalled(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("renders verified formula answers and explanations and still formats a missing-photo prompt safely", () => {
    const source = { ...first, reviewContext: { ...first.reviewContext!, grading: { status: "correct" as const, referenceAnswer: String.raw`$\boxed{5}$`, analysis: String.raw`$3 + 2 = \boxed{5}$`, knowledgePoints: [String.raw`$3 + 2$`], geometryVerified: true, source: "tencent", studentQuality: { status: "verified" as const, reason: "已核对原题", method: "verified_arithmetic.v1", countsForAbility: false as const } } } };
    const submission = { ...snapshot().submission, items: [source], tutorItems: [] };
    const view = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByText("核对后的答案与讲解"));
    const formulas = view.container.querySelectorAll(".homework-grading-details .katex-html");
    expect(formulas).toHaveLength(3); for (const formula of formulas) expect(formula.textContent).not.toMatch(/boxed|\\/);
    expect(view.container.querySelectorAll(".homework-grading-details .fbox")).toHaveLength(2);
    view.unmount();
    const prompt = String.raw`比较 $\boxed{4} \bigcirc \boxed{1}$`;
    const { container } = render(<HomeworkQuestionPicture submission={{ ...submission, pages: [] }} item={{ ...source, prompt, reviewContext: undefined, picture: null }} />);
    expect(container.querySelector(".homework-question-fallback .katex-html")).toBeVisible();
    expect(container.querySelector(".homework-question-fallback .katex-html")?.textContent).not.toMatch(/boxed|bigcirc|\\/);
    expect(screen.getByText("原图位置还没确认")).toBeVisible(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("shows the original essay before teaching without creating a score or grading on read", () => {
    const submission = snapshot().submission;
    const onTutor = vi.fn(), onStart = vi.fn();
    const essayItem = { id: first.id, pageId, revision: 1, prompt: "对照这一页作文给修改建议", status: "unsupported", type: "writing", tutorAvailable: true };
    const essay = homeworkDetailSchema.parse({ ok: true, submission: { ...submission, analysisKind: "essay", items: [], tutorItems: [essayItem], readyForStudent: false,
      essayReview: { status: "ready", scope: "guidance_only", countsForAbility: false, suggestions: [{ id: "s1", type: "word", subType: "spelling", origin: "原句", replace: "修改建议", message: "建议说明", pageId }] },
    } }).submission;
    render(<HomeworkPaperOverview submission={essay} onStart={onStart} onTutor={onTutor} onRefresh={vi.fn()} />);
    expectPhotoPath(screen.getByRole("img", { name: "上传的原作文照片" }), pageId);
    expect(screen.getByRole("heading", { name: "和老师看看我的作文" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "和老师一起订正" })).not.toBeInTheDocument();
    expect(globalThis.Audio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "请老师看我的作文" }));
    expect(onTutor).toHaveBeenCalledWith(first.id);
    expect(onStart).not.toHaveBeenCalled();
    expect(screen.getByText("和老师一起修改作文，不作为考试分数。")).toBeVisible();
  });

  it("rejects an essay review that claims ability assessment", () => {
    expect(() => homeworkDetailSchema.parse({ ...snapshot(), submission: { ...snapshot().submission, analysisKind: "essay", essayReview: { status: "ready", scope: "guidance_only", countsForAbility: true, suggestions: [] } } })).toThrow();
  });

  it.each([undefined, { status: "needs_review" as const, reason: "人物对应尚未核实", method: "original_image_quality.v1", countsForAbility: false as const }])("does not mark four wrong or expose an old Tencent answer of two without verified student quality: %j", async studentQuality => {
    const source = { ...first, tutorAvailable: true, reviewContext: { ...first.reviewContext!, originalAnswer: "4", grading: { status: "incorrect" as const, referenceAnswer: "2", analysis: "原批改的错误解析答案2。", knowledgePoints: ["位置与顺序"], geometryVerified: true, answerRegion: first.reviewContext!.region, source: "tencent", studentQuality } } };
    const submission = { ...snapshot().submission, items: [source], tutorItems: [], originalPaperSummary: { total: 1, correct: 0, incorrect: 0, unknown: 1 } };
    const onStart = vi.fn(), onTutor = vi.fn();
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={onStart} onTutor={onTutor} onRefresh={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelector(".homework-paper-marker")).toHaveAttribute("data-status", "unknown"));
    expect(screen.getByText("老师还要核实原题")).toBeVisible(); expect(screen.getByText("再看看 0")).toBeVisible(); expect(screen.getByText("待核实 1")).toBeVisible();
    expect(container.querySelector("s")).toBeNull(); expect(screen.queryByText("2")).not.toBeInTheDocument(); expect(screen.queryByText("原批改的错误解析答案2。")).not.toBeInTheDocument(); expect(screen.queryByText("看原题答案和解析")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "我自己再做一次" })).not.toBeInTheDocument(); expect(practiceReady(submission, source)).toBe(false);
    expect(screen.getByText("这道题暂时不能确认，可以先看原图或换一道题")).toBeVisible();
    const original = screen.getByRole("button", { name: "看原图，圈一圈" }); expect(original.querySelector(".lucide-pointer")).not.toBeNull(); expect(original.querySelector(".lucide-volume2")).toBeNull();
    expect(screen.queryByText("老师会直接看这张原图，再陪你讲解和解答")).not.toBeInTheDocument();
    fireEvent.click(original); expect(onTutor).toHaveBeenCalledWith(source.id); expect(onStart).not.toHaveBeenCalled(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("shows the verified correction of four while the immutable provider record is separate from student results", () => {
    const source = { ...first, reviewContext: { ...first.reviewContext!, originalAnswer: "4", grading: { status: "correct" as const, referenceAnswer: "4", analysis: "先找到雪雪，再从转身后的队伍前面数。", knowledgePoints: ["位置与顺序"], geometryVerified: true, source: "tencent", studentQuality: { status: "verified" as const, reason: "已核对原图", method: "operator_confirmed", countsForAbility: false as const } } } };
    const submission = { ...snapshot().submission, items: [source], tutorItems: [], originalPaperSummary: { total: 1, correct: 1, incorrect: 0, unknown: 0 } };
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByText("核对后的答案与讲解")); expect(screen.getByText("核对后的答案")).toBeVisible(); expect(screen.getByText("答对 1")).toBeVisible(); expect(screen.getByText("再看看 0")).toBeVisible();
    expect(container.querySelector("s")).toBeNull(); expect(screen.queryByText("这是作业检查的参考结果，请听老师核对后再试试。")).not.toBeInTheDocument();
  });

  it("keeps old provider hints neutral without a current source gate while retaining reviewed results and every original entry", async () => {
    const pendingQuality = { status: "needs_review" as const, reason: "讲解还需核对", method: "original_image_quality.v1", countsForAbility: false as const };
    function provisional(base: HomeworkItem, status: "correct" | "incorrect"): HomeworkItem {
      return { ...base, tutorAvailable: true, reviewContext: { ...base.reviewContext!, grading: { status: "unknown", source: "tencent", geometryVerified: true, answerRegion: base.reviewContext!.region, referenceAnswer: "2", analysis: "不应展示的旧参考解析。", knowledgePoints: [], studentQuality: pendingQuality, providerVerdict: { status, source: "tencent", provisional: true, countsForAbility: false } } } };
    }
    const initialWrong = provisional(item("5", 3, "4", .1), "incorrect");
    const initialCorrect = provisional(item("6", 7, "6", .26), "correct");
    const reviewed = provisional(item("7", 10, "4", .42), "incorrect");
    reviewed.reviewContext!.grading = { ...reviewed.reviewContext!.grading!, status: "correct", referenceAnswer: "4", analysis: "核对后的正确解释。", studentQuality: { ...pendingQuality, status: "verified", method: "operator_reviewed_order_reversal.v1" } };
    const highRisk = provisional(item("8", 12, "4", .58), "incorrect");
    delete highRisk.reviewContext!.grading!.providerVerdict; highRisk.reviewContext!.grading!.providerVerdictBlockedReason = "direction_reversal_requires_review";
    const blank = provisional(item("9", 14, "", .76), "incorrect");
    delete blank.reviewContext!.grading!.providerVerdict; blank.reviewContext!.answerState = "blank";
    const records = [initialWrong, initialCorrect, reviewed, highRisk, blank];
    const submission = { ...snapshot().submission, items: records, tutorItems: [], summary: { total: 5, corrected: 0, incorrect: 0 }, originalPaperSummary: { total: 5, correct: 1, incorrect: 0, unknown: 4, blank: 1 }, provisionalPaperSummary: { total: 5, correct: 1, incorrect: 1, unknown: 3, blank: 1, countsForAbility: false as const } };
    const onTutor = vi.fn(), onStart = vi.fn();
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={onStart} onTutor={onTutor} onRefresh={vi.fn()} />);
    expect(screen.queryByText("作业检查（待老师核对）")).not.toBeInTheDocument(); expect(screen.getByText("答对 1")).toBeVisible(); expect(screen.getByText("再看看 0")).toBeVisible(); expect(screen.getByText("未作答 1")).toBeVisible(); expect(screen.getByText("待核实 3")).toBeVisible();
    expect(screen.getByText("老师还要核实原题")).toBeVisible(); expect(container.querySelector("s")).toBeNull(); expect(homeworkPaperJudgment(initialWrong)).toBe("unknown"); expect(practiceReady(submission, initialWrong)).toBe(false);
    expect(container.textContent).not.toMatch(/腾讯|AI老师|初判|Qwen|DeepSeek/iu);
    for (const element of container.querySelectorAll("[aria-label], [alt]")) expect(`${element.getAttribute("aria-label") ?? ""} ${element.getAttribute("alt") ?? ""}`).not.toMatch(/腾讯|AI老师|初判|Qwen|DeepSeek/iu);
    expect(screen.queryByText("不应展示的旧参考解析。")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "我自己再做一次" })).not.toBeInTheDocument();
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll('.homework-paper-marker')).toHaveLength(5));
    expect(container.querySelectorAll('.homework-paper-marker[data-provisional="true"]')).toHaveLength(0);
    expect(screen.getByRole("button", { name: "听老师讲原题 3，老师还要核实原题" })).toHaveAttribute("data-status", "unknown");
    expect(screen.getByRole("button", { name: "听老师讲原题 7，老师还要核实原题" })).toHaveAttribute("data-status", "unknown");
    expect(screen.getByRole("button", { name: "听老师讲原题 10，核对后答对" })).toHaveAttribute("data-status", "correct");
    expect(screen.getByRole("button", { name: "听老师讲原题 12，老师还要核实原题" })).toHaveAttribute("data-status", "unknown");
    const choices = screen.getByRole("group", { name: "选择原作业题目" }); expect(within(choices).getAllByRole("button")).toHaveLength(5);
    expect(screen.getByRole("button", { name: "先看错题 0" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "全部原题 5" })); expect(within(choices).getAllByRole("button")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "看原图，圈一圈" })); expect(onTutor).toHaveBeenCalledWith(initialWrong.id); expect(onStart).not.toHaveBeenCalled(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("uses the current gated paper totals rather than old provisional counts or displayed marks", () => {
    const quality = { status: "needs_review" as const, reason: "参考还需核对", method: "reference_gate.v1", countsForAbility: false as const };
    const records = Array.from({ length: 62 }, (_, index): HomeworkItem => ({ ...first,
      id: `hwi_${index.toString(16).padStart(56, "0")}`, tutorAvailable: true,
      reviewContext: { ...first.reviewContext!, originalOrdinal: index + 1, sourceQuestionLabel: String(index + 1),
        grading: { status: index < 52 ? "correct" : index < 54 ? "incorrect" : "unknown", source: "tencent", geometryVerified: true, knowledgePoints: [], studentQuality: quality,
          referenceGate: { available: index < 54, status: index < 54 ? "provider_consistent" : "needs_review", method: "current_source_reference.v1" },
          ...(index < 59 ? { providerVerdict: { status: index < 57 ? "correct" as const : "incorrect" as const, source: "tencent" as const, provisional: true as const, countsForAbility: false as const } } : {}) } },
    }));
    const submission = { ...snapshot().submission, items: records, tutorItems: [],
      originalPaperSummary: { total: 62, correct: 52, incorrect: 2, unknown: 8, blank: 0, countsForAbility: false as const },
      provisionalPaperSummary: { total: 62, correct: 57, incorrect: 2, unknown: 3, blank: 0, countsForAbility: false as const } };
    render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onTutor={vi.fn()} onRefresh={vi.fn()} />);
    const results = screen.getByLabelText("原作业批改结果");
    expect(within(results).getByText("答对 52")).toBeVisible(); expect(within(results).getByText("再看看 2")).toBeVisible(); expect(within(results).getByText("待核实 8")).toBeVisible();
    expect(within(results).queryByText("答对 57")).not.toBeInTheDocument(); expect(within(results).queryByText("待核实 3")).not.toBeInTheDocument(); expect(globalThis.Audio).not.toHaveBeenCalled();
    const judgments = records.map(homeworkPaperDisplayJudgment);
    expect(judgments.filter(status => status === "correct")).toHaveLength(52); expect(judgments.filter(status => status === "incorrect")).toHaveLength(2); expect(judgments.filter(status => status === "unknown")).toHaveLength(8);
  });

  it("marks a source-gate blocked old green answer neutral while preserving gated correct/wrong pictures and their teacher entries", async () => {
    const quality = { status: "needs_review" as const, reason: "同题参考不能证明独立掌握", method: "current_source_reference.v1", countsForAbility: false as const };
    const records = [first, seventh, corrected].map((base, index): HomeworkItem => ({ ...base, correctionStatus: "pending", tutorAvailable: true,
      reviewContext: { ...base.reviewContext!, grading: { status: index === 0 ? "unknown" : index === 1 ? "correct" : "incorrect", source: "tencent", knowledgePoints: [], geometryVerified: true,
        answerRegion: base.reviewContext!.region, studentQuality: quality,
        referenceGate: { available: index !== 0, status: index === 0 ? "needs_review" : "provider_consistent", method: "same_method_is_not_authority.v1" },
        providerVerdict: { status: "correct", source: "tencent", provisional: true, countsForAbility: false } } },
    }));
    const onTutor = vi.fn(), { container } = render(<HomeworkPaperOverview submission={{ ...snapshot().submission, items: records, tutorItems: [], originalPaperSummary: { total: 3, correct: 1, incorrect: 1, unknown: 1 } }} onStart={vi.fn()} onTutor={onTutor} onRefresh={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(3));
    const held = screen.getByRole("button", { name: "听老师讲原题 3，老师还要核实原题" });
    expect(held).toHaveAttribute("data-status", "unknown"); expect(held).toHaveAttribute("data-provisional", "false"); expect(held.querySelector(".lucide-check")).toBeNull();
    expect(screen.getByRole("button", { name: "听老师讲原题 7，检查提示：答对" })).toHaveAttribute("data-status", "correct");
    expect(screen.getByRole("button", { name: "听老师讲原题 10，检查提示：再看看" })).toHaveAttribute("data-status", "incorrect");
    expect(screen.getByRole("button", { name: "老师带我订正原题" })).toBeVisible();
    fireEvent.click(held); expect(onTutor).toHaveBeenCalledWith(first.id); expect(practiceReady(snapshot().submission, records[0])).toBe(false); expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "看原图，圈一圈" })).toBeVisible(); expect(screen.queryByRole("button", { name: "老师带我订正原题" })).not.toBeInTheDocument();
    expect(screen.getByText("能确认的原题可以听老师讲解和追问；待核实的题先看原图，听过讲解不算独立订正。")).toBeVisible();
  });

  it("keeps totals neutral when no gated paper summary exists, even if legacy provider totals and marks exist", () => {
    const submission = { ...snapshot().submission, provisionalPaperSummary: { total: 9, correct: 7, incorrect: 2, unknown: 0, blank: 0, countsForAbility: false as const } };
    render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onRefresh={vi.fn()} />);
    const results = screen.getByLabelText("原作业批改结果");
    expect(within(results).getByText("答对 0")).toBeVisible(); expect(within(results).getByText("再看看 0")).toBeVisible(); expect(within(results).getByText("看原图 9")).toBeVisible();
    expect(within(results).queryByText("答对 7")).not.toBeInTheDocument(); expect(within(results).queryByText("再看看 2")).not.toBeInTheDocument(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it.each(["direction_reversal_requires_review", "answer_geometry_unverified", "numeric_verdict_contradiction"])("withholds a contradictory initial field when the server provides the blocked reason %s", async reason => {
    const source = { ...first, tutorAvailable: true, reviewContext: { ...first.reviewContext!, grading: { status: "unknown" as const, source: "tencent", geometryVerified: true, answerRegion: first.reviewContext!.region, knowledgePoints: [], providerIsCorrect: false, studentQuality: { status: "needs_review" as const, reason, method: "original_image_quality.v1", countsForAbility: false as const }, providerVerdict: { status: "incorrect" as const, source: "tencent" as const, provisional: true as const, countsForAbility: false as const }, providerVerdictBlockedReason: reason } } };
    const { container } = render(<HomeworkPaperOverview submission={{ ...snapshot().submission, items: [source], tutorItems: [] }} onStart={vi.fn()} onTutor={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText("老师还要核实原题")).toBeVisible(); expect(screen.queryByText("作业检查（待老师核对）")).not.toBeInTheDocument(); expect(screen.getByText("再看看 0")).toBeVisible(); expect(container.querySelector("s")).toBeNull();
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" })); await waitFor(() => expect(container.querySelector(".homework-paper-marker")).toHaveAttribute("data-status", "unknown"));
  });

  it("accepts an explicit provisional contract but rejects ability evidence or a verdict masquerading as verified", () => {
    const body = snapshot(), grading = { status: "unknown", source: "tencent", knowledgePoints: [], geometryVerified: true, providerVerdict: { status: "incorrect", source: "tencent", provisional: true, countsForAbility: false } };
    const value = { ...body, submission: { ...body.submission, items: [{ ...first, reviewContext: { ...first.reviewContext!, grading } }], provisionalPaperSummary: { total: 1, correct: 0, incorrect: 1, unknown: 0, blank: 0, countsForAbility: false } } };
    expect(homeworkDetailSchema.safeParse(value).success).toBe(true);
    expect(homeworkDetailSchema.safeParse({ ...value, submission: { ...value.submission, provisionalPaperSummary: { ...value.submission.provisionalPaperSummary, countsForAbility: true } } }).success).toBe(false);
    expect(homeworkDetailSchema.safeParse({ ...value, submission: { ...value.submission, items: [{ ...first, reviewContext: { ...first.reviewContext!, grading: { ...grading, providerVerdict: { ...grading.providerVerdict, provisional: false } } } }] } }).success).toBe(false);
  });

  it("opens a read-only original-paper overview and changes original-question pictures without grading, analysis or narration", async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(json(snapshot())));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkWorkspace id={id} />);
    expect(await screen.findByRole("heading", { name: "先看看，哪里需要再试试" })).toBeVisible();
    expectPhotoPath(screen.getByRole("img", { name: "上传的原作业照片" }), pageId);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(3));
    expect(screen.queryByRole("group", { name: "点图片，选择圆片的数量" })).not.toBeInTheDocument();
    const context = screen.getByRole("figure", { name: "正在订正的原题" });
    expect(within(context).getByText("原题 3")).toBeVisible();
    expect(within(context).getByText("4").closest("s")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "看看原题 7" }));
    expect(screen.getByRole("button", { name: "看看原题 7" })).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelectorAll(".homework-paper-stage button")).toHaveLength(3);
    expect(container.querySelector('.homework-paper-marker[data-selected="true"]')).toHaveTextContent("7");
    expect(within(context).getByText("原题 7")).toBeVisible();
    expect(within(context).getByText("6").closest("s")).toBeVisible();
    expect(screen.queryByRole("group", { name: "点图片，选择圆片的数量" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls.every(([url, init]) => url === `/api/learning/homework/${id}` && !init.method)).toBe(true);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("starts only the explicitly chosen original question and keeps its context while the teacher explains", async () => {
    const paper = snapshot();
    const explained = { ...seventh, explanationViewed: true, expectedAnswer: "7", explanation: "四个和三个放在一起，一共七个。" };
    const fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(json({ ...paper, submission: { ...paper.submission, items: [first, explained, corrected, waiting] } }));
      return Promise.resolve(json(paper));
    });
    vi.stubGlobal("fetch", fetch);
    render(<HomeworkWorkspace id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "看看原题 7" }));
    fireEvent.click(screen.getByRole("button", { name: "和老师一起订正" }));
    expect(await screen.findByRole("group", { name: "点图片，选择圆片的数量" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "4 + 3 =" })).toBeVisible();
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByText("原题 7")).toBeVisible();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls.every(([, init]) => !init?.method)).toBe(true);
    expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("老师讲解后的数量演示")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "老师带我订正" }));
    expect(await screen.findByLabelText("老师讲解后的数量演示")).toBeVisible();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toBe(`/api/learning/homework/${id}/items/${seventh.id}/actions`);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ itemRevision: 1, action: "explanation" });
    expect(globalThis.Audio).toHaveBeenCalledWith(`/api/learning/homework/${id}/items/${seventh.id}/audio/explanation`);
  });

  it("retains a saved child's correction when returning to the overview without resubmitting it", async () => {
    const paper = snapshot();
    const saved = { ...paper, feedback: { correct: true, attempt: 1, scope: "same_question_correction", audioKind: "success" }, submission: { ...paper.submission, items: [first, { ...seventh, correctionStatus: "corrected" }, corrected, waiting], summary: { ...paper.submission.summary, corrected: 2 }, studentSummary: { ...paper.submission.studentSummary, corrected: 2 } } };
    const fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => Promise.resolve(json(init?.method === "POST" ? saved : paper)));
    vi.stubGlobal("fetch", fetch);
    render(<HomeworkWorkspace id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "看看原题 7" }));
    fireEvent.click(screen.getByRole("button", { name: "和老师一起订正" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole("button", { name: "7 个圆片" }));
    expect(await screen.findByText("这一次你会啦！")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "回到错题概览" }));
    expect(await screen.findByText("已经订正 2 道")).toBeVisible();
    expect(screen.getByText("另外 1 道题的原题讲解尚未准备好，尚未计作订正。")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "全部原题 3" }));
    fireEvent.click(screen.getByRole("button", { name: "看看原题 7" }));
    expect(screen.getByText("这道题已经订正好了")).toBeVisible();
    expect(screen.queryByRole("button", { name: "和老师一起订正" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    expect(JSON.parse(String(fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body))).toMatchObject({ itemRevision: 1, answer: "n7" });
  });

  it("does not invent a marked image location or offer practice for an unprepared question", () => {
    const onStart = vi.fn();
    const submission = snapshot().submission;
    const { container } = render(<HomeworkPaperOverview submission={{ ...submission, pages: [...submission.pages, page(`hwp_${"d".repeat(32)}`, 2)] }} onStart={onStart} onRefresh={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    expectPhotoPath(screen.getByRole("img", { name: "上传的原作业照片" }), secondPageId);
    expect(container.querySelector(".homework-paper-marker")).toBeNull();
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByRole("img", { name: "原题 12" })).toBeVisible();
    expect(screen.getByText("老师的原题讲解还在准备，可以先看原图")).toBeVisible();
    expect(screen.queryByRole("button", { name: "和老师一起订正" })).not.toBeInTheDocument();
    expect(onStart).not.toHaveBeenCalled();
    expect(globalThis.Audio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "第 3 页" }));
    expect(screen.queryByRole("figure", { name: "正在订正的原题" })).not.toBeInTheDocument();
    expect(screen.getByText("这一页还没有可打开的原题，老师正在整理")).toBeVisible();
    expect(screen.queryByRole("button", { name: "和老师一起订正" })).not.toBeInTheDocument();
  });

  it("shows each real photographed cover, separates ready/waiting/completed work and formats millisecond dates", () => {
    const submission = snapshot().submission;
    const waitingId = `hw_${"d".repeat(32)}`;
    const doneId = `hw_${"e".repeat(32)}`;
    const waitingRecord = { ...submission, id: waitingId, title: "等待识别的作业", pages: [], items: [], status: "provider_unknown", readyForStudent: false };
    const doneRecord = { ...submission, id: doneId, title: "已经完成的作业", pages: [], items: submission.items.map(question => ({ ...question, correctionStatus: "corrected", readyForStudent: true })), summary: { ...submission.summary, corrected: 4 }, studentSummary: { ready: 4, awaitingMedia: 0, unsupportedCorrection: 0, corrected: 4 } };
    render(<HomeworkCollection records={[waitingRecord, doneRecord, submission]} />);
    expectPhotoPath(screen.getByRole("img", { name: "q的原作业照片" }), pageId);
    const readyLink = screen.getByRole("link", { name: "q，老师带我订正" });
    expect(readyLink).toHaveAttribute("href", `/learning/homework/${id}`);
    expect(within(readyLink).getByText("数学 · 9月30日")).toBeVisible();
    expect(within(readyLink).getByText("2 道题，和老师再试试")).toBeVisible();
    expect(screen.getByRole("heading", { name: "和老师再试试1 份" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "还在准备1 份" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "已经看过的作业1 份" })).toBeVisible();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("never fetches an arbitrary photo URL and provides explicit image retry without replaying AI", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const view = render(<HomeworkPaperImage submissionId={id} page={{ ...page(pageId, 0), assetUrl: "https://other.test/private-image.png" }} alt="上传的原作业照片" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("原作业图片暂时没打开")).toBeVisible();
    view.rerender(<HomeworkPaperImage submissionId={id} page={page(pageId, 0)} alt="上传的原作业照片" />);
    fireEvent.error(screen.getByRole("img", { name: "上传的原作业照片" }));
    expect(screen.getByText("原作业图片暂时没打开")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "重新看图" }));
    expectPhotoPath(screen.getByRole("img", { name: "上传的原作业照片" }), pageId);
    expect(fetch).not.toHaveBeenCalled();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("shows locations only after the paper loads and still opens a different page after failure", async () => {
    const onStart = vi.fn();
    const { container } = render(<HomeworkPaperOverview submission={snapshot().submission} onStart={onStart} onRefresh={vi.fn()} />);
    expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(0);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(3));
    fireEvent.error(screen.getByRole("img", { name: "上传的原作业照片" }));
    expect(container.querySelector(".homework-paper-marker")).toBeNull();
    expect(screen.getByRole("button", { name: "看看原题 3" })).toBeVisible();
    expect(screen.getByRole("button", { name: "看看原题 7" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "第 2 页" }));
    expectPhotoPath(screen.getByRole("img", { name: "上传的原作业照片" }), secondPageId);
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByText("原题 12")).toBeVisible();
    expect(onStart).not.toHaveBeenCalled();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("returns to the current paper overview when a refreshed GET changes the revision", async () => {
    const paper = snapshot();
    const updated = { ...paper, submission: { ...paper.submission, revision: 6, items: paper.submission.items.map(question => ({ ...question, revision: 2, correctionStatus: "pending", reviewContext: { ...question.reviewContext!, originalAnswer: "1" } })), summary: { ...paper.submission.summary, corrected: 0 }, studentSummary: { ...paper.submission.studentSummary, corrected: 0 } } };
    const fetch = vi.fn().mockResolvedValueOnce(json(paper)).mockResolvedValueOnce(json(updated));
    vi.stubGlobal("fetch", fetch);
    render(<HomeworkWorkspace id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "和老师一起订正" }));
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("heading", { name: "先看看，哪里需要再试试" })).toBeVisible();
      expect(screen.queryByRole("group", { name: "点图片，选择圆片的数量" })).not.toBeInTheDocument();
    });
    expect(within(screen.getByRole("figure", { name: "正在订正的原题" })).getByText("1").closest("s")).toBeVisible();
    expect(fetch.mock.calls.every(([, init]) => !init?.method)).toBe(true);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("uses a printed subquestion label instead of the recognition array position and leaves unconfirmed handwriting unstruck", () => {
    const context = { ...first.reviewContext!, sourceQuestionLabel: "5（1）", originalOrdinal: 8, originalAnswer: "4 - 1 = 3", recognitionConfirmed: false };
    const { container } = render(<HomeworkOriginalQuestion submission={snapshot().submission} item={{ ...first, reviewContext: context }} />);
    const figure = screen.getByRole("figure", { name: "正在订正的原题" });
    expect(within(figure).getByText("原题 5（1）")).toBeVisible();
    expect(within(figure).getByText("识别到的作答", { exact: false })).toBeVisible();
    expect(within(figure).getByText("4 - 1 = 3")).toBeVisible();
    expect(within(figure).getByRole("img", { name: "原题 5（1）" })).toBeVisible();
    expect(container.querySelector("s")).toBeNull();
    expect(screen.queryByText("原题 8")).not.toBeInTheDocument();
  });

  it("labels legacy ordinal-only records as image positions and does not assert that OCR answers were written by the child", () => {
    const legacyContext = { pageId, region: first.reviewContext!.region, originalAnswer: "4", originalOrdinal: 3 };
    const { container } = render(<HomeworkOriginalQuestion submission={snapshot().submission} item={{ ...first, reviewContext: legacyContext }} />);
    expect(screen.getByText("题目图片 3")).toBeVisible();
    expect(screen.getByText("识别到的作答", { exact: false })).toBeVisible();
    expect(screen.getByText("· 第 1 页", { exact: false })).toBeVisible();
    expect(container.querySelector("s")).toBeNull();
    expect(screen.queryByText(/原来写的是|原作业 · 第 3 题/)).not.toBeInTheDocument();
  });
  it("can show the same source answer neutrally for the teacher without changing the original paper judgment", () => {
    const submission = snapshot().submission;
    const view = render(<HomeworkOriginalQuestion submission={submission} item={first} neutralAnswer />);
    const figure = screen.getByRole("figure", { name: "正在订正的原题" });
    expect(within(figure).getByText("孩子原作答：")).toBeVisible(); expect(within(figure).getByText("4")).toBeVisible(); expect(view.container.querySelector("s")).toBeNull();
    view.rerender(<HomeworkOriginalQuestion submission={submission} item={first} />); expect(view.container.querySelector("s")).toHaveTextContent("4");
  });

  it.each([
    { x: .1, y: .5, width: .8, height: .04 },
    { x: .1, y: .5, width: .15, height: .1 },
  ])("keeps the whole illustrated question page when the OCR box is too thin or small: %j", async region => {
    const answerRegion = { x: .15, y: .52, width: .025, height: .015 };
    const illustrated = { ...first, reviewContext: { ...first.reviewContext!, region, grading: { status: "incorrect" as const, knowledgePoints: [], geometryVerified: true, answerRegion } } };
    const { container } = render(<HomeworkOriginalQuestion submission={snapshot().submission} item={illustrated} neutralAnswer />);
    const image = screen.getByRole("img", { name: "原题 3" });
    expect(image).toHaveStyle({ width: "100%", height: "100%", objectFit: "contain" });
    expect(container.querySelector(".homework-paper-image")).toHaveStyle({ aspectRatio: "1200 / 1600" });
    fireEvent.load(image);
    await waitFor(() => expect(container.querySelector(".homework-answer-focus")).toHaveStyle({ left: "15%", top: "52%", width: "2.5%", height: "1.5%" }));
  });

  it("still crops a complete question block and maps the answer focus inside that crop", async () => {
    const answerRegion = { x: .4, y: .3, width: .05, height: .03 };
    const region = { x: .1, y: .1, width: .7, height: .4 };
    const complete = { ...first, reviewContext: { ...first.reviewContext!, region, grading: { status: "incorrect" as const, knowledgePoints: [], geometryVerified: true, answerRegion } } };
    const { container } = render(<HomeworkOriginalQuestion submission={snapshot().submission} item={complete} neutralAnswer />);
    const image = screen.getByRole("img", { name: "原题 3" });
    expect(image).toHaveStyle({ position: "absolute" });
    expect(Number.parseFloat(image.style.width)).toBeGreaterThan(100);
    fireEvent.load(image);
    await waitFor(() => expect(container.querySelector(".homework-answer-focus")).toBeInTheDocument());
    const focus = container.querySelector<HTMLElement>(".homework-answer-focus")!;
    expect(Number.parseFloat(focus.style.left)).toBeCloseTo((.4 - .088) / .724 * 100);
    expect(Number.parseFloat(focus.style.top)).toBeCloseTo((.3 - .098) / .404 * 100);
  });

  it("keeps the current subquestion with shared illustrated context and source options, without displaying sibling questions or reference text", async () => {
    const submission = { ...snapshot().submission, paperStructure: homeworkPaperStructureFixture(first.id, pageId) };
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkOriginalQuestion submission={submission} item={first} neutralAnswer />);
    const figure = screen.getByRole("figure", { name: "正在订正的原题" }), sourceImage = within(figure).getByRole("img", { name: "原题 3" });
    expect(Number.parseFloat(sourceImage.style.top)).toBeCloseTo(-.078 / .574 * 100);
    const media = screen.getByRole("group", { name: "这道原题的配图和选项" });
    expect(within(media).getAllByRole("img")).toHaveLength(4);
    expect(within(media).getByRole("img", { name: "原题选项图片 A" })).toBeVisible();
    expect(within(media).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText(/另一个小题|第一个印刷选项|共享表格/)).not.toBeInTheDocument();
    fireEvent.load(sourceImage);
    await waitFor(() => expect(container.querySelector(".homework-answer-focus")).toBeInTheDocument());
    expect(Number.parseFloat(container.querySelector<HTMLElement>(".homework-answer-focus")!.style.left)).toBeCloseTo((.6 - .088) / .624 * 100);
    expect(fetch).not.toHaveBeenCalled(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("shows a blank source slot without the OCR-completed answer and does not offer grading or wrong-question marks while source confirmation is pending", async () => {
    const uncertain = { ...first, tutorAvailable: true, reviewContext: { ...first.reviewContext!, sourceQuestionLabel: "5（1）", originalAnswer: "4 - 1 = 3", answerState: "blank" as const, recognitionConfirmed: false, recognitionNeedsConfirmation: true } };
    const onStart = vi.fn();
    const submission = { ...snapshot().submission, items: [uncertain], tutorItems: [] };
    const { container } = render(<HomeworkPaperOverview submission={submission} onStart={onStart} onRefresh={vi.fn()} onTutor={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    expect(await screen.findByText("□（空白）")).toBeVisible();
    expect(screen.queryByText("4 - 1 = 3")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "和老师一起订正" })).not.toBeInTheDocument();
    expect(container.querySelector(".homework-paper-marker")).toBeNull();
    expect(screen.getByText("老师会直接看这张原图，再陪你讲解和解答")).toBeVisible();
    expect(screen.getByRole("button", { name: "请老师看原题" })).toBeVisible();
    expect(onStart).not.toHaveBeenCalled();
  });

  it("keeps clear arithmetic practice available without manual confirmation but blocks unclear source answers", () => {
    const submission = snapshot().submission;
    const clear = { ...first, reviewContext: { ...first.reviewContext!, recognitionConfirmed: false } };
    expect(practiceReady(submission, clear)).toBe(true);
    expect(practiceReady(submission, { ...clear, reviewContext: { ...clear.reviewContext, answerState: "unclear" } })).toBe(false);
  });
});
