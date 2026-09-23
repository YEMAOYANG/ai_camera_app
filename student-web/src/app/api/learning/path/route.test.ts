import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "@/app/api/learning/path/route";
import { BackendApiError } from "@/lib/api/errors";
import { progressivePath } from "@/test/fixtures/progressive-learning";

const { studentBackendRequest, applyRefreshedStudentSession } = vi.hoisted(() => ({
  studentBackendRequest: vi.fn(), applyRefreshedStudentSession: vi.fn((response: Response) => response),
}));
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest, applyRefreshedStudentSession }));
const request = (query = "subject=chinese&gradeCode=primary_1") => new NextRequest(`https://learn.mira.test/api/learning/path?${query}`);

describe("progressive learning path BFF", () => {
  beforeEach(() => { studentBackendRequest.mockReset(); applyRefreshedStudentSession.mockClear(); });

  it("uses the student session, exact public query and private no-store response", async () => {
    const refreshed = { student: { id: "student-1" } };
    studentBackendRequest.mockResolvedValue({ payload: progressivePath(), refreshed });
    const response = await GET(request());
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await response.json()).toEqual(progressivePath());
    expect(studentBackendRequest).toHaveBeenCalledWith(expect.anything(), "/api/v2/student/learning/path?subject=chinese&gradeCode=primary_1", { cache: "no-store" });
    expect(applyRefreshedStudentSession).toHaveBeenCalledWith(response, refreshed);
  });

  it.each(["subject=math&gradeCode=primary_7", "subject=science", "subject=math&childId=another-child"])("rejects invalid or caller-selected identity query %s", async query => {
    expect((await GET(request(query))).status).toBe(400);
    expect(studentBackendRequest).not.toHaveBeenCalled();
  });

  it("does not pass private answers or a mismatched subject through to the browser", async () => {
    studentBackendRequest.mockResolvedValue({ payload: { ...progressivePath(), answer: "private-answer-999" } });
    const response = await GET(request());
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain("private-answer-999");
    studentBackendRequest.mockResolvedValue({ payload: progressivePath() });
    expect((await GET(request("subject=math"))).status).toBe(502);
  });

  it.each([401, 403, 503])("preserves backend failure %s without inventing progress", async status => {
    studentBackendRequest.mockRejectedValue(new BackendApiError(status, "path_unavailable", "暂时无法读取学习路线"));
    const response = await GET(request());
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ ok: false, error: "path_unavailable", message: "暂时无法读取学习路线" });
  });
});
