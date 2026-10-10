import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
import { HomeworkAiTutor } from "./homework-ai-tutor";
import { homeworkTutorQuestions } from "./homework-paper-context";

const id = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`, pageId = `hwp_${"c".repeat(32)}`, turnId = `hwt_${"d".repeat(32)}`, replyId = `hwt_${"e".repeat(32)}`;
const submission = homeworkDetailSchema.parse({ ok: true, submission: { id, title: "苹果题", gradeCode: "primary_1", subject: "math", revision: 1, status: "ready", items: [], tutorItems: [{ id: itemId, revision: 1, prompt: "数苹果", status: "incorrect", tutorAvailable: true, reviewContext: { pageId, region: { x: .1, y: .1, width: .5, height: .2 }, originalAnswer: "5", originalOrdinal: 1 } }], pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1000, height: 1500, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${pageId}/image` }], summary: { total: 0, corrected: 0, incorrect: 1 }, createdAt: 1, updatedAt: 1, readyForStudent: false } }).submission;
const item = homeworkTutorQuestions(submission)[0], message = "第二棵树有几个苹果？";
const turn = { id: turnId, mode: "explain", message: "", status: "ready", teacherText: "原来的分步讲解。", steps: [{ id: "old", text: "原来的第一步。", visual: { kind: "paper_region" } }], assessment: { status: "guidance_only", method: "ai_guidance", countsForAbility: false }, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${turnId}/audio` }, createdAt: 1 };
const reply = { ...turn, id: replyId, mode: "followup", message, replyReady: true, teacherText: "这道题只数第二棵树，旁边的苹果不算。", steps: [{ id: "look", text: "这道题只数第二棵树，旁边的苹果不算。", visual: { kind: "paper_region" } }, { id: "count", text: "看第二棵树，一个、两个、三个。", visual: { kind: "quantity", count: 3 } }, { id: "result", text: "所以这里填3个。", visual: { kind: "paper_region" } }], audio: { status: "pending" }, createdAt: 2 };
const snapshot = (turns: unknown[]) => ({ ok: true, tutor: { itemId, itemRevision: 1, enabled: true, voiceAvailable: true, turns } });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
function typeQuestion() { fireEvent.click(screen.getByRole("button", { name: "问老师" })); fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); fireEvent.change(screen.getByRole("textbox", { name: "写下你想问的" }), { target: { value: message } }); fireEvent.click(screen.getByRole("button", { name: "发送问题" })); }

describe("a visible complete answer to the child's current question", () => {
  beforeEach(() => vi.stubGlobal("Audio", vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() }; })));
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("starts with the original lesson alone and preserves a typed draft in one mounted composer when the child closes and reopens questions", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn, { ...reply, status: "ready", audio: { status: "unavailable" } }]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); await screen.findByText("原来的第一步。");
    const returnToLesson = vi.fn(); container.querySelector<HTMLElement>(".homework-ai-tutor")!.scrollIntoView = returnToLesson;
    const chat = container.querySelector(".homework-tutor-chat")!; expect(chat).toHaveAttribute("hidden"); expect(container.querySelector(".homework-tutor-layout")).toHaveClass("is-chat-closed"); expect(screen.queryByRole("heading", { name: "老师回答" })).not.toBeInTheDocument(); expect(screen.queryByText("老师回复了")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); expect(chat).not.toHaveAttribute("hidden"); fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); const input = screen.getByRole("textbox", { name: "写下你想问的" }); fireEvent.change(input, { target: { value: "还没写完的问题" } });
    fireEvent.click(screen.getByRole("button", { name: "收起追问" })); expect(chat).toHaveAttribute("hidden"); expect(input).toBeInTheDocument(); expect(input).not.toBeVisible(); expect(returnToLesson).toHaveBeenCalledExactlyOnceWith({ block: "start", behavior: "auto" });
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); expect(screen.getByRole("textbox", { name: "写下你想问的" })).toBe(input); expect(input).toHaveValue("还没写完的问题"); expect(container.querySelectorAll(".homework-question-recorder-chat")).toHaveLength(1); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("does not announce a newly generated original explanation as an unread chat reply after recovering its lost receipt", async () => {
    vi.useFakeTimers(); let key = "", reads = 0;
    const fetch = vi.fn().mockImplementation((_url, init) => {
      if (init?.method === "POST") { key = JSON.parse(init.body).idempotencyKey; return Promise.reject(new Error("原题回执丢失")); }
      if (!key) return Promise.resolve(json(snapshot([])));
      reads += 1; return Promise.resolve(json(snapshot([{ ...turn, requestKey: key, status: reads === 1 ? "queued" : "ready", teacherText: reads === 1 ? "" : turn.teacherText, steps: reads === 1 ? [] : turn.steps, audio: reads === 1 ? { status: "pending" } : turn.audio }])));
    }); vi.stubGlobal("fetch", fetch);
    const { container } = await act(async () => render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />)); await act(async () => { fireEvent.click(screen.getByRole("button", { name: "老师讲讲这道题" })); });
    expect(screen.getByText("老师正在看这道原题，准备图片讲解和声音…")).toBeVisible(); await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(screen.getByText("原来的第一步。")).toBeVisible(); expect(screen.queryByText("老师回复了")).not.toBeInTheDocument(); expect(container.querySelector(".homework-tutor-chat")).toHaveAttribute("hidden"); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("keeps a closed paid request polling, cancels pending autoplay, and announces only its own newly ready reply until viewed", async () => {
    vi.useFakeTimers(); let key = "";
    const fetch = vi.fn().mockImplementation((_url, init) => {
      if (init?.method === "POST") { key = JSON.parse(init.body).idempotencyKey; return Promise.resolve(json(snapshot([turn, { ...reply, requestKey: key, status: "queued", replyReady: false, teacherText: "", steps: [] }]))); }
      return Promise.resolve(json(snapshot(key ? [turn, { ...reply, requestKey: key, status: "ready", audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${replyId}/audio` } }] : [turn])));
    }); vi.stubGlobal("fetch", fetch);
    const { container } = await act(async () => render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />));
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); fireEvent.change(screen.getByRole("textbox", { name: "写下你想问的" }), { target: { value: message } }); await act(async () => { fireEvent.click(screen.getByRole("button", { name: "发送问题" })); }); expect(screen.getByRole("button", { name: "收起追问" })).toBeEnabled(); fireEvent.click(screen.getByRole("button", { name: "收起追问" }));
    expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled(); fireEvent.click(screen.getByRole("button", { name: "提交订正答案" })); expect(screen.getByLabelText("说出自己的问题")).toBeInTheDocument(); expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled(); fireEvent.click(screen.getByRole("button", { name: "收起追问" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); }); expect(screen.getByText("老师回复了")).toBeVisible(); expect(container.querySelector(".homework-tutor-chat")).toHaveAttribute("hidden"); expect(globalThis.Audio).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); expect(screen.getByText("所以这里填3个。")).toBeVisible(); fireEvent.click(screen.getByRole("button", { name: "收起追问" })); expect(screen.queryByText("老师回复了")).not.toBeInTheDocument(); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("shows the question immediately during POST and never substitutes the earlier lecture", async () => {
    let finish!: (value: Response) => void, requestKey = ""; const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn, { ...turn, id: `hwt_${"f".repeat(32)}` }]))).mockImplementation((_url, init) => { requestKey = JSON.parse(init.body).idempotencyKey; return new Promise(resolve => { finish = resolve; }); }); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); await screen.findByRole("button", { name: "问老师" }); typeQuestion();
    expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(`你问：${message}`); expect(screen.getByText("老师正在回答这个问题…")).toBeVisible(); expect(screen.getByText("原来的第一步。")).toBeVisible(); expect(screen.getByRole("log", { name: "和老师的对话" })).not.toContainElement(screen.getByText("原来的第一步。")); expect(screen.queryByRole("navigation", { name: "已经保存的学习记录" })).not.toBeInTheDocument();
    await act(async () => { finish(json(snapshot([turn, { ...reply, requestKey, status: "queued", replyReady: false, teacherText: "", steps: [] }]))); });
    expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(message); expect(screen.getByText("老师正在回答这个问题…")).toBeVisible(); expect(fetch).toHaveBeenCalledTimes(2); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("reveals all answer paragraphs before audio finishes without step navigation or a duplicate paper image", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn, { ...reply, status: "working" }]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); fireEvent.click(await screen.findByRole("button", { name: "问老师" })); const response = await screen.findByRole("region", { name: "老师回答这次问题" });
    expect(within(response).getByRole("heading", { name: "老师回答" })).toBeVisible(); expect(within(response).getAllByText(reply.teacherText)).toHaveLength(1); expect(screen.getByText("看第二棵树，一个、两个、三个。")).toBeVisible(); expect(screen.getByText("所以这里填3个。")).toBeVisible();
    expect(screen.getByRole("img", { name: "3 个圆片" })).toBeVisible(); expect(within(response).queryByRole("button", { name: "下一步" })).not.toBeInTheDocument(); expect(container.querySelectorAll(".homework-tutor-followup .homework-paper-image")).toHaveLength(0);
    expect(screen.getByText("文字回答已经准备好，老师的语音还在准备。")).toBeVisible(); expect(screen.getByRole("button", { name: "听老师回答" })).toBeDisabled(); expect(screen.getByRole("button", { name: "问老师" })).toBeDisabled(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it.each([undefined, false])("does not release unverified working text when replyReady is %s", async replyReady => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(snapshot([{ ...reply, status: "working", replyReady }])))); render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "问老师" })); await screen.findByText("老师正在回答这个问题…"); expect(screen.queryByText(reply.teacherText)).not.toBeInTheDocument(); expect(screen.queryByText("所以这里填3个。")).not.toBeInTheDocument();
  });
  it.each(["unknown", "failed"])("keeps validated text visible after %s audio and only checks the saved receipt", async status => {
    const first = { ...reply, status, audio: { status: "unavailable" } }, withdrawn = { ...first, replyReady: false, teacherText: "", steps: [] }; const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn, first]))).mockResolvedValue(json(snapshot([turn, withdrawn]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); fireEvent.click(await screen.findByRole("button", { name: "问老师" })); await screen.findByText("所以这里填3个。"); expect(screen.getByText("文字回答已保留，老师的语音暂时不可用。")).toBeVisible(); expect(screen.getByRole("button", { name: "问老师" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "查看回答状态" })); await waitFor(() => expect(screen.queryByText("所以这里填3个。")).not.toBeInTheDocument()); expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(message); expect(fetch.mock.calls.every(([, init]) => !init.method)).toBe(true); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
  it("matches the current request key after response loss and clears the old network error", async () => {
    let key = ""; const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn]))).mockImplementation((_url, init) => { if (init?.method === "POST") { key = JSON.parse(init.body).idempotencyKey; return Promise.reject(new Error("网络断了")); } return Promise.resolve(json(snapshot([turn, { ...reply, requestKey: key, status: "ready", audio: { status: "unavailable" } }]))); }); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); await screen.findByRole("button", { name: "问老师" }); typeQuestion(); await screen.findByText("所以这里填3个。");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(message); expect(screen.queryByRole("navigation", { name: "已经保存的学习记录" })).not.toBeInTheDocument(); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
  it("does not mistake an earlier response to the same words for this request", async () => {
    const old = { ...reply, requestKey: "old-key", status: "ready", audio: { status: "unavailable" } }; const fetch = vi.fn().mockResolvedValue(json(snapshot([turn, old]))); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); await screen.findByRole("button", { name: "问老师" }); typeQuestion(); await screen.findByText("这次问题的处理结果还在核实，原问题已保留。");
    expect(screen.getByText("所以这里填3个。")).toBeVisible(); expect(screen.getAllByLabelText("本次向老师提问").at(-1)).toHaveTextContent(message); expect(screen.getByRole("article", { name: "老师正在回应这次消息" })).not.toHaveTextContent("所以这里填3个。"); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(screen.queryByRole("button", { name: "第 1 次追问" })).not.toBeInTheDocument();
  });
  it("keeps the original lesson open beside the paper while every question and full answer remains in the chat", async () => {
    const fetch = vi.fn().mockResolvedValue(json(snapshot([turn, { ...reply, status: "ready", audio: { status: "unavailable" } }]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); fireEvent.click(await screen.findByRole("button", { name: "问老师" })); await screen.findByRole("heading", { name: "老师回答" });
    const originalLesson = screen.getByRole("region", { name: "原题讲解" }), log = screen.getByRole("log", { name: "和老师的对话" });
    expect(within(originalLesson).getByRole("heading", { level: 2, name: "原题讲解" })).toBeVisible(); expect(originalLesson.querySelector(".homework-tutor-explanation-heading")).toContainElement(screen.getByRole("button", { name: "听老师完整讲解" }));
    expect(screen.getByRole("heading", { name: "问问老师" })).toBeVisible(); const preview = screen.getByRole("button", { name: "展开原题" }); expect(preview).toHaveAttribute("aria-expanded", "false"); fireEvent.click(preview); expect(screen.getByRole("button", { name: "收起原题" })).toHaveAttribute("aria-expanded", "true");
    expect(log).toContainElement(screen.getByText("所以这里填3个。")); expect(screen.getByText("原来的第一步。")).toBeVisible(); expect(originalLesson).toContainElement(screen.getByText("原来的第一步。")); expect(log).not.toContainElement(originalLesson);
    expect(within(originalLesson).getByRole("button", { name: "下一步" })).toBeInTheDocument(); expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(message); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
    const actions = screen.getByRole("complementary", { name: "原题与订正操作" }); expect(actions).toContainElement(screen.getByRole("group", { name: "提问或提交订正答案" })); expect(container.querySelector(".homework-chat-composer")).not.toContainElement(screen.getByRole("button", { name: "问老师" }));
    expect(container.querySelectorAll(".homework-question-recorder-chat")).toHaveLength(1); expect(screen.getByRole("button", { name: "切换到打字" })).toBeVisible(); expect(screen.queryByRole("button", { name: "语音" })).not.toBeInTheDocument();
  });
  it("keeps a real queued source gate pending, releases verified text before audio, and autoplays only this new saved reply once", async () => {
    vi.useFakeTimers();
    const quality = { status: "verified", reason: "原题已核对", method: "original_image_quality.v1", countsForAbility: false as const };
    const sourceItem = { ...item, reviewContext: { ...item.reviewContext!, grading: { source: "tencent", status: "incorrect" as const, knowledgePoints: [], geometryVerified: true, studentQuality: { ...quality, status: "needs_review" as const } } } };
    let key = "", reads = 0;
    const queued = { ...reply, status: "queued", reviewState: "not_required", replyReady: false, teacherText: "", steps: [], assessment: null, teachingQuality: { ...quality, status: "needs_review" } };
    const fetch = vi.fn().mockImplementation((_url, init) => {
      if (init?.method === "POST") { key = JSON.parse(init.body).idempotencyKey; return Promise.resolve(json(snapshot([{ ...turn, teachingQuality: quality }, { ...queued, requestKey: key }]))); }
      if (!key) return Promise.resolve(json(snapshot([{ ...turn, teachingQuality: quality }])));
      reads += 1;
      return Promise.resolve(json(snapshot([{ ...turn, teachingQuality: quality }, { ...reply, requestKey: key, teachingQuality: quality, status: reads === 1 ? "working" : "ready", audio: reads === 1 ? { status: "pending" } : { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${replyId}/audio` } }])));
    }); vi.stubGlobal("fetch", fetch);
    await act(async () => { render(<HomeworkAiTutor submission={submission} item={sourceItem} onBack={vi.fn()} />); });
    act(() => { fireEvent.click(screen.getByRole("button", { name: "问老师" })); }); act(() => { fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); }); act(() => { fireEvent.change(screen.getByRole("textbox", { name: "写下你想问的" }), { target: { value: message } }); }); await act(async () => { fireEvent.click(screen.getByRole("button", { name: "发送问题" })); }); expect(screen.getByText("老师正在回答这个问题…")).toBeVisible(); expect(screen.queryByRole("region", { name: "原题暂未核实" })).not.toBeInTheDocument(); expect(globalThis.Audio).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); }); expect(screen.getByText("所以这里填3个。")).toBeVisible(); expect(screen.getByRole("button", { name: "问老师" })).toBeDisabled(); expect(globalThis.Audio).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); }); expect(globalThis.Audio).toHaveBeenCalledTimes(1); expect(screen.getByRole("button", { name: "暂停老师回答" })).toBeEnabled(); expect(screen.getByRole("button", { name: "问老师" })).toBeEnabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); }); expect(globalThis.Audio).toHaveBeenCalledTimes(1); expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "暂停老师回答" })); expect(screen.getByRole("button", { name: "听老师回答" })).toBeEnabled();
  });
  it("does not steal the scroll while the child reads earlier messages and offers the latest reply instead", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn, { ...reply, status: "working" }]))).mockResolvedValue(json(snapshot([turn, { ...reply, status: "working", teacherText: "补充：只数这棵树上的苹果。" }]))); vi.stubGlobal("fetch", fetch);
    const { container } = await act(async () => render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />)); fireEvent.click(screen.getByRole("button", { name: "问老师" }));
    const log = screen.getByRole("log", { name: "和老师的对话" }), end = container.querySelector<HTMLElement>(".homework-chat-end")!, scroll = vi.fn(); end.scrollIntoView = scroll;
    Object.defineProperties(log, { scrollHeight: { value: 2000, configurable: true }, clientHeight: { value: 500, configurable: true }, scrollTop: { value: 0, configurable: true } }); fireEvent.scroll(log);
    await act(async () => { await vi.advanceTimersByTimeAsync(4001); }); await act(async () => { await vi.advanceTimersByTimeAsync(1); }); expect(screen.getByText("补充：只数这棵树上的苹果。")).toBeVisible(); expect(scroll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "看看最新回复" })); expect(scroll).toHaveBeenCalledTimes(1); expect(screen.queryByRole("button", { name: "看看最新回复" })).not.toBeInTheDocument(); expect(fetch.mock.calls.every(([, init]) => !init.method)).toBe(true);
  });
  it("positions the tutor once on entry without repeating page navigation for receipt polling", async () => {
    vi.useFakeTimers(); const pageScroll = vi.fn(), messageScroll = vi.fn();
    const existing = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollIntoView");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: function (this: HTMLElement, options: ScrollIntoViewOptions) { if (this.classList.contains("homework-ai-tutor")) pageScroll(options); else messageScroll(options); } });
    try {
      let finish!: (value: Response) => void;
      const fetch = vi.fn().mockReturnValueOnce(new Promise<Response>(resolve => { finish = resolve; })).mockResolvedValue(json(snapshot([turn, { ...reply, status: "working" }]))); vi.stubGlobal("fetch", fetch);
      await act(async () => { render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); });
      expect(pageScroll).not.toHaveBeenCalled();
      await act(async () => { finish(json(snapshot([turn, { ...reply, status: "working" }]))); });
      expect(pageScroll).toHaveBeenCalledExactlyOnceWith({ block: "start", behavior: "auto" });
      await act(async () => { await vi.advanceTimersByTimeAsync(8000); }); expect(fetch).toHaveBeenCalledTimes(3); expect(pageScroll).toHaveBeenCalledTimes(1); expect(messageScroll).not.toHaveBeenCalled();
    } finally { if (existing) Object.defineProperty(HTMLElement.prototype, "scrollIntoView", existing); else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView"); }
  });
  it("shows the verified original lesson once after three superseded unverified explanation attempts", async () => {
    const quality = { status: "verified", reason: "原题已核对", method: "original_image_quality.v1", countsForAbility: false };
    const old = ["f", "1", "2"].map((char, index) => ({ ...turn, id: `hwt_${char.repeat(32)}`, replyReady: false, reviewState: "required", teachingQuality: { ...quality, status: "needs_review" }, teacherText: `未核实的旧讲解${index}。`, createdAt: index + 1 }));
    const fetch = vi.fn().mockResolvedValue(json(snapshot([...old, { ...turn, replyReady: true, teachingQuality: quality, createdAt: 4 }]))); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />); await screen.findByText("原来的第一步。");
    expect(screen.getAllByRole("region", { name: "原题讲解" })).toHaveLength(1); expect(container.querySelectorAll(".homework-tutor-original-lesson")).toHaveLength(1); expect(container.querySelectorAll(".homework-chat-exchange")).toHaveLength(0); expect(screen.queryByText("这段讲解还需核对，先看原图。")).not.toBeInTheDocument();
    for (const saved of old) { expect(screen.queryByText(saved.teacherText)).not.toBeInTheDocument(); expect(container.querySelector(`[data-turn-id="${saved.id}"]`)).toBeNull(); }
    expect(screen.getByRole("button", { name: "听老师完整讲解" })).toBeEnabled(); expect(fetch).toHaveBeenCalledTimes(1); expect(globalThis.Audio).not.toHaveBeenCalled();
  });
});
