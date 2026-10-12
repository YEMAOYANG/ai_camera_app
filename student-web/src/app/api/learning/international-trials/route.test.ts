import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import manifest from "../../../../../../backend/content/international_textbook_trials.v1.json";
import { BackendApiError } from "@/lib/api/errors";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { GET } from "./route";

vi.mock("@/lib/auth/student-backend-session", () => ({
  studentBackendRequest: vi.fn(),
  applyRefreshedStudentSession: vi.fn((response: Response) => response),
}));

beforeEach(() => vi.clearAllMocks());

describe("international trial read-only proxy", () => {
  it("reads only the authenticated endpoint, validates its payload and prevents shared caching", async () => {
    const payload = { ok: true, ...manifest, generation: { status: "blocked_source", canGenerate: false, publishedCourseKey: null } };
    vi.mocked(studentBackendRequest).mockResolvedValue({ payload });
    const request = new NextRequest("http://localhost/api/learning/international-trials");
    const result = await GET(request);
    expect(result.status).toBe(200);
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await result.json()).toEqual(payload);
    expect(studentBackendRequest).toHaveBeenCalledExactlyOnceWith(request, "/api/v2/student/learning/international-trials", { cache: "no-store" });
    expect(applyRefreshedStudentSession).toHaveBeenCalledWith(result, undefined);
  });

  it("rejects all caller-supplied identity or generation parameters before forwarding", async () => {
    const result = await GET(new NextRequest("http://localhost/api/learning/international-trials?childId=other&generate=true"));
    expect(result.status).toBe(400);
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
    expect(studentBackendRequest).not.toHaveBeenCalled();
  });

  it.each([401, 403, 500])("returns a safe %s failure without leaking backend details", async status => {
    vi.mocked(studentBackendRequest).mockRejectedValue(new BackendApiError(status, "private_backend_error", "/private/source/token=secret"));
    const result = await GET(new NextRequest("http://localhost/api/learning/international-trials"));
    expect(result.status).toBe(status === 500 ? 502 : status);
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await result.text()).not.toMatch(/private|secret|token/);
  });

  it("does not expose a malformed backend payload or validation details", async () => {
    vi.mocked(studentBackendRequest).mockResolvedValue({ payload: { ...manifest, providerKey: "secret" } });
    const result = await GET(new NextRequest("http://localhost/api/learning/international-trials"));
    expect(result.status).toBe(502);
    expect(await result.json()).toEqual({ ok: false, error: "international_trial_load_failed", message: "教材测试暂时没有加载成功，请再试一次" });
  });
});
