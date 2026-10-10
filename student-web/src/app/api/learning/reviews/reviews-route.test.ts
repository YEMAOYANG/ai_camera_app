import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
const backend = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest: backend, applyRefreshedStudentSession: (response: Response) => response }));
import { GET as list } from "./route";
import { POST as answer } from "./[reviewId]/answers/route";
import { reviewAudioPath } from "@/lib/contracts/learning-review";

describe("weekly review student boundary", () => {
  beforeEach(() => backend.mockReset());
  it("rejects family/child scope injection and self-reported grades", async () => {
    expect((await list(new NextRequest("http://localhost/api/learning/reviews?childId=someone"))).status).toBe(400);
    const request = new NextRequest("http://localhost/api/learning/reviews/review_1/answers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ questionId: "q1", response: "A", revision: 1, requestId: "test-1", correct: true, independent: true }) });
    expect((await answer(request, { params: Promise.resolve({ reviewId: "review_1" }) })).status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });
  it("keeps disabled feature quiet and removes uncontracted fields", async () => {
    backend.mockResolvedValue({ payload: { ok: true, enabled: false, reviews: [], rawToken: "private" } });
    const response = await list(new NextRequest("http://localhost/api/learning/reviews"));
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await response.json()).toEqual({ ok: true, reviews: [] });
  });
  it("restricts audio to the same student's run proxy", () => {
    expect(reviewAudioPath("/api/v2/student/learning/reviews/review_1/media/abc.wav", "review_1")).toBe("/api/learning/reviews/review_1/media/abc.wav");
    for (const value of ["https://elsewhere.test/a.wav", "/api/v2/student/learning/reviews/review_2/media/abc.wav", "/api/learning/reviews/review_1/media/../../private", "//elsewhere.test/a.wav"]) expect(reviewAudioPath(value, "review_1")).toBeNull();
  });
});
