import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackendApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ backend: vi.fn(), refresh: vi.fn((response: Response) => response) }));
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRawRequest: mocks.backend, applyRefreshedStudentSession: mocks.refresh }));

import { GET } from "./route";

const submissionId = `hw_${"a".repeat(32)}`;
const pageId = `hwp_${"b".repeat(32)}`;
const context = { params: Promise.resolve({ submissionId, pageId }) };
const path = `/api/learning/homework/${submissionId}/pages/${pageId}/image`;
const request = (query = "") => new NextRequest(`http://localhost${path}${query}`);

describe("private student homework-photo proxy", () => {
  beforeEach(() => { mocks.backend.mockReset(); mocks.refresh.mockClear(); });

  it.each(["image/png", "image/jpeg", "image/webp", "IMAGE/PNG; charset=binary"])("streams approved image MIME %s and applies refreshed student cookies", async (contentType) => {
    const refreshed = { tokens: { accessToken: "student-test" } };
    mocks.backend.mockResolvedValue({ response: new Response(new Uint8Array([137, 80, 78, 71]), { headers: { "Content-Type": contentType } }), refreshed });
    const response = await GET(request(), context);
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe(contentType);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([137, 80, 78, 71]);
    expect(mocks.backend).toHaveBeenCalledWith(expect.any(NextRequest), `/api/v2/student/learning/homework/${submissionId}/pages/${pageId}/image`, { cache: "no-store" });
    expect(mocks.refresh).toHaveBeenCalledWith(response, refreshed);
  });

  it.each(["?childId=other", "?familyId=other", "?url=https://example.test/photo", "?token=parent", "?size=small"])("rejects query injection %s before requesting the backend", async (query) => {
    const response = await GET(request(query), context);
    expect(response.status).toBe(400);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(mocks.backend).not.toHaveBeenCalled();
  });

  it.each([
    { submissionId: "../parent", pageId },
    { submissionId, pageId: "../other" },
    { submissionId: `hw_${"a".repeat(31)}`, pageId },
    { submissionId, pageId: `hwp_${"B".repeat(32)}` },
  ])("rejects malformed identifiers %o", async (params) => {
    expect((await GET(request(), { params: Promise.resolve(params) })).status).toBe(400);
    expect(mocks.backend).not.toHaveBeenCalled();
  });

  it.each(["text/html", "application/json", "image/svg+xml", "image/gif", ""])("blocks unsafe or missing image MIME %s without exposing response text", async (contentType) => {
    const refreshed = { tokens: { accessToken: "student-test" } };
    mocks.backend.mockResolvedValue({ response: new Response("private upstream content", { headers: { "Content-Type": contentType } }), refreshed });
    const response = await GET(request(), context);
    expect(response.status).toBe(502);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await response.text()).toBe("");
    expect(mocks.refresh).toHaveBeenCalledWith(response, refreshed);
  });

  it.each([401, 403, 404, 409, 503])("preserves backend status %i for expired sessions, wrong ownership and unavailable images", async (status) => {
    mocks.backend.mockRejectedValue(new BackendApiError(status, "homework_page_not_found", "照片暂时不可用"));
    const response = await GET(request(), context);
    expect(response.status).toBe(status);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(await response.json()).toEqual({ ok: false, error: "homework_page_not_found", message: "照片暂时不可用" });
  });

  it("returns a private generic failure when the upstream cannot connect", async () => {
    mocks.backend.mockRejectedValue(new Error("internal URL or secret"));
    const response = await GET(request(), context);
    expect(response.status).toBe(502);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await response.text()).not.toContain("internal URL or secret");
  });
});
