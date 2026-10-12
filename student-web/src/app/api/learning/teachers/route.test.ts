import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, PUT } from "./route";
import { studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningTeacherProfiles } from "@/features/learning/teacher-registry";

vi.mock("@/lib/auth/student-backend-session", () => ({
  studentBackendRequest: vi.fn(),
  applyRefreshedStudentSession: (response: Response) => response,
}));

beforeEach(() => vi.mocked(studentBackendRequest).mockReset());

describe("teacher subject boundary", () => {
  it("passes science through the existing authenticated teacher endpoint and parses v3", async () => {
    const science = learningTeacherProfiles.find((p) => p.subject === "science")!;
    vi.mocked(studentBackendRequest).mockResolvedValue({ payload: { ok: true,
      registryVersion: "mira.teacher-registry.v3", items: [science], selected: null } });
    const request = new NextRequest("http://localhost/api/learning/teachers?subject=science");
    const result = await GET(request);
    expect(result.status).toBe(200);
    expect(studentBackendRequest).toHaveBeenCalledWith(request, "/api/v2/student/learning/teachers?subject=science");
    expect((await result.json()).items[0].avatarPath).toBe("/teachers/ke-science-v1.png");
  });

  it("keeps science preferences versioned and uses the existing preference API", async () => {
    const science = learningTeacherProfiles.find((p) => p.subject === "science")!;
    const body = { subject: "science", teacherProfileId: science.id, teacherProfileVersion: 1 };
    vi.mocked(studentBackendRequest).mockResolvedValue({ payload: { ok: true, subject: "science",
      childId: "child", teacher: science, updatedAt: 1 } });
    const request = new NextRequest("http://localhost/api/learning/teachers", {
      method: "PUT", body: JSON.stringify(body), headers: { "content-type": "application/json" },
    });
    expect((await PUT(request)).status).toBe(200);
    expect(studentBackendRequest).toHaveBeenCalledWith(request, "/api/v2/student/learning/preferences/teacher",
      { method: "PUT", body: JSON.stringify(body) });
  });

  it("rejects unknown teacher subjects before reaching the authenticated backend", async () => {
    expect((await GET(new NextRequest("http://localhost/api/learning/teachers?subject=history"))).status).toBe(400);
    expect(studentBackendRequest).not.toHaveBeenCalled();
  });
});
