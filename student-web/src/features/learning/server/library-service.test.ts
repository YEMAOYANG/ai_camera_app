import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BackendApiError } from "@/lib/api/errors";

const { studentBackendRequest } = vi.hoisted(() => ({
  studentBackendRequest: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest }));
vi.mock("@/lib/learning/student-preferences", () => ({
  readStudentFavoriteIds: () => new Set<string>(),
}));

import { loadLearningLibrary } from "@/features/learning/server/library-service";

describe("formal learning library authority", () => {
  beforeEach(() => {
    studentBackendRequest.mockReset();
  });

  it("surfaces a missing formal library and never synthesizes one from today data", async () => {
    const missing = new BackendApiError(404, "learning_library_not_ready", "正式课程还没有发布");
    studentBackendRequest.mockRejectedValue(missing);

    await expect(loadLearningLibrary(
      new NextRequest("https://learn.mira.test/api/learning/library?bucket=all"),
      { bucket: "all", limit: 20 },
    )).rejects.toBe(missing);

    expect(studentBackendRequest).toHaveBeenCalledTimes(1);
    expect(studentBackendRequest.mock.calls[0]?.[1]).toBe(
      "/api/v2/student/learning/library?bucket=all&limit=20",
    );
  });
});
