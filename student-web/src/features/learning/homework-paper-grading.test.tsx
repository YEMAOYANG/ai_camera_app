import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
import { HomeworkPaperOverview, homeworkTutorQuestions } from "./homework-paper-overview";
import { HomeworkWorkspace } from "./learning-homework";

const id = `hw_${"a".repeat(32)}`, pageId = `hwp_${"b".repeat(32)}`;
function paper() {
  const originalPaperItems = Array.from({ length: 13 }, (_, index) => ({
    id: `hwi_${index.toString(16).padStart(32, "0")}`, pageId, revision: 1, prompt: "把每个空格填好", status: "pending", tutorAvailable: true,
    reviewContext: { pageId, region: { x: .1, y: .1, width: .8, height: .55 }, originalOrdinal: index + 1, originalAnswer: index === 12 ? "" : "4", answerState: index === 12 ? "blank" : "written", sourceQuestionLabel: "1（1）", answerIndex: index + 1, answerCount: 13, sourcePath: ["一、填空", "把每个空格填好"],
      sourceHierarchy: { schemaVersion: "mira.homework-source-hierarchy.v1", receiptIndex: 1, markPath: [1, 1], sourcePath: ["一、填空", "把每个空格填好"], answerIndex: index + 1, answerCount: 13, scope: "answer_blank", questionTextScope: "shared_question", hierarchyVerified: true },
      grading: { status: index < 7 ? "incorrect" : index < 12 ? "correct" : "unknown", answerState: index === 12 ? "blank" : "written", providerIsCorrect: index < 7 ? false : true, source: "tencent", provider: "tencent", referenceAnswer: "5", analysis: "先数左边，再接着数。", knowledgePoints: ["数的合并"], geometryVerified: true, sourceValidationTrusted: false, countsForAbility: false,
        studentQuality: { status: "verified", reason: "原图及确定算术已核对", method: "verified_arithmetic.v1", countsForAbility: false },
        answerRegion: index === 12 ? null : { x: .11 + index % 4 * .19, y: .15 + Math.floor(index / 4) * .11, width: .16, height: .07 } },
    },
  }));
  return homeworkDetailSchema.parse({ ok: true, submission: { id, title: "我的两页练习", gradeCode: "primary_1", subject: "math", revision: 3, status: "needs_confirmation", readyForStudent: false, items: [], tutorItems: [], originalPaperItems, pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1200, height: 1600, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${pageId}/image` }], summary: { total: 0, corrected: 0, incorrect: 0 }, originalSummary: { total: 13, correct: 0, incorrect: 0, blank: 1, pending: 12, unsupported: 0 }, originalPaperSummary: { total: 13, correct: 5, incorrect: 7, unknown: 1, blank: 1, countsForAbility: false }, createdAt: 1, updatedAt: 1 } }).submission;
}

describe("original paper grading and teacher entry", () => {
  beforeEach(() => vi.stubGlobal("Audio", vi.fn()));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("uses reviewed student counts, offers bounded wrong-question pictures, and keeps blank work separate", () => {
    const { container } = render(<HomeworkPaperOverview submission={paper()} onStart={vi.fn()} onTutor={vi.fn()} onRefresh={vi.fn()} />);
    expect(screen.getByText("答对 5")).toBeVisible(); expect(screen.getByText("再看看 7")).toBeVisible(); expect(screen.getByText("未作答 1")).toBeVisible();
    const choices = screen.getByRole("group", { name: "选择原作业题目" });
    expect(within(choices).getAllByRole("button")).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: "下一组" })); expect(within(choices).getAllByRole("button")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "全部原题 13" })); expect(within(choices).getAllByRole("button")).toHaveLength(6);
    expect(container.querySelectorAll('.homework-question-picture[data-status="incorrect"]')).toHaveLength(6);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("gives shared-question answers separate image hit regions, focuses the actual blank, and opens that teacher", async () => {
    const onTutor = vi.fn(), onStart = vi.fn();
    const { container } = render(<HomeworkPaperOverview submission={paper()} onStart={onStart} onTutor={onTutor} onRefresh={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(12));
    const markers = container.querySelectorAll<HTMLButtonElement>(".homework-paper-marker");
    expect(markers).toHaveLength(12); expect(markers[0].style.left).toBe("11%"); expect(markers[1].style.left).toBe("30%"); expect(markers[0].style.width).toBe("16%");
    expect(container.querySelector('.homework-paper-marker[data-status="incorrect"]')).not.toBeNull(); expect(container.querySelector('.homework-paper-marker[data-status="correct"]')).not.toBeNull();
    const selected = within(screen.getByRole("figure", { name: "正在订正的原题" })).getByRole("img"); fireEvent.load(selected);
    await waitFor(() => expect(container.querySelector(".homework-answer-focus")).not.toBeNull());
    fireEvent.click(markers[1]); expect(onTutor).toHaveBeenCalledWith(paper().originalPaperItems![1].id); expect(onStart).not.toHaveBeenCalled();
  });

  it("keeps unknown geometry as the full original photo with a working teacher entry and no fabricated mark", () => {
    const source = paper(), unknown = source.originalPaperItems![12];
    const submission = { ...source, originalPaperItems: [{ ...unknown, reviewContext: { ...unknown.reviewContext!, grading: { ...unknown.reviewContext!.grading!, geometryVerified: false } } }] };
    const onTutor = vi.fn(), { container } = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onTutor={onTutor} onRefresh={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" })); expect(container.querySelector(".homework-paper-marker")).toBeNull();
    const image = within(screen.getByRole("figure", { name: "正在订正的原题" })).getByRole("img"); expect(image.style.objectFit).toBe("contain");
    expect(screen.getByText("这里还没作答，老师陪你试试")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "请老师看原题" })); expect(onTutor).toHaveBeenCalledWith(unknown.id);
    expect(screen.queryByText(/家长.*核对|先确认照片/)).not.toBeInTheDocument();
  });
  it("keeps small legal answer positions and disambiguates overlapping raw boxes before opening a teacher", async () => {
    const source = paper(), a = source.originalPaperItems![0], b = source.originalPaperItems![1];
    const small = { x: .2, y: .2, width: .01, height: .006 };
    const submission = { ...source, originalPaperItems: [a, b].map(item => ({ ...item, reviewContext: { ...item.reviewContext!, grading: { ...item.reviewContext!.grading!, answerRegion: small } } })) };
    const onTutor = vi.fn(), { container } = render(<HomeworkPaperOverview submission={submission} onStart={vi.fn()} onTutor={onTutor} onRefresh={vi.fn()} />);
    fireEvent.load(screen.getByRole("img", { name: "上传的原作业照片" }));
    await waitFor(() => expect(container.querySelectorAll(".homework-paper-marker")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "看看这一区域的 2 个原作答" })); expect(onTutor).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "老师带我订正原题" })).not.toBeInTheDocument();
    const choices = screen.getByRole("group", { name: "这一区域的原作答" });
    expect(within(choices).getAllByRole("button")).toHaveLength(2);
    fireEvent.click(within(choices).getByRole("button", { name: "请老师看原题 1（1） · 第 2 个答案" })); expect(onTutor).toHaveBeenCalledWith(b.id);
  });

  it("keeps paper answers and analysis collapsed until explicitly expanded, without running AI", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkPaperOverview submission={paper()} onStart={vi.fn()} onTutor={vi.fn()} onRefresh={vi.fn()} />);
    const details = container.querySelector("details")!; expect(details).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("核对后的答案与讲解")); expect(details).toHaveAttribute("open");
    expect(within(details).getByText("先数左边，再接着数。")).toBeVisible(); expect(within(details).queryByText("这是作业检查的参考结果，请听老师核对后再试试。")).not.toBeInTheDocument(); expect(within(details).getByText("核对后的答案")).toBeVisible(); expect(fetch).not.toHaveBeenCalled();
  });

  it("accepts an original-image leaf without an answer instead of rejecting the complete paper", () => {
    const source = paper(), leaf = source.originalPaperItems![0];
    const parsed = homeworkDetailSchema.parse({ ok: true, submission: { ...source, originalPaperItems: [{ ...leaf, reviewContext: { ...leaf.reviewContext!, answerIndex: null, answerCount: 0, sourceHierarchy: { ...leaf.reviewContext!.sourceHierarchy!, receiptIndex: null, markPath: [], hierarchyVerified: false, answerIndex: null, answerCount: 0, questionTextScope: "image_only" } } }] } });
    expect(homeworkTutorQuestions(parsed.submission)).toHaveLength(1);
  });

  it("shows a missing/unauthorized paper error without a simultaneous loading message or paid call", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: "没有找到这份作业" }), { status: 404 })); vi.stubGlobal("fetch", fetch);
    render(<HomeworkWorkspace id={id} />); expect(await screen.findByRole("alert")).toHaveTextContent("没有找到这份作业");
    expect(screen.queryByText("正在整理原作业…")).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
  });
});
