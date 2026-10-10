import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
import { HomeworkReviewExplorer } from "./homework-review-explorer";
import { homeworkTutorQuestions } from "./homework-paper-overview";

const id = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`, pageId = `hwp_${"c".repeat(32)}`;
const submission = homeworkDetailSchema.parse({ ok: true, submission: {
  id, title: "原作业", gradeCode: "primary_1", subject: "math", revision: 1, status: "needs_confirmation", items: [],
  tutorItems: [{ id: itemId, revision: 1, prompt: "模型识别的题干和答案2", status: "unsupported", type: "geometry", tutorAvailable: true, reviewContext: { pageId, region: { x: .1, y: .1, width: .8, height: .3 }, originalAnswer: "4", originalOrdinal: 1, grading: { status: "incorrect", referenceAnswer: "2", analysis: "尚未核实的分析", knowledgePoints: [], geometryVerified: true, source: "tencent" } } }],
  pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1200, height: 1600, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${pageId}/image` }],
  summary: { total: 0, corrected: 0, incorrect: 0 }, createdAt: 1, updatedAt: 1, readyForStudent: false,
} }).submission;
const item = homeworkTutorQuestions(submission)[0];
async function loadPreview() { fireEvent.load(screen.getByRole("img", { name: "可以点图做临时标记的原题照片" })); await screen.findByRole("button", { name: "点原图做临时标记" }); }
function point(button: HTMLElement, x: number, y: number) {
  vi.spyOn(button, "getBoundingClientRect").mockReturnValue({ x: 10, y: 20, left: 10, top: 20, right: 210, bottom: 320, width: 200, height: 300, toJSON: () => ({}) });
  fireEvent.click(button, { detail: 1, clientX: 10 + x * 200, clientY: 20 + y * 300 });
}
function expectPosition(mark: HTMLElement, xPercent: number, yPercent: number) {
  expect(parseFloat(mark.style.left)).toBeCloseTo(xPercent, 5);
  expect(parseFloat(mark.style.top)).toBeCloseTo(yPercent, 5);
}

describe("temporary original-picture exploration", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("shows the owned photo without OCR answers, reference digits or model text and enables pointing only after load", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkReviewExplorer submission={submission} item={item} />);
    expect(new URL(screen.getByRole("img").getAttribute("src")!, "http://localhost:3000").pathname).toBe(`/api/learning/homework/${id}/pages/${pageId}/image`);
    expect(container.textContent).not.toMatch(/模型识别|答案2|尚未核实|原图识别到|腾讯/);
    expect(screen.queryByText("4")).not.toBeInTheDocument(); expect(screen.queryByText("2")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "点原图做临时标记" })).not.toBeInTheDocument();
    for (const name of ["放大原图", "清除标记"]) expect(screen.getByRole("button", { name })).toHaveAttribute("data-size", "compact");
    expect(screen.getByRole("button", { name: "清除标记" })).toBeDisabled();
    await loadPreview(); expect(screen.getByRole("button", { name: "点原图做临时标记" })).toBeEnabled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("places unnumbered circles at tapped positions, removes a tapped circle and clears only local memory", async () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const originalData = JSON.stringify(submission);
    render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    const surface = screen.getByRole("button", { name: "点原图做临时标记" }); point(surface, .25, .5); point(surface, .75, .5);
    const marks = screen.getAllByRole("button", { name: "临时标记，点一下移除" });
    expect(marks).toHaveLength(2); expectPosition(marks[0], 25, 50);
    for (const mark of marks) expect(mark).toHaveTextContent("");
    fireEvent.click(marks[0]); expect(screen.getAllByRole("button", { name: "临时标记，点一下移除" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "清除标记" }));
    expect(screen.queryByRole("button", { name: "临时标记，点一下移除" })).not.toBeInTheDocument();
    expect(JSON.stringify(submission)).toBe(originalData); expect(fetch).not.toHaveBeenCalled();
  });
  it("keeps circle coordinates on the original full page when zooming and retains them after closing", async () => {
    render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    point(screen.getByRole("button", { name: "点原图做临时标记" }), .5, .5);
    const trigger = screen.getByRole("button", { name: "放大原图" }); fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "放大原图和临时圈记" });
    const enlarged = within(dialog).getByRole("img", { name: "放大的原作业照片" }); fireEvent.load(enlarged); await within(dialog).findByRole("button", { name: "点原图做临时标记" });
    expect(enlarged).toHaveAttribute("src", screen.getByRole("img", { name: "可以点图做临时标记的原题照片" }).getAttribute("src"));
    expect(enlarged.closest(".homework-paper-image")).toHaveStyle({ aspectRatio: "1200 / 1600" });
    expectPosition(within(dialog).getByRole("button", { name: "临时标记，点一下移除" }), 50, 25);
    fireEvent.click(within(dialog).getByRole("button", { name: "回到题目" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus();
    expectPosition(screen.getByRole("button", { name: "临时标记，点一下移除" }), 50, 50);
    fireEvent.click(trigger); fireEvent.load(screen.getByRole("img", { name: "放大的原作业照片" })); await within(screen.getByRole("dialog")).findByRole("button", { name: "点原图做临时标记" });
    expect(within(screen.getByRole("dialog")).getAllByRole("button", { name: "临时标记，点一下移除" })).toHaveLength(1);
  });
  it("can mark outside the question crop on the full original page and clear both views from the dialog", async () => {
    render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    fireEvent.click(screen.getByRole("button", { name: "放大原图" }));
    const dialog = screen.getByRole("dialog"); fireEvent.load(within(dialog).getByRole("img")); await within(dialog).findByRole("button", { name: "点原图做临时标记" });
    point(within(dialog).getByRole("button", { name: "点原图做临时标记" }), .5, .9);
    expectPosition(within(dialog).getByRole("button", { name: "临时标记，点一下移除" }), 50, 90);
    expect(screen.getAllByRole("button", { name: "临时标记，点一下移除" })).toHaveLength(1);
    fireEvent.click(within(dialog).getByRole("button", { name: "清除标记" }));
    expect(screen.queryByRole("button", { name: "临时标记，点一下移除" })).not.toBeInTheDocument();
  });
  it("handles keyboard activation and dialog cancellation, restoring focus to the zoom control", async () => {
    render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    fireEvent.click(screen.getByRole("button", { name: "点原图做临时标记" }), { detail: 0 });
    expectPosition(screen.getByRole("button", { name: "临时标记，点一下移除" }), 50, 50);
    const trigger = screen.getByRole("button", { name: "放大原图" }); fireEvent.click(trigger);
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "回到题目" })).toHaveFocus();
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: false, cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus();
  });
  it("does not place circles on a failed or missing photo or fall back to unverified text", async () => {
    const view = render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("button", { name: "点原图做临时标记" })).not.toBeInTheDocument();
    expect(screen.getByText("原作业图片暂时没打开")).toBeVisible();
    view.unmount(); render(<HomeworkReviewExplorer submission={{ ...submission, pages: [] }} item={item} />);
    expect(screen.queryByRole("button", { name: "放大原图" })).not.toBeInTheDocument(); expect(screen.queryByText(/模型识别/)).not.toBeInTheDocument();
  });
  it("starts a new item with no circles and never stores them across reopening", async () => {
    const view = render(<HomeworkReviewExplorer key={item.id} submission={submission} item={item} />); await loadPreview();
    fireEvent.click(screen.getByRole("button", { name: "点原图做临时标记" })); expect(screen.getByRole("button", { name: "临时标记，点一下移除" })).toBeVisible();
    view.rerender(<HomeworkReviewExplorer key="different-item" submission={submission} item={{ ...item, id: `hwi_${"e".repeat(56)}` }} />); await loadPreview();
    expect(screen.queryByRole("button", { name: "临时标记，点一下移除" })).not.toBeInTheDocument();
    view.unmount(); render(<HomeworkReviewExplorer submission={submission} item={item} />); await loadPreview();
    expect(screen.queryByRole("button", { name: "临时标记，点一下移除" })).not.toBeInTheDocument();
  });
});
