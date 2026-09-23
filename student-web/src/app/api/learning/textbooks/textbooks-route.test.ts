import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const backend = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/student-backend-session", () => ({ studentBackendRequest: backend, applyRefreshedStudentSession: (response: Response) => response }));
import { GET as catalog } from "./route";
import { GET as contents } from "./[editionId]/contents/route";

describe("textbook student proxy", () => {
  beforeEach(() => backend.mockReset());
  it("rejects parent/child scope injection before forwarding", async () => {
    const result = await catalog(new NextRequest("http://localhost/api/learning/textbooks?childId=other"));
    expect(result.status).toBe(400);
    expect(backend).not.toHaveBeenCalled();
  });
  it("rejects missing or duplicate revisions", async () => {
    for (const query of ["", "?alignmentRevisionId=a&alignmentRevisionId=b"]) {
      const response = await contents(new NextRequest(`http://localhost/api/learning/textbooks/book/contents${query}`), { params: Promise.resolve({ editionId: "book" }) });
      expect(response.status).toBe(400);
    }
    expect(backend).not.toHaveBeenCalled();
  });
  it("preserves no-store and projects only public catalog fields", async () => {
    backend.mockResolvedValue({ payload: { ok: true, schemaVersion: "mira.learning.textbooks.v1", gradeCode: "primary_1", schoolYearStartYear: 2026, semester: "upper", books: [], privateAnswer: "secret" }, refreshed: null });
    const result = await catalog(new NextRequest("http://localhost/api/learning/textbooks"));
    expect(result.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await result.json()).not.toHaveProperty("privateAnswer");
    expect(backend.mock.calls[0][1]).toBe("/api/v2/student/learning/textbooks");
  });
});
