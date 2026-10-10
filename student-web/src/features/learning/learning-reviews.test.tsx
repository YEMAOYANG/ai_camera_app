import { Blob as NodeBlob } from "node:buffer";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewActivity, ReviewInvitation } from "./learning-reviews";
import type { ReviewSummary } from "@/lib/contracts/learning-review";
import navigationVoice from "./navigation-audio.json";

const snapshot = {
  ok: true, review: { id: "review_1", title: "周末小复习", status: "in_progress", weekStart: "2026-09-28", revision: 2, appointmentRevision: 0, scheduledAt: null, estimatedMinutes: 3, coverage: { lessonCount: 1, questionCount: 2, contentGap: true, notes: [] }, totalQuestions: 2, currentIndex: 0, correctCount: 0, independentCorrectCount: 0, completedAt: null },
  currentQuestion: { id: "q1", renderer: "tiandiren", prompt: "风筝飞在哪儿？", visual: { setting: "school", skyObject: "kite", ground: "track", cast: ["coral", "teal", "yellow"] }, options: [{ value: "A", label: "天", picture: "sky" }, { value: "B", label: "地", picture: "earth" }, { value: "C", label: "人", picture: "people" }], promptAudioUrl: "/api/v2/student/learning/reviews/review_1/media/prompt.wav" }, feedback: null,
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const review = (id: string, status: string, fields: Partial<ReviewSummary> = {}): ReviewSummary => ({ ...snapshot.review, id, status, title: `${id}小测验`, ...fields });

describe("review list entry points", () => {
  beforeEach(() => { vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn(), removeAttribute: vi.fn() }; })); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("shows every ready, paused and completed review, prioritising unfinished work", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, reviews: [review("done", "completed", { currentIndex: 2 }), review("ready", "pending"), review("paused", "paused", { currentIndex: 1 }), review("playing", "in_progress")] }));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<ReviewInvitation />);
    await screen.findByRole("heading", { name: /接着完成/ });
    const links = screen.getAllByRole("link");
    expect(links.map(link => link.getAttribute("href"))).toEqual(["/learning/reviews/paused", "/learning/reviews/playing", "/learning/reviews/ready", "/learning/reviews/done"]);
    expect(screen.getByRole("link", { name: /开始复习：ready小测验/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /查看完成记录：done小测验/ })).toBeVisible();
    expect(screen.getByText("已进行 1 / 2 个小任务")).toBeVisible();
    expect(container.querySelectorAll(".learning-subject-picture")).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: "听老师说" })).toHaveLength(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "听老师说" }));
    expect(globalThis.Audio).toHaveBeenCalledWith(navigationVoice.cues.continue.src);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])("keeps completed-only history visible (compact=%s)", async compact => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, reviews: [review("done", "completed", { currentIndex: 2 })] })));
    render(<ReviewInvitation compact={compact} />);
    expect(await screen.findByRole("link", { name: /查看完成记录：done小测验/ })).toHaveAttribute("href", "/learning/reviews/done");
    expect(screen.queryByText("还没有复习或小测验")).not.toBeInTheDocument();
    expect(globalThis.Audio).not.toHaveBeenCalled();
    if (compact) expect(screen.getByRole("link", { name: "查看全部复习" })).toHaveAttribute("href", "/learning/reviews");
  });

  it.each([false, true])("uses an honest empty state with no invented examination (compact=%s)", async compact => {
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, reviews: [] }));
    vi.stubGlobal("fetch", fetch);
    render(<ReviewInvitation compact={compact} />);
    expect(await screen.findByRole("heading", { name: "还没有复习或小测验" })).toBeVisible();
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "回到书包" })).toHaveAttribute("href", "/learning");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });

  it("does not present content gaps or skipped arrangements as playable tests", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ok: true, reviews: [review("preparing", "content_gap", { totalQuestions: 0 }), review("skipped", "skipped")] })));
    render(<ReviewInvitation />);
    expect(await screen.findByRole("heading", { name: /其他安排/ })).toBeVisible();
    expect(screen.queryByRole("heading", { name: /可以开始/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /开始复习/ })).not.toBeInTheDocument();
    expect(screen.getByText("老师还在准备图片和声音")).toBeVisible();
    expect(screen.getByRole("link", { name: /查看安排：skipped小测验/ })).toHaveAttribute("href", "/learning/reviews/skipped");
  });

  it("keeps compact errors visible and retries the existing authenticated list API", async () => {
    const fetch = vi.fn().mockRejectedValueOnce(new Error("连接中断"))
      .mockResolvedValueOnce(json({ ok: true, reviews: [review("ready", "pending")] }));
    vi.stubGlobal("fetch", fetch);
    render(<ReviewInvitation compact />);
    expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByRole("link", { name: /开始复习：ready小测验/ })).toHaveAttribute("href", "/learning/reviews/ready");
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls.every(([url, init]) => url === "/api/learning/reviews" && init.cache === "no-store" && !init.method)).toBe(true);
  });
});

describe("picture-led review state", () => {
  beforeEach(() => { vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() }; })); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  it("resumes quietly with distinct pictures and does not expose a choice before answering", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(snapshot)));
    const { container } = render(<ReviewActivity id="review_1" />);
    await screen.findByText("风筝飞在哪儿？");
    expect(container.querySelectorAll('.learning-review-choices button svg')).toHaveLength(3);
    expect(screen.getByRole("button", { name: "天" })).toHaveAttribute("aria-pressed", "false");
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("preserves the idempotency key after a lost answer response", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot)).mockRejectedValueOnce(new Error("连接中断"))
      .mockResolvedValueOnce(json({ ...snapshot, review: { ...snapshot.review, revision: 3 }, feedback: { correct: false, independent: true, explanation: "听老师说，再看看图。" } }));
    vi.stubGlobal("fetch", fetch);
    render(<ReviewActivity id="review_1" />);
    fireEvent.click(await screen.findByRole("button", { name: "地" }));
    await screen.findByText("连接中断");
    fireEvent.click(screen.getByRole("button", { name: "地" }));
    await screen.findByText("听老师说，再看看图。");
    const first = JSON.parse(fetch.mock.calls[1][1].body);
    const retry = JSON.parse(fetch.mock.calls[2][1].body);
    expect(retry).toEqual(first);
    expect(retry).not.toHaveProperty("correct");
    expect(screen.getByRole("button", { name: "继续" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "天" })).toBeDisabled();
  });
  it("restores the server-recorded hint and selected response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ ...snapshot, currentQuestion: { ...snapshot.currentQuestion, selectedResponse: "B", helpUsed: true }, feedback: { correct: false, independent: false, explanation: "再看看天空。" } })));
    render(<ReviewActivity id="review_1" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "地" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "继续" })).toBeEnabled();
    expect(globalThis.Audio).not.toHaveBeenCalled();
  });
});

describe("spoken review of a saved original homework question", () => {
  const submissionId = `hw_${"a".repeat(32)}`, pageId = `hwp_${"b".repeat(32)}`, itemId = `hwi_${"c".repeat(56)}`;
  const original = { ...snapshot, currentQuestion: { id: "original_one", renderer: "homework_original", prompt: "看原图，自己说出圈出的空的答案", visual: { kind: "homework_original", submissionId, pageId, width: 1200, height: 1600, region: { x: .1, y: .2, width: .7, height: .2 }, answerRegion: { x: .4, y: .25, width: .05, height: .04 } }, homeworkSource: { submissionId, itemId, itemRevision: 7 }, options: [], promptAudioUrl: "/api/v2/student/learning/reviews/review_1/media/original-prompt.wav" } };
  beforeEach(() => { vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() }; })); });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the owned original photo, records a child's answer and submits only the confirmed transcript to review scoring", async () => {
    vi.stubGlobal("Blob", NodeBlob); vi.stubGlobal("FormData", class { values = new Map<string, unknown>(); set(name: string, value: unknown) { this.values.set(name, value); } get(name: string) { return this.values.get(name); } });
    vi.stubGlobal("isSecureContext", true); const stop = vi.fn(), microphone = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: microphone } });
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:review-answer"); vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.stubGlobal("AudioContext", class { decodeAudioData() { return Promise.resolve({ numberOfChannels: 1, sampleRate: 16000, getChannelData: () => new Float32Array(16000) }); } close() { return Promise.resolve(); } });
    vi.stubGlobal("MediaRecorder", class { static isTypeSupported() { return true; } state = "inactive"; mimeType = "audio/webm"; ondataavailable?: (event: { data: Blob }) => void; onstop?: () => void; start() { this.state = "recording"; } stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["recorded"], { type: this.mimeType }) }); this.onstop?.(); } });
    const answered = { ...original, review: { ...original.review, revision: 3 }, feedback: { correct: true, independent: false, answered: true, message: "这次同一道原题答对了。" } };
    const fetch = vi.fn().mockResolvedValueOnce(json(original)).mockResolvedValueOnce(json({ ok: true, transcription: { id: "hwtr_answer", status: "ready", transcript: "5", errorCode: null } })).mockResolvedValueOnce(json(answered)); vi.stubGlobal("fetch", fetch);
    const onQuestionKind = vi.fn(); const { container } = render(<ReviewActivity id="review_1" onQuestionKind={onQuestionKind} />);
    const image = await screen.findByRole("img", { name: "这次复习的原作业题目" });
    expect(new URL(image.getAttribute("src")!, window.location.origin).pathname).toBe(`/api/learning/homework/${submissionId}/pages/${pageId}/image`);
    expect(image).toHaveStyle({ position: "absolute" }); fireEvent.load(image); await waitFor(() => expect(container.querySelector(".homework-answer-focus")).toBeVisible());
    expect(screen.getByRole("heading", { name: "看原图，再试一试" })).toBeVisible(); expect(screen.queryByRole("group", { name: "点图片作答" })).not.toBeInTheDocument();
    expect(onQuestionKind).toHaveBeenLastCalledWith(true); expect(microphone).not.toHaveBeenCalled(); expect(globalThis.Audio).not.toHaveBeenCalled(); expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "再听一遍题目" })); expect(globalThis.Audio).toHaveBeenCalledWith("/api/learning/reviews/review_1/media/original-prompt.wav");
    fireEvent.click(screen.getByRole("button", { name: "说出我的答案" })); fireEvent.click(await screen.findByRole("button", { name: "我说完了" }));
    fireEvent.click(await screen.findByRole("button", { name: "让老师听听" })); await screen.findByDisplayValue("5");
    expect(fetch).toHaveBeenCalledTimes(2); expect(stop).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[1][0]).toBe(`/api/learning/homework/${submissionId}/items/${itemId}/tutor/transcribe`); expect(fetch.mock.calls[1][1].body.get("itemRevision")).toBe("7");
    fireEvent.click(screen.getByRole("button", { name: "提交我的答案" })); expect(await screen.findByText("这次同一道原题答对了。")).toBeVisible();
    expect(fetch.mock.calls[2][0]).toBe("/api/learning/reviews/review_1/answers"); const body = JSON.parse(fetch.mock.calls[2][1].body);
    expect(body).toEqual({ questionId: "original_one", response: "5", revision: 2, requestId: expect.any(String) });
    expect(screen.getByRole("button", { name: "继续" })).toBeEnabled(); expect(screen.getByRole("button", { name: "重新说" })).toBeDisabled(); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2);
  });

  it("keeps hint, pause and continuation explicit and does not play voice while restoring the saved original", async () => {
    const withHint = { ...original, review: { ...original.review, revision: 3 }, currentQuestion: { ...original.currentQuestion, hint: "看圈出的空，再数一数。", hintAudioUrl: "/api/v2/student/learning/reviews/review_1/media/original-hint.wav", helpUsed: true } };
    const paused = { ...withHint, review: { ...withHint.review, status: "paused", revision: 4 } };
    const fetch = vi.fn().mockResolvedValueOnce(json(original)).mockResolvedValueOnce(json(withHint)).mockResolvedValueOnce(json(paused)); vi.stubGlobal("fetch", fetch);
    render(<ReviewActivity id="review_1" />); fireEvent.click(await screen.findByRole("button", { name: "给一点提示" }));
    expect(await screen.findByText("看圈出的空，再数一数。")).toBeVisible(); expect(globalThis.Audio).toHaveBeenCalledWith("/api/learning/reviews/review_1/media/original-hint.wav");
    fireEvent.click(screen.getByRole("button", { name: "休息一下" })); expect(await screen.findByRole("button", { name: "开始" })).toBeEnabled();
    expect(fetch.mock.calls.slice(1).map(([, init]) => JSON.parse(init.body).action)).toEqual(["hint", "pause"]); expect(globalThis.Audio).toHaveBeenCalledTimes(1);
  });
});
