import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
import { HomeworkAiTutor } from "./homework-ai-tutor";
import { homeworkTutorQuestions } from "./homework-paper-context";

const id = `hw_${"a".repeat(32)}`, itemId = `hwi_${"b".repeat(56)}`, pageId = `hwp_${"c".repeat(32)}`, turnId = `hwt_${"d".repeat(32)}`, replyId = `hwt_${"e".repeat(32)}`;
const submission = homeworkDetailSchema.parse({ ok: true, submission: { id, title: "看图数数", gradeCode: "primary_1", subject: "math", revision: 1, status: "ready", items: [], tutorItems: [{ id: itemId, revision: 1, prompt: "数一数", status: "incorrect", tutorAvailable: true, reviewContext: { pageId, region: { x: .1, y: .1, width: .5, height: .2 }, originalAnswer: "4", originalOrdinal: 1 } }], pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1000, height: 1500, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${id}/pages/${pageId}/image` }], summary: { total: 0, corrected: 0, incorrect: 1 }, createdAt: 1, updatedAt: 1, readyForStudent: false } }).submission;
const item = homeworkTutorQuestions(submission)[0];
const turn = { id: turnId, mode: "explain", message: "", status: "ready", teacherText: "看看原图，再数一数。", steps: [{ id: "look", text: "看看原图，再数一数。", visual: { kind: "paper_region" } }], assessment: { status: "guidance_only", method: "ai_guidance", countsForAbility: false }, audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${turnId}/audio` }, createdAt: 1 };
const snapshot = (turns: unknown[]) => ({ ok: true, tutor: { itemId, itemRevision: 1, enabled: true, voiceAvailable: true, turns } });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
const postReply = (reply: typeof turn & { mode: string; message: string }) => (_url: string, init: RequestInit) => Promise.resolve(json(snapshot([turn, { ...reply, requestKey: JSON.parse(String(init.body)).idempotencyKey }])));

describe("real tutor composer without a microphone", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
  it.each(["primary_1", "primary_2", "primary_4"])("supports typed questions in %s and renders the teacher's picture reply and explicit voice replay", async gradeCode => {
    const getUserMedia = vi.fn(), audio = vi.fn(function () { return { play: vi.fn().mockResolvedValue(undefined), pause: vi.fn() }; }); vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } }); vi.stubGlobal("Audio", audio);
    const message = "为什么第二棵要从左边数？", reply = { ...turn, id: replyId, mode: "followup", message, teacherText: "先找到左边，再一棵一棵数。", steps: [{ id: "answer", text: "先找到左边，再一棵一棵数。", visual: { kind: "paper_region" } }], audio: { status: "ready", assetUrl: `/api/v2/student/learning/homework/${id}/items/${itemId}/tutor/${replyId}/audio` } };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn]))).mockImplementationOnce(postReply(reply)); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={{ ...submission, gradeCode }} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "问老师" })); expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "切换到打字" }));
    fireEvent.change(screen.getByRole("textbox", { name: "写下你想问的" }), { target: { value: message } }); fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    expect(await screen.findByText("先找到左边，再一棵一棵数。")).toBeVisible(); expect(screen.getByLabelText("本次向老师提问")).toHaveTextContent(`你问：${message}`);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "followup", message, itemRevision: 1 }); expect(getUserMedia).not.toHaveBeenCalled(); await waitFor(() => expect(audio).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "暂停老师回答" })); expect(audio).toHaveBeenCalledTimes(1); fireEvent.click(screen.getByRole("button", { name: "听老师回答" })); expect(audio).toHaveBeenCalledTimes(1); expect(fetch.mock.calls.filter(([url]) => String(url).includes("transcribe"))).toHaveLength(0);
  });
  it("submits a typed correction as an answer rather than a teacher question", async () => {
    const message = "3", reply = { ...turn, id: replyId, mode: "answer", message };
    const fetch = vi.fn().mockResolvedValueOnce(json(snapshot([turn]))).mockImplementationOnce(postReply(reply)); vi.stubGlobal("fetch", fetch);
    render(<HomeworkAiTutor submission={submission} item={item} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "提交订正答案" })); fireEvent.click(screen.getByRole("button", { name: "切换到打字" })); fireEvent.change(screen.getByRole("textbox", { name: "写下你的答案和想法" }), { target: { value: message } }); fireEvent.click(screen.getByRole("button", { name: "提交答案" }));
    expect(await screen.findByLabelText("本次提交的答案")).toHaveTextContent("你的答案：3"); expect(JSON.parse(fetch.mock.calls[1][1].body)).toMatchObject({ mode: "answer", message });
  });
});
