import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
const backend = vi.hoisted(() => vi.fn());
const raw = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest: backend, studentBackendRawRequest: raw, applyRefreshedStudentSession: (response: Response) => response }));
import { homeworkTutorAudioRoute, homeworkTutorRoute, homeworkTutorTranscribeRoute } from "./homework-tutor-route";
const p = { submissionId: `hw_${"a".repeat(32)}`, itemId: `hwi_${"b".repeat(56)}` }, turnId = `hwt_${"c".repeat(32)}`;
const payload = { ok: true, tutor: { itemId: p.itemId, itemRevision: 1, enabled: true, voiceAvailable: true, turns: [] } };
const post = (body: unknown) => new NextRequest("http://localhost/api/learning/homework/tutor", { method: "POST", body: JSON.stringify(body) });
describe("private student tutor BFF", () => {
  beforeEach(() => { backend.mockReset(); raw.mockReset(); });
  it("strictly validates question input and refuses family/child/scoring injection", async () => {
    for (const patch of [{ childId: "other" }, { correct: true }, { parentToken: "invalid" }, { history: [] }]) expect((await homeworkTutorRoute(post({ itemRevision: 1, idempotencyKey: "one", mode: "followup", message: "为什么", ...patch }), p)).status).toBe(400);
    expect((await homeworkTutorRoute(post({ itemRevision: 1, idempotencyKey: "one", mode: "answer", message: " " }), p)).status).toBe(400);
    expect((await homeworkTutorRoute(new NextRequest("http://localhost/api/x?childId=other"), p)).status).toBe(400); expect(backend).not.toHaveBeenCalled();
  });
  it("isolates queue creation and read-only restoration with no provider metadata in responses", async () => {
    backend.mockResolvedValue({ payload: { ...payload, providerKey: "should-be-stripped" } });
    const response = await homeworkTutorRoute(post({ itemRevision: 1, idempotencyKey: "one", mode: "explain", message: "" }), p);
    expect(response.status).toBe(202); expect(response.headers.get("cache-control")).toBe("private, no-store"); expect(await response.json()).not.toHaveProperty("providerKey");
    expect(backend.mock.calls[0][1]).toBe(`/api/v2/student/learning/homework/${p.submissionId}/items/${p.itemId}/tutor`);
    await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p); expect(backend.mock.calls[1][2].method).toBe("GET");
  });
  it.each(["queued", "working"])("accepts the real %s turn with an absent assessment without retrying submission", async status => {
    const turn = { id: turnId, requestKey: "one", mode: "explain", message: "", status, teacherText: "", steps: [], assessment: null, audio: { status: "pending", errorCode: null }, errorCode: null, createdAt: 1 };
    const responsePayload = { ...payload, tutor: { ...payload.tutor, turns: [turn], remainingTurnsPerItem: 19, remainingCallsPerSubmission: 199 } };
    backend.mockResolvedValue({ payload: responsePayload });
    const submitted = await homeworkTutorRoute(post({ itemRevision: 1, idempotencyKey: "one", mode: "explain", message: "" }), p);
    expect(submitted.status).toBe(202); expect((await submitted.json()).tutor.turns[0]).toEqual(turn);
    const restored = await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p);
    expect(restored.status).toBe(200); expect((await restored.json()).tutor.turns[0].assessment).toBeNull();
    expect(backend.mock.calls.map(([, , options]) => options.method)).toEqual(["POST", "GET"]);
  });
  it("rejects a fabricated partial assessment rather than turning a pending explanation into a grade", async () => {
    backend.mockResolvedValue({ payload: { ...payload, tutor: { ...payload.tutor, turns: [{ id: turnId, mode: "explain", message: "", status: "queued", teacherText: "", steps: [], assessment: { method: "ai_guidance", countsForAbility: false }, audio: { status: "pending" }, createdAt: 1 }] } } });
    expect((await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p)).status).toBe(502);
    expect(backend).toHaveBeenCalledTimes(1); expect(backend.mock.calls[0][2].method).toBe("GET");
  });
  it("preserves the server zoom-review flag without leaking its private image contract", async () => {
    const turn = { id: turnId, mode: "explain", message: "", status: "ready", teacherText: "老师需要放大原题重新看", steps: [], assessment: { status: "needs_confirmation", method: "ai_guidance", countsForAbility: false }, audio: { status: "unavailable", errorCode: "homework_tutor_source_image_review_required" }, createdAt: 1, sourceImageReviewRequired: true, sourceCheck: { status: "matched", basis: "original_image" }, sourceImageContract: { privateInputHash: "not-for-client" } };
    backend.mockResolvedValue({ payload: { ...payload, tutor: { ...payload.tutor, turns: [turn] } } });
    const response = await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p), body = await response.json();
    expect(response.status).toBe(200); expect(body.tutor.turns[0].sourceImageReviewRequired).toBe(true); expect(body.tutor.turns[0]).not.toHaveProperty("sourceImageContract");
    expect(backend).toHaveBeenCalledTimes(1); expect(backend.mock.calls[0][2].method).toBe("GET");
  });
  it("preserves a guidance-only comparison with the paper reference on read without creating another teacher request", async () => {
    const comparison = { status: "conflict", reason: "same answer position has a different reference", referenceAnswer: "2", teacherAnswer: "4" };
    const turn = { id: turnId, mode: "explain", message: "", status: "ready", teacherText: "看原图再想想。", steps: [], assessment: { status: "guidance_only", method: "ai_guidance", countsForAbility: false }, audio: { status: "unavailable" }, createdAt: 1, gradingReferenceComparison: comparison };
    backend.mockResolvedValue({ payload: { ...payload, tutor: { ...payload.tutor, turns: [turn] } } });
    const response = await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p);
    expect(response.status).toBe(200); expect((await response.json()).tutor.turns[0].gradingReferenceComparison).toEqual(comparison);
    expect(backend).toHaveBeenCalledTimes(1); expect(backend.mock.calls[0][2].method).toBe("GET");
  });
  it("does not proxy another item's result or arbitrary audio identifiers", async () => {
    backend.mockResolvedValue({ payload: { ...payload, tutor: { ...payload.tutor, itemId: `hwi_${"d".repeat(56)}` } } });
    expect((await homeworkTutorRoute(new NextRequest("http://localhost/api/x"), p)).status).toBe(502);
    expect((await homeworkTutorAudioRoute(new NextRequest("http://localhost/api/x"), { ...p, turnId: "../../secret" })).status).toBe(400); expect(raw).not.toHaveBeenCalled();
  });
  it("rejects audio recovery injection and forwards only an explicit existing-turn recovery", async () => {
    expect((await homeworkTutorAudioRoute(post({ itemRevision: 1, idempotencyKey: "one", retryVision: true }), { ...p, turnId })).status).toBe(400);
    backend.mockResolvedValue({ payload }); expect((await homeworkTutorAudioRoute(post({ itemRevision: 1, idempotencyKey: "one" }), { ...p, turnId })).status).toBe(202);
    expect(backend.mock.calls[0][1]).toBe(`/api/v2/student/learning/homework/${p.submissionId}/items/${p.itemId}/tutor/${turnId}/audio`);
  });
  it("uses scoped GET transcription reconciliation and rejects extra query parameters", async () => {
    const transcription = { ok: true, transcription: { id: `hwtr_${"e".repeat(56)}`, status: "ready", transcript: "这道题为什么", errorCode: null } };
    backend.mockResolvedValue({ payload: transcription });
    const response = await homeworkTutorTranscribeRoute(new NextRequest("http://localhost/api/x?itemRevision=1&idempotencyKey=one"), p);
    expect(response.status).toBe(200); expect(await response.json()).toEqual(transcription); expect(backend.mock.calls[0][2].method).toBeUndefined();
    expect((await homeworkTutorTranscribeRoute(new NextRequest("http://localhost/api/x?itemRevision=1&idempotencyKey=one&childId=other"), p)).status).toBe(400);
  });
  it("refuses oversized audio before reading or sending it", async () => {
    const request = new NextRequest("http://localhost/api/x", { method: "POST", headers: { "content-length": String(3 * 1024 * 1024) }, body: "irrelevant" });
    expect((await homeworkTutorTranscribeRoute(request, p)).status).toBe(413); expect(raw).not.toHaveBeenCalled();
  });
});
