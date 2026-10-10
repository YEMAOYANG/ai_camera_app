import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "@/test/fixtures/homework-service.json";
const backend = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest: backend, applyRefreshedStudentSession: (response: Response) => response }));
import { GET as list } from "./route";
import { GET as detail } from "./[submissionId]/route";
import { POST as answer } from "./[submissionId]/items/[itemId]/answers/route";
import { POST as action } from "./[submissionId]/items/[itemId]/actions/route";
import { POST as capture } from "../homework-captures/route";
import { homeworkDetailSchema } from "@/lib/contracts/homework";

describe("real isolated-service homework contract", () => {
  beforeEach(() => backend.mockReset());
  it("parses real service list/detail/actions/answer and strips grading keys", async () => {
    backend.mockResolvedValue({ payload: fixture.studentList });
    const response = await list(new NextRequest("http://localhost/api/learning/homework"));
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    const parsed = await response.json();
    expect(parsed.captureTasks[0].available).toBe(false);
    expect(parsed.submissions[0].items[0]).not.toHaveProperty("expectedAnswer");
    for (const payload of [fixture.studentDetail, fixture.studentAction, fixture.studentAnswer]) expect(homeworkDetailSchema.safeParse(payload).success).toBe(true);
    backend.mockResolvedValue({ payload: fixture.studentDetail });
    expect((await detail(new NextRequest("http://localhost/api/learning/homework/x"), { params: Promise.resolve({ submissionId: fixture.studentDetail.submission.id }) })).status).toBe(200);
  });
  it("rejects target-child injection, self scoring and arbitrary camera ids", async () => {
    expect((await list(new NextRequest("http://localhost/api/learning/homework?childId=other"))).status).toBe(400);
    const request = (body: unknown) => new NextRequest("http://localhost/api/learning/homework", { method: "POST", body: JSON.stringify(body) });
    expect((await answer(request({ answer: "n5", itemRevision: 1, idempotencyKey: "test", correct: true }), { params: Promise.resolve({ submissionId: fixture.studentDetail.submission.id, itemId: fixture.studentDetail.submission.items[0].id }) })).status).toBe(400);
    expect((await capture(request({ taskId: "task-a", idempotencyKey: "3dabf4e7-09de-4a1f-a65e-1846c1004ade", deviceId: "other-family" }))).status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });
  it("proxies a separate idempotent paper acknowledgement and rejects a fabricated answer grade", async () => {
    const params = { params: Promise.resolve({ submissionId: fixture.studentDetail.submission.id, itemId: fixture.studentDetail.submission.items[0].id }) }, request = (body: unknown) => new NextRequest("http://localhost/api/learning/homework", { method: "POST", body: JSON.stringify(body) });
    for (const body of [{ action: "self_complete", itemRevision: 1 }, { action: "self_complete", itemRevision: 1, idempotencyKey: "one", correct: true }]) expect((await action(request(body), params)).status).toBe(400);
    backend.mockResolvedValue({ payload: fixture.studentDetail }); const response = await action(request({ action: "self_complete", itemRevision: 1, idempotencyKey: "one" }), params);
    expect(response.status).toBe(200); expect(JSON.parse(backend.mock.calls[0][2].body)).toEqual({ action: "self_complete", itemRevision: 1, idempotencyKey: "one" });
  });
});
