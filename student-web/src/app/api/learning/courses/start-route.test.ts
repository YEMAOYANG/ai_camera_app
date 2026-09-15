import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BackendApiError } from "@/lib/api/errors";
import { POST } from "@/app/api/learning/courses/[courseId]/versions/[version]/start/route";

const { studentBackendRequest, applyRefreshedStudentSession } = vi.hoisted(() => ({
  studentBackendRequest: vi.fn(), applyRefreshedStudentSession: vi.fn((response: Response) => response),
}));
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest, applyRefreshedStudentSession }));
const payload = { ok: true, courseId: "course-1", courseVersion: "2", taskId: "task-2", created: true };
const context = { params: Promise.resolve({ courseId: "course-1", version: "2" }) };
function request(body: unknown = {}) {
  return new NextRequest("https://learn.mira.test/api/learning/courses/course-1/versions/2/start", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}

describe("published course start BFF", () => {
  beforeEach(() => { studentBackendRequest.mockReset(); applyRefreshedStudentSession.mockClear(); });

  it("forwards only an empty authenticated start and applies refreshed cookies", async () => {
    const refreshed = { student: { id: "student-1" } };
    studentBackendRequest.mockResolvedValue({ payload, refreshed });
    const response = await POST(request(), context);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(payload);
    expect(studentBackendRequest).toHaveBeenCalledWith(expect.anything(),
      "/api/v2/student/learning/courses/course-1/versions/2/start", { method: "POST", body: "{}" });
    expect(applyRefreshedStudentSession).toHaveBeenCalledWith(response, refreshed);
  });

  it("rejects caller supplied identity and a mismatched backend task binding", async () => {
    expect((await POST(request({ childId: "another-child" }), context)).status).toBe(400);
    expect(studentBackendRequest).not.toHaveBeenCalled();
    studentBackendRequest.mockResolvedValue({ payload: { ...payload, courseVersion: "older" } });
    const response = await POST(request(), context);
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ error: "learning_course_start_invalid" });
  });

  it.each([
    [401, "student_session_required"], [404, "learning_course_not_found"], [409, "learning_classroom_release_changed"],
  ])("preserves the backend %s status without inventing a task", async (status, code) => {
    studentBackendRequest.mockRejectedValue(new BackendApiError(status as number, code as string, "这节课暂时不能开始"));
    const response = await POST(request(), context);
    expect(response.status).toBe(status);
    expect(await response.json()).toEqual({ ok: false, error: code, message: "这节课暂时不能开始" });
  });
});
