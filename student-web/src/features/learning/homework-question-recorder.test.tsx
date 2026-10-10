import { Blob as NodeBlob } from "node:buffer";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { encodeHomeworkQuestionWav, HomeworkQuestionRecorder } from "./homework-question-recorder";
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
function installRecording() {
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.stubGlobal("Blob", NodeBlob); vi.stubGlobal("FormData", class { values = new Map<string, unknown>(); set(name: string, value: unknown) { this.values.set(name, value); } get(name: string) { return this.values.get(name); } });
  vi.stubGlobal("isSecureContext", true); const stop = vi.fn(); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } });
  vi.spyOn(URL, "createObjectURL").mockImplementation(() => "blob:saved-question"); vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.stubGlobal("AudioContext", class { decodeAudioData() { return Promise.resolve({ numberOfChannels: 1, sampleRate: 16000, getChannelData: () => new Float32Array(16000) }); } close() { return Promise.resolve(); } });
  vi.stubGlobal("MediaRecorder", class { static isTypeSupported() { return true; } state = "inactive"; mimeType = "audio/webm"; ondataavailable?: (event: { data: Blob }) => void; onstop?: () => void; start() { this.state = "recording"; } stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["recorded"], { type: this.mimeType }) }); this.onstop?.(); } });
  return stop;
}
async function record() { fireEvent.click(screen.getByRole("button", { name: "说出我的问题" })); fireEvent.click(await screen.findByRole("button", { name: "我说完了" })); await screen.findByRole("button", { name: "让老师听听" }); }
describe("Qwen question recording", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("encodes real mono 16k 16-bit PCM WAV and enforces one-minute duration", async () => {
    vi.stubGlobal("Blob", NodeBlob); const wav = encodeHomeworkQuestionWav([new Float32Array([1, 0, -1, 0]), new Float32Array([1, 0, -1, 0])], 16000);
    const bytes = new DataView(await wav.arrayBuffer()); expect(wav.type).toBe("audio/wav"); expect(bytes.getUint16(22, true)).toBe(1); expect(bytes.getUint32(24, true)).toBe(16000); expect(bytes.getUint16(34, true)).toBe(16); expect(bytes.getInt16(44, true)).toBe(32767); expect(bytes.getInt16(48, true)).toBe(-32768);
    expect(() => encodeHomeworkQuestionWav([new Float32Array(16000 * 61)], 16000)).toThrow("一分钟");
  });
  it("requests no microphone or AI on entry and explains insecure browser contexts", () => {
    vi.stubGlobal("isSecureContext", false); const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />);
    expect(fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "说出我的问题" }));
    expect(screen.getByRole("alert")).toHaveTextContent("HTTPS"); expect(fetch).not.toHaveBeenCalled();
  });
  it("releases an active microphone on unmount", async () => {
    const stop = vi.fn(), mic = { getTracks: () => [{ stop }] }, permission = vi.fn().mockResolvedValue(mic);
    vi.stubGlobal("isSecureContext", true); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: permission } }); vi.stubGlobal("AudioContext", vi.fn());
    vi.stubGlobal("MediaRecorder", class { static isTypeSupported() { return true; } state = "inactive"; start() { this.state = "recording"; } stop() { this.state = "inactive"; } });
    const { unmount } = render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的问题" })); await screen.findByText("正在听你说，点方块说完"); unmount(); expect(stop).toHaveBeenCalledTimes(1);
  });
  it("does not reopen a late microphone permission after unmount", async () => {
    const stop = vi.fn(); let resolve!: (value: unknown) => void; const permission = vi.fn(() => new Promise(value => { resolve = value; }));
    vi.stubGlobal("isSecureContext", true); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: permission } }); vi.stubGlobal("AudioContext", vi.fn()); vi.stubGlobal("MediaRecorder", vi.fn());
    const { unmount } = render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />); fireEvent.click(screen.getByRole("button", { name: "说出我的问题" })); unmount(); resolve({ getTracks: () => [{ stop }] }); await waitFor(() => expect(stop).toHaveBeenCalledTimes(1));
  });
  it("turns a saved recording into explicit ASR then explicit tutor question, without browser speech recognition", async () => {
    const stop = installRecording();
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "为什么长方形有四条边", errorCode: null } })); vi.stubGlobal("fetch", fetch); const onQuestion = vi.fn();
    render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={3} onQuestion={onQuestion} />);
    await record(); expect(fetch).not.toHaveBeenCalled(); expect(stop).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "让老师听听" })); await screen.findByDisplayValue("为什么长方形有四条边"); expect(onQuestion).not.toHaveBeenCalled();
    const form = fetch.mock.calls[0][1].body as FormData; expect(form.get("itemRevision")).toBe("3"); expect(form.get("idempotencyKey")).toEqual(expect.any(String));
    fireEvent.click(screen.getByRole("button", { name: "问老师" })); expect(onQuestion).toHaveBeenCalledWith("为什么长方形有四条边"); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it.each([400, 403, 413])("allows a new recording after definitive HTTP %s without querying or repeating the rejected ASR", async status => {
    installRecording(); const fetch = vi.fn().mockResolvedValue(json({ ok: false, message: "录音未提交，请重新录" }, status)); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    await screen.findByText("录音未提交，请重新录"); expect(screen.getByRole("button", { name: "重新说" })).toBeEnabled(); expect(screen.queryByRole("button", { name: "让老师听听" })).not.toBeInTheDocument(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("allows a new recording after a terminal failed receipt but retains unknown receipts for GET only", async () => {
    installRecording(); const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "failed", transcript: "", errorCode: "invalid" } })); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    await screen.findByText("这段话没有听清，可以重新录一小段；旧录音不会自动重发"); expect(screen.getByRole("button", { name: "重新说" })).toBeEnabled(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("never resends a lost ASR response and offers only scoped read-only reconciliation", async () => {
    installRecording(); const fetch = vi.fn().mockRejectedValueOnce(new Error("网络中断")).mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "unknown", transcript: "", errorCode: "unknown" } })); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    await screen.findByRole("button", { name: "查看录音状态" }); expect(screen.getByRole("button", { name: "重新说" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "查看录音状态" })); await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1); expect(fetch.mock.calls.at(-1)?.[0]).toMatch(/^\/api\/transcribe\?itemRevision=1&idempotencyKey=/);
  });
  it("offers typing without requesting a microphone or recognition", () => {
    const permission = vi.fn(), fetch = vi.fn(), onQuestion = vi.fn(); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: permission } }); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" />);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "打字" }));
    fireEvent.change(screen.getByRole("textbox", { name: "写下你想问的" }), { target: { value: "为什么要加起来？" } }); fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(onQuestion).toHaveBeenCalledWith("为什么要加起来？"); expect(permission).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled();
  });
  it("falls back to typing when no microphone exists and submits an answer through the same composer", async () => {
    vi.stubGlobal("isSecureContext", true); vi.stubGlobal("MediaRecorder", vi.fn()); vi.stubGlobal("AudioContext", vi.fn()); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("absent", "NotFoundError")) } }); const onQuestion = vi.fn();
    render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} intent="answer" actionLabel="提交答案" onQuestion={onQuestion} />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的答案" }));
    expect(await screen.findByRole("textbox", { name: "写下你的答案和想法" })).toBeEnabled(); expect(screen.getByRole("alert")).toHaveTextContent("没有找到麦克风");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "3" } }); fireEvent.click(screen.getByRole("button", { name: "提交答案" })); expect(onQuestion).toHaveBeenCalledWith("3");
  });
  it("lets the child edit a mistaken recognition before submitting and never calls ASR twice", async () => {
    installRecording(); const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "第两棵", errorCode: null } })); vi.stubGlobal("fetch", fetch); const onQuestion = vi.fn();
    render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} />); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    const confirmation = await screen.findByRole("textbox", { name: "确认识别的问题" }); fireEvent.change(confirmation, { target: { value: "第二棵为什么有3个？" } }); fireEvent.click(screen.getByRole("button", { name: "问老师" }));
    expect(onQuestion).toHaveBeenCalledWith("第二棵为什么有3个？"); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("does not permit typing to discard an unknown recording receipt", async () => {
    installRecording(); const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "unknown", transcript: "", errorCode: "unknown" } })); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} />); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" })); await screen.findByRole("button", { name: "查看录音状态" });
    expect(screen.getByRole("button", { name: "打字" })).toBeDisabled(); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("keeps a sent draft until its receipt is accepted, then clears it while retaining typing", async () => {
    const onQuestion = vi.fn(); const { rerender } = render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" resetKey="" />);
    fireEvent.click(screen.getByRole("button", { name: "打字" })); fireEvent.change(screen.getByRole("textbox"), { target: { value: "为什么要加起来？" } }); fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(screen.getByRole("textbox")).toHaveValue("为什么要加起来？"); expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled(); fireEvent.click(screen.getByRole("button", { name: "发送问题" })); expect(onQuestion).toHaveBeenCalledTimes(1);
    rerender(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" resetKey="accepted-key" />);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue("")); expect(screen.getByRole("button", { name: "打字" })).toHaveAttribute("aria-pressed", "true");
  });
  it("stops teacher playback synchronously before requesting microphone permission", async () => {
    installRecording(); const stopTeacher = vi.fn(); const permission = navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>;
    render(<HomeworkQuestionRecorder allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} onStartRecording={stopTeacher} />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的问题" })); await screen.findByText("正在听你说，点方块说完");
    expect(stopTeacher).toHaveBeenCalledTimes(1); expect(stopTeacher.mock.invocationCallOrder[0]).toBeLessThan(permission.mock.invocationCallOrder[0]);
  });
});

describe("compact homework chat input", () => {
  afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it("starts with one accessible keyboard switch and a real click-to-record action", () => {
    const permission = vi.fn(), fetch = vi.fn(); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: permission } }); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} actionLabel="发送问题" />);
    const mode = screen.getByRole("button", { name: "切换到打字" });
    expect(mode).toHaveAttribute("title", "切换到打字"); expect(mode).toHaveAttribute("data-size", "icon");
    expect(screen.getByRole("button", { name: "说出我的问题" })).toBeEnabled();
    expect(screen.queryByRole("group", { name: "选择说话或打字" })).not.toBeInTheDocument();
    expect(container.querySelector(".homework-recorder-visual")).not.toBeInTheDocument();
    expect(container.querySelector(".homework-recorder-chat-details")).not.toBeInTheDocument();
    expect(permission).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled();
  });

  it("uses one-line typing beside send, preserves a draft across switches and clears only an accepted send", async () => {
    const onQuestion = vi.fn(), fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const { container, rerender } = render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" resetKey="" />);
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" }));
    const field = screen.getByRole("textbox", { name: "写下你想问的" });
    expect(field).toHaveAttribute("rows", "1"); expect(field).toHaveAttribute("placeholder", "把问题写在这里…");
    expect(field.closest("form")).toBe(screen.getByRole("button", { name: "发送问题" }).closest("form"));
    expect(container.querySelector("label.sr-only")).toHaveTextContent("写下你想问的");
    fireEvent.change(field, { target: { value: "第二棵树为什么有三个苹果？" } });
    fireEvent.click(screen.getByRole("button", { name: "切换到语音" }));
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" }));
    expect(screen.getByRole("textbox")).toHaveValue("第二棵树为什么有三个苹果？");
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(onQuestion).toHaveBeenCalledExactlyOnceWith("第二棵树为什么有三个苹果？");
    expect(screen.getByRole("textbox")).toHaveValue("第二棵树为什么有三个苹果？");
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    rerender(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" resetKey="accepted-question-key" />);
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
    expect(screen.getByRole("button", { name: "切换到语音" })).toBeEnabled(); expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps answer typing accessible after a missing microphone", async () => {
    vi.stubGlobal("isSecureContext", true); vi.stubGlobal("MediaRecorder", vi.fn()); vi.stubGlobal("AudioContext", vi.fn()); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("absent", "NotFoundError")) } });
    const onQuestion = vi.fn();
    render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={2} intent="answer" onQuestion={onQuestion} actionLabel="提交答案" />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的答案" }));
    const field = await screen.findByRole("textbox", { name: "写下你的答案和想法" });
    expect(field).toHaveAttribute("placeholder", "写下你的答案和想法…"); expect(field).toHaveAttribute("rows", "1");
    expect(screen.getByRole("alert")).toHaveTextContent("没有找到麦克风");
    fireEvent.change(field, { target: { value: "3，因为只数第二棵" } }); fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(onQuestion).toHaveBeenCalledExactlyOnceWith("3，因为只数第二棵");
  });

  it("expands real recording and confirmation only when needed, preserving the saved ASR key", async () => {
    installRecording(); const stopTeacher = vi.fn(), onQuestion = vi.fn();
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "第两棵有几个", errorCode: null } })); vi.stubGlobal("fetch", fetch);
    const { container } = render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={3} onQuestion={onQuestion} onStartRecording={stopTeacher} actionLabel="发送问题" />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的问题" }));
    expect(screen.getByRole("button", { name: "切换到打字" })).toBeDisabled();
    const done = await screen.findByRole("button", { name: "我说完了" }); expect(screen.getByRole("button", { name: "切换到打字" })).toBeDisabled();
    fireEvent.click(done); await screen.findByRole("button", { name: "让老师听听" });
    expect(container.querySelector(".homework-recorder-chat-details audio")).toHaveAttribute("src", "blob:saved-question");
    expect(fetch).not.toHaveBeenCalled(); expect(stopTeacher).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    const field = await screen.findByRole("textbox", { name: "确认识别的问题" });
    fireEvent.change(field, { target: { value: "第二棵有几个苹果？" } }); fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(onQuestion).toHaveBeenCalledExactlyOnceWith("第二棵有几个苹果？"); expect(fetch).toHaveBeenCalledTimes(1);
    const form = fetch.mock.calls[0][1].body as FormData;
    expect(form.get("itemRevision")).toBe("3"); expect(form.get("idempotencyKey")).toEqual(expect.any(String));
  });

  it("locks the icon through processing and unknown recovery without resubmitting or discarding the clip", async () => {
    installRecording(); let finish!: (value: Response) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "unknown", transcript: "", errorCode: "unknown" } })); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={7} onQuestion={vi.fn()} />);
    await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    expect(screen.getByRole("button", { name: "切换到打字" })).toBeDisabled(); expect(screen.getByRole("status")).toHaveTextContent("老师正在听你的问题");
    await act(async () => finish(json({ ok: true, transcription: { id: "hwtr_one", status: "unknown", transcript: "", errorCode: "unknown" } })));
    expect(screen.getByRole("button", { name: "切换到打字" })).toBeDisabled(); expect(screen.getByRole("button", { name: "重新说" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看录音状态" })); await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const form = fetch.mock.calls[0][1].body as FormData;
    expect(fetch.mock.calls[1][0]).toBe(`/api/transcribe?itemRevision=7&idempotencyKey=${form.get("idempotencyKey")}`);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("stops the old clip before a new recording and pauses teacher audio before opening permission", async () => {
    installRecording(); const stopTeacher = vi.fn();
    const permission = navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>;
    render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} onStartRecording={stopTeacher} />);
    await record();
    fireEvent.click(screen.getByRole("button", { name: "重新说" })); await screen.findByRole("button", { name: "我说完了" });
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1); expect(stopTeacher).toHaveBeenCalledTimes(2);
    expect(stopTeacher.mock.invocationCallOrder[1]).toBeLessThan(permission.mock.invocationCallOrder[1]);
  });

  it("retains and locks a typed draft while the tutor request is disabled", () => {
    const onQuestion = vi.fn();
    const { rerender } = render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" />);
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); fireEvent.change(screen.getByRole("textbox"), { target: { value: "为什么？" } });
    rerender(<HomeworkQuestionRecorder presentation="chat" allowTyping disabled endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} actionLabel="发送问题" />);
    expect(screen.getByRole("textbox")).toHaveValue("为什么？"); expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: "切换到语音" })).toBeDisabled(); expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    expect(onQuestion).not.toHaveBeenCalled();
  });

  it.each(["ready", "working"])("ignores a late %s GET after an accepted send resets the composer", async status => {
    installRecording(); let finish!: (value: Response) => void;
    const onQuestion = vi.fn(), onLockChange = vi.fn();
    const fetch = vi.fn().mockResolvedValueOnce(json({ ok: true, transcription: { id: "hwtr_one", status: "working", transcript: "" } })).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })); vi.stubGlobal("fetch", fetch);
    const renderRecorder = (resetKey: string) => <HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} onLockChange={onLockChange} actionLabel="发送问题" resetKey={resetKey} />;
    const { rerender } = render(renderRecorder("")); await record(); vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "让老师听听" })); await act(async () => {});
    await act(async () => vi.advanceTimersByTime(4000)); expect(fetch).toHaveBeenCalledTimes(2);
    // A slow read cannot overlap with repeated polling reads.
    await act(async () => vi.advanceTimersByTime(12000)); expect(fetch).toHaveBeenCalledTimes(2);
    rerender(renderRecorder("accepted-first-send")); await act(async () => vi.advanceTimersByTime(0));
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); fireEvent.change(screen.getByRole("textbox"), { target: { value: "新的问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" })); expect(onQuestion).toHaveBeenCalledExactlyOnceWith("新的问题");
    rerender(renderRecorder("accepted-second-send")); await act(async () => vi.advanceTimersByTime(0));
    await act(async () => finish(json({ ok: true, transcription: { id: "hwtr_one", status, transcript: status === "ready" ? "旧录音的内容" : "" } })));
    expect(screen.getByRole("textbox")).toHaveValue(""); expect(screen.getByRole("textbox")).toBeEnabled();
    expect(screen.getByRole("button", { name: "切换到语音" })).toBeEnabled(); expect(screen.queryByText("旧录音的内容")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument(); expect(onLockChange).toHaveBeenLastCalledWith(false);
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("does not poll over an unfinished POST or restore its old transcript after reset", async () => {
    installRecording(); let finish!: (value: Response) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })); vi.stubGlobal("fetch", fetch);
    const renderRecorder = (resetKey: string) => <HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} resetKey={resetKey} />;
    const { rerender } = render(renderRecorder("")); await record(); vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    await act(async () => vi.advanceTimersByTime(16000)); expect(fetch).toHaveBeenCalledTimes(1);
    rerender(renderRecorder("accepted-send")); await act(async () => vi.advanceTimersByTime(0));
    await act(async () => finish(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "旧识别内容" } })));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); expect(screen.queryByDisplayValue("旧识别内容")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "说出我的问题" })).toBeEnabled(); expect(screen.getByRole("button", { name: "切换到打字" })).toBeEnabled();
  });

  it("a new recording stays current when an older saved read finally returns", async () => {
    installRecording(); let finish!: (value: Response) => void;
    const fetch = vi.fn().mockResolvedValueOnce(json({ ok: true, transcription: { id: "hwtr_one", status: "unknown", transcript: "" } })).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })); vi.stubGlobal("fetch", fetch);
    const renderRecorder = (resetKey: string) => <HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} resetKey={resetKey} />;
    const { rerender } = render(renderRecorder("")); await record(); fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    fireEvent.click(await screen.findByRole("button", { name: "查看录音状态" }));
    rerender(renderRecorder("accepted-send")); await screen.findByRole("button", { name: "说出我的问题" });
    await record();
    await act(async () => finish(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "旧识别内容" } })));
    expect(screen.getByRole("button", { name: "让老师听听" })).toBeEnabled(); expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("unlocks after AudioContext construction fails and permits another real recording", async () => {
    const stopMic = installRecording(), WorkingContext = AudioContext, onLockChange = vi.fn();
    vi.stubGlobal("AudioContext", class { constructor() { throw new Error("录音解码器暂时不可用"); } });
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    render(<HomeworkQuestionRecorder presentation="chat" allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={vi.fn()} onLockChange={onLockChange} />);
    fireEvent.click(screen.getByRole("button", { name: "说出我的问题" })); fireEvent.click(await screen.findByRole("button", { name: "我说完了" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("录音解码器暂时不可用");
    expect(screen.getByRole("button", { name: "切换到打字" })).toBeEnabled(); expect(screen.getByRole("button", { name: "说出我的问题" })).toBeEnabled();
    expect(onLockChange).toHaveBeenLastCalledWith(false); expect(stopMic).toHaveBeenCalledTimes(1);
    vi.stubGlobal("AudioContext", WorkingContext); await record();
    expect(screen.getByRole("button", { name: "让老师听听" })).toBeEnabled(); expect(stopMic).toHaveBeenCalledTimes(2); expect(fetch).not.toHaveBeenCalled();
  });

  it("pauses a hidden preview while retaining the clip, edited transcript and input method without another ASR call", async () => {
    installRecording();
    const fetch = vi.fn().mockResolvedValue(json({ ok: true, transcription: { id: "hwtr_one", status: "ready", transcript: "第二棵有几个苹果？" } })); vi.stubGlobal("fetch", fetch);
    const onQuestion = vi.fn();
    const renderRecorder = (active: boolean) => <HomeworkQuestionRecorder presentation="chat" active={active} allowTyping endpoint="/api/transcribe" itemRevision={1} onQuestion={onQuestion} />;
    const { container, rerender } = render(renderRecorder(true)); await record();
    fireEvent.click(screen.getByRole("button", { name: "让老师听听" }));
    const transcript = await screen.findByRole("textbox", { name: "确认识别的问题" });
    fireEvent.change(transcript, { target: { value: "为什么只数第二棵？" } });
    const preview = container.querySelector("audio"); expect(preview).toHaveAttribute("src", "blob:saved-question");
    rerender(renderRecorder(false)); expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1);
    expect(container.querySelector("audio")).toBe(preview); expect(transcript).toHaveValue("为什么只数第二棵？");
    expect(screen.getByRole("button", { name: "切换到打字" })).toBeEnabled();
    rerender(renderRecorder(true)); expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox", { name: "确认识别的问题" })).toHaveValue("为什么只数第二棵？");
    fireEvent.click(screen.getByRole("button", { name: "切换到打字" }));
    expect(screen.getByRole("textbox", { name: "写下你想问的" })).toHaveValue("为什么只数第二棵？");
    rerender(renderRecorder(false)); rerender(renderRecorder(true));
    expect(screen.getByRole("button", { name: "切换到语音" })).toBeEnabled();
    expect(screen.getByRole("textbox", { name: "写下你想问的" })).toHaveValue("为什么只数第二棵？");
    expect(fetch).toHaveBeenCalledTimes(1); expect(onQuestion).not.toHaveBeenCalled();
  });
});
