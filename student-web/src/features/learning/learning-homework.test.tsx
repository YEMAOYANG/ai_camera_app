import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HomeworkActivity, HomeworkInvitation } from "./learning-homework";
import { homeworkAudioPath, homeworkDetailSchema } from "@/lib/contracts/homework";

const id = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`;
const picture = { kind: "quantity_arithmetic", operation: "add", left: 3, right: 2, choices: [{ id: "n4", count: 4 }, { id: "n5", count: 5 }, { id: "n6", count: 6 }] };
const item = { id: itemId, revision: 1, prompt: "一共有几个圆片？", status: "incorrect", readyForStudent: true, correctionStatus: "pending", hintViewed: false, explanationViewed: false, picture, voice: { prompt: { assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/audio/prompt`, status: "ready" } } };
const snapshot = { ok: true, submission: { id, title: "数学小练习", gradeCode: "primary_1", subject: "math", revision: 2, status: "ready", items: [item], summary: { total: 1, corrected: 0, incorrect: 1 }, createdAt: 1, updatedAt: 1, readyForStudent: true } };
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });

describe("homework correction flow", () => {
  beforeEach(() => vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn(), removeAttribute: vi.fn() }; })));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each([false, true])("formats an already available picture exercise prompt and its granted %s explanation", async explanationViewed => {
    const source = { ...item, prompt: String.raw`数一数 $3 + 2 = \boxed{\quad}$`, hintViewed: !explanationViewed, explanationViewed, hint: String.raw`先数 $\boxed{3}$ 个圆片。`, explanation: String.raw`$3 + 2 = \boxed{5}$` };
    const fetch = vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, items: [source] } })); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkActivity id={id} />);
    await screen.findByRole("group", { name: "点图片，选择圆片的数量" });
    expect(container.querySelector(".learning-review-task-heading .fbox")).toBeVisible();
    expect(container.querySelector(".learning-review-feedback .fbox")).toBeVisible();
    for (const formula of container.querySelectorAll(".katex-html")) expect(formula.textContent).not.toMatch(/boxed|\\/);
    expect(container.querySelectorAll(".learning-review-choices svg")).toHaveLength(3);
    expect(fetch).toHaveBeenCalledTimes(1); expect(fetch.mock.calls[0][1].method).toBeUndefined(); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("accepts real item identities, renders countable choices, and restores quietly", async () => {
    expect(homeworkDetailSchema.safeParse(snapshot).success).toBe(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(snapshot)));
    const { container } = render(<HomeworkActivity id={id} />);
    await screen.findByText("一共有几个圆片？");
    expect(container.querySelectorAll('.learning-review-choices svg')).toHaveLength(3);
    expect(globalThis.Audio).not.toHaveBeenCalled();
    expect(homeworkAudioPath(item.voice.prompt.assetUrl, id, itemId)).toContain("/api/learning/homework/");
    expect(homeworkAudioPath(item.voice.prompt.assetUrl, `hw_${"c".repeat(32)}`, itemId)).toBeNull();
  });
  it("retries the same answer with the same key without accepting browser scoring", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot)).mockRejectedValueOnce(new Error("网络中断"))
      .mockResolvedValueOnce(json({ ...snapshot, feedback: { correct: true, attempt: 1, scope: "repeated_practice", audioKind: "success" }, submission: { ...snapshot.submission, items: [{ ...item, correctionStatus: "corrected" }], summary: { total: 1, corrected: 1, incorrect: 1 } } }));
    vi.stubGlobal("fetch", fetch); render(<HomeworkActivity id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "5 个圆片" }));
    await screen.findByText("网络中断");
    fireEvent.click(screen.getByRole("button", { name: "5 个圆片" }));
    await screen.findByText("这一次你会啦！");
    const payload = JSON.parse(fetch.mock.calls[1][1].body);
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual(payload);
    expect(payload).not.toHaveProperty("correct");
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.getByText("这次订正完成啦")).toBeInTheDocument();
  });
  it("does not replace missing low-grade pictures with text-only answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, items: [{ ...item, picture: null }] } })));
    render(<HomeworkActivity id={id} />);
    await screen.findByText("这份作业暂时没有可订正的练习");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it.each(["provider_unknown", "failed", "error"])("shows %s submissions without presenting them as playable or processing", async status => {
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, submissions: [{ ...snapshot.submission, status, processing: false, readyForStudent: false, items: [] }] }));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkInvitation />);
    expect(await screen.findByRole("link", { name: "数学小练习，这份原作业还需要老师看一看" })).toHaveAttribute("href", `/learning/homework/${id}`);
    expect(screen.queryByText("老师正在准备图片和声音")).not.toBeInTheDocument();
    expect(container.querySelector(".lucide-play")).toBeNull();
    expect(container.querySelector(".learning-subject-picture")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "听老师说" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it.each(["provider_unknown", "failed", "error"])("does not poll or reopen unprepared items for a %s activity", async status => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(json({ ...snapshot, submission: { ...snapshot.submission, status, processing: true, readyForStudent: false, items: [{ ...item, readyForStudent: false }] } })));
    vi.stubGlobal("fetch", fetch);
    const timer = vi.spyOn(window, "setInterval");
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("heading", { name: "这份原作业还需要老师看一看" })).toBeVisible();
    expect(screen.getByText("原作业已保存。可以回到原作业，选择原题请老师讲解。")).toBeVisible();
    expect(screen.queryByRole("group", { name: "点图片，选择圆片的数量" })).not.toBeInTheDocument();
    expect(screen.queryByText("老师正在准备图片和声音")).not.toBeInTheDocument();
    expect(timer).not.toHaveBeenCalledWith(expect.any(Function), 5000);
    fireEvent.click(screen.getByRole("button", { name: "再看看" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls.every(([url, init]) => url === `/api/learning/homework/${id}` && !init.method)).toBe(true);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it.each(["queued", "working", "processing"])("can describe an actual %s job as preparing, without a play button", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, submissions: [{ ...snapshot.submission, status, readyForStudent: false, items: [] }] })));
    const { container } = render(<HomeworkInvitation />);
    expect(await screen.findByText("老师正在准备图片和声音")).toBeVisible();
    expect(container.querySelector(".lucide-play")).toBeNull();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("respects processing=false when audio preparation has stopped", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, status: "media_preparing", processing: false, error: "homework_audio_unknown", readyForStudent: false, items: [{ ...item, readyForStudent: false }] } })));
    const timer = vi.spyOn(window, "setInterval");
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("heading", { name: "这份原作业还需要老师看一看" })).toBeVisible();
    expect(screen.queryByText("老师正在准备图片和声音")).not.toBeInTheDocument();
    expect(timer).not.toHaveBeenCalledWith(expect.any(Function), 5000);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("polls only while the server confirms real processing, without dispatching analysis", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, status: "media_preparing", processing: true, readyForStudent: false, items: [] } }));
    vi.stubGlobal("fetch", fetch);
    const timer = vi.spyOn(window, "setInterval");
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("heading", { name: "老师正在准备图片和声音" })).toBeVisible();
    await waitFor(() => expect(timer).toHaveBeenCalledWith(expect.any(Function), 5000));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("keeps real ready picture exercises playable and quiet on entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, submissions: [snapshot.submission] })));
    const { container } = render(<HomeworkInvitation />);
    expect(await screen.findByRole("link", { name: "数学小练习，老师带我订正" })).toHaveAttribute("href", `/learning/homework/${id}`);
    expect(container.querySelector(".lucide-play")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "听老师说" })).not.toBeInTheDocument();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("preserves verified ready exercises while the remaining items are processing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, status: "media_preparing", processing: true } })));
    const timer = vi.spyOn(window, "setInterval");
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("group", { name: "点图片，选择圆片的数量" })).toBeVisible();
    await waitFor(() => expect(timer).toHaveBeenCalledWith(expect.any(Function), 5000));
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("offers teacher explanation directly, reveals the demonstration only after the server grants it, and saves the child's answer", async () => {
    const explained = { ...item, explanationViewed: true, explanation: "3 加 2 等于 5。", expectedAnswer: "5", voice: { ...item.voice, explanation: { assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/audio/explanation`, status: "ready" } } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot))
      .mockResolvedValueOnce(json({ ...snapshot, submission: { ...snapshot.submission, items: [explained] } }))
      .mockResolvedValueOnce(json({ ...snapshot, feedback: { correct: true, attempt: 1, scope: "same_question_correction", audioKind: "success" }, submission: { ...snapshot.submission, items: [{ ...explained, correctionStatus: "corrected" }], summary: { total: 1, corrected: 1, incorrect: 1 } } }));
    vi.stubGlobal("fetch", fetch);
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("button", { name: "老师带我订正" })).toBeVisible();
    expect(screen.getByRole("img", { name: "老师" })).toBeVisible();
    expect(screen.queryByLabelText("老师讲解后的数量演示")).not.toBeInTheDocument();
    expect(globalThis.Audio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "老师带我订正" }));
    expect(await screen.findByLabelText("老师讲解后的数量演示")).toBeVisible();
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ itemRevision: 1, action: "explanation" });
    expect(fetch.mock.calls[1][0]).toBe(`/api/learning/homework/${id}/items/${itemId}/actions`);
    expect(globalThis.Audio).toHaveBeenCalledWith(`/api/learning/homework/${id}/items/${itemId}/audio/explanation`);
    fireEvent.click(screen.getByRole("button", { name: "5 个圆片" }));
    expect(await screen.findByText("这一次你会啦！")).toBeVisible();
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toMatchObject({ itemRevision: 1, answer: "n5" });
    expect(JSON.parse(fetch.mock.calls[2][1].body)).not.toHaveProperty("correct");
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.getByText("你和老师一起完成的记录已保存，家长也能看到。")).toBeVisible();
  });

  it("chooses a prepared wrong question before one whose teacher voice is still preparing", async () => {
    const waiting = { ...item, id: `hwi_${"c".repeat(56)}`, prompt: "等待语音的题目", readyForStudent: false };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, status: "media_preparing", processing: true, items: [waiting, item] } })));
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByText("一共有几个圆片？")).toBeVisible();
    expect(screen.queryByText("等待语音的题目")).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "点图片，选择圆片的数量" })).toBeVisible();
  });

  it("keeps already verified picture/voice questions usable after another question fails, without polling or restarting AI", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, status: "failed", processing: true, error: "homework_audio_unknown", studentSummary: { ready: 1, awaitingMedia: 1, unsupportedCorrection: 0, corrected: 0 } } }));
    vi.stubGlobal("fetch", fetch);
    const timer = vi.spyOn(window, "setInterval");
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("group", { name: "点图片，选择圆片的数量" })).toBeVisible();
    expect(screen.getByRole("button", { name: "老师带我订正" })).toBeVisible();
    expect(timer).not.toHaveBeenCalledWith(expect.any(Function), 5000);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("retains feedback and a saved completion for eight supported wrong questions while excluding nine unsupported questions", async () => {
    const corrected = Array.from({ length: 7 }, (_, index) => ({ ...item, id: `hwi_${index.toString(16).repeat(56)}`, correctionStatus: "corrected" }));
    const paper = { ...snapshot.submission, source: "parent_app", items: [...corrected, item], originalSummary: { total: 29, correct: 12, incorrect: 8, blank: 0, pending: 0, unsupported: 9 }, studentSummary: { ready: 8, awaitingMedia: 0, unsupportedCorrection: 0, corrected: 7 }, summary: { total: 8, incorrect: 8, corrected: 7 } };
    const saved = { ...paper, items: [...corrected, { ...item, correctionStatus: "corrected" }], studentSummary: { ...paper.studentSummary, corrected: 8 }, summary: { ...paper.summary, corrected: 8 } };
    const fetch = vi.fn().mockResolvedValueOnce(json({ ok: true, submission: paper })).mockResolvedValueOnce(json({ ok: true, submission: saved, feedback: { correct: true, attempt: 1, scope: "same_question_correction", audioKind: "success" } }));
    vi.stubGlobal("fetch", fetch);
    const activity = render(<HomeworkActivity id={id} />);
    fireEvent.click(await screen.findByRole("button", { name: "5 个圆片" }));
    expect(await screen.findByText("这一次你会啦！")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "可订正的 8 道题完成啦" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.getByRole("heading", { name: "可订正的 8 道题完成啦" })).toBeVisible();
    expect(screen.getByText("另外 9 道题的原题讲解尚未准备好，尚未计作订正或全对。")).toBeVisible();
    expect(screen.queryByText("这份作业没有需要订正的题目")).not.toBeInTheDocument();
    activity.unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, submissions: [saved] })));
    render(<HomeworkInvitation />);
    expect(await screen.findByRole("link", { name: "数学小练习，可订正的题目已完成" })).toBeVisible();
  });

  it("shows an all-correct real paper and preserves its saved record", async () => {
    const paper = { ...snapshot.submission, source: "parent_app", items: [], readyForStudent: false, originalSummary: { total: 4, correct: 4, incorrect: 0, blank: 0, pending: 0, unsupported: 0 }, studentSummary: { ready: 0, awaitingMedia: 0, unsupportedCorrection: 0, corrected: 0 } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, submissions: [paper] })));
    const list = render(<HomeworkInvitation />);
    expect(await screen.findByRole("link", { name: "数学小练习，这份作业没有需要订正的题目" })).toBeVisible();
    list.unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, submission: paper })));
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("heading", { name: "这份作业没有需要订正的题目" })).toBeVisible();
    expect(screen.queryByText("这次订正完成啦")).not.toBeInTheDocument();
  });

  it.each([
    { originalSummary: { total: 2, correct: 1, incorrect: 0, blank: 0, pending: 0, unsupported: 1 }, label: "老师的原题讲解还没准备好" },
    { originalSummary: { total: 2, correct: 1, incorrect: 0, blank: 0, pending: 1, unsupported: 0 }, label: "这份原作业还需要老师看一看" },
    { originalSummary: { total: 2, correct: 1, incorrect: 1, blank: 0, pending: 0, unsupported: 0 }, studentSummary: { ready: 0, awaitingMedia: 1, unsupportedCorrection: 0, corrected: 0 }, label: "老师的语音还没准备好" },
    { originalSummary: { total: 2, correct: 1, incorrect: 1, blank: 0, pending: 0, unsupported: 0 }, studentSummary: { ready: 0, awaitingMedia: 0, unsupportedCorrection: 1, corrected: 0 }, label: "老师的原题讲解还没准备好" },
  ])("does not mark a partial or unsupported paper as fully corrected ($label)", async ({ label, ...fields }) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, submission: { ...snapshot.submission, ...fields, readyForStudent: false, items: [] } })));
    render(<HomeworkActivity id={id} />);
    expect(await screen.findByRole("heading", { name: label })).toBeVisible();
    expect(screen.queryByText("这次订正完成啦")).not.toBeInTheDocument();
    expect(screen.queryByText("这份作业没有需要订正的题目")).not.toBeInTheDocument();
  });
});
