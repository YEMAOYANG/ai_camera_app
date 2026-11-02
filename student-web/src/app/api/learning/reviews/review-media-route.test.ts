import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const backend = vi.hoisted(() => vi.fn());
const refreshedSession = vi.hoisted(() => vi.fn((response: Response) => response));
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRawRequest: backend, applyRefreshedStudentSession: refreshedSession }));
import { GET } from "./[reviewId]/media/[asset]/route";

const asset = "reviewpack." + "a".repeat(64) + ".png";
function get(name = asset, query = "") {
  return GET(new NextRequest("http://localhost/api/learning/reviews/review_one/media/" + name + query), { params: Promise.resolve({ reviewId: "review_one", asset: name }) });
}

describe("review media cookie boundary", () => {
  beforeEach(() => { backend.mockReset(); refreshedSession.mockClear(); });
  it.each([[asset, "image/png"], ["reviewpack." + "b".repeat(64) + ".wav", "audio/wav"], ["legacy_prompt.wav", "audio/x-wav"]])("proxies only authorized bytes with the actual media type", async (name, mime) => {
    const refreshed = { accessToken: "test-only" };
    backend.mockResolvedValue({ response: new Response("verified-media", { headers: { "Content-Type": mime } }), refreshed });
    const result = await get(name);
    expect(result.status).toBe(200);
    expect(result.headers.get("Content-Type")).toBe(mime);
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
    expect(result.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(await result.text()).toBe("verified-media");
    expect(backend).toHaveBeenCalledWith(expect.any(NextRequest), "/api/v2/student/learning/reviews/review_one/media/" + name, { cache: "no-store" });
    expect(refreshedSession).toHaveBeenCalledWith(expect.any(Response), refreshed);
  });
  it.each(["application/json", "text/html", "audio/wav"])("does not serve unexpected content as a PNG", async mime => {
    backend.mockResolvedValue({ response: new Response("not-image", { headers: { "Content-Type": mime } }) });
    expect((await get()).status).toBe(502);
  });
  it.each([["source.json", ""], ["../private.wav", ""], ["a..wav", ""], [asset, "?childId=other"]])("rejects arbitrary assets and scope injection before calling backend", async (name, query) => {
    expect((await get(name, query)).status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });
});
