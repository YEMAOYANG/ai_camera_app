import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { studentQrBackendErrorResponse } from "@/lib/auth/qr-error-response";

const { backendJsonRequest } = vi.hoisted(() => ({ backendJsonRequest: vi.fn() }));

vi.mock("@/lib/api/server", () => ({ backendJsonRequest }));

import { POST } from "@/app/api/auth/qr/exchange/route";

function exchangeRequest() {
  const challengeId = `msc_${"A".repeat(43)}`;
  const verifier = `msv_${"B".repeat(43)}`;
  return new NextRequest("https://learn.mira.test/api/auth/qr/exchange", {
    method: "POST",
    headers: {
      Cookie: `mira_student_qr_challenge=${challengeId}; mira_student_qr_verifier=${verifier}`,
    },
  });
}

describe("student QR exchange BFF", () => {
  beforeEach(() => backendJsonRequest.mockReset());

  it("returns a sanitized 202 while parent approval is pending", async () => {
    backendJsonRequest.mockResolvedValue({ status: 202, payload: { status: "pending", verifier: "must-not-leak" } });

    const response = await POST(exchangeRequest());
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ ok: false, status: "pending" });
    expect(backendJsonRequest).toHaveBeenCalledWith(
      "/api/v2/student/auth/qr/exchange",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          challengeId: `msc_${"A".repeat(43)}`,
          verifier: `msv_${"B".repeat(43)}`,
        }),
      }),
    );
  });

  it("sets the existing student session cookies and clears temporary QR cookies", async () => {
    const now = Date.now();
    backendJsonRequest.mockResolvedValue({
      status: 200,
      payload: authPayload(now),
    });

    const response = await POST(exchangeRequest());
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      ok: true,
      student: expect.objectContaining({ id: "student-1", displayName: "乐乐" }),
    });

    const cookies = response.headers.getSetCookie().join("\n");
    expect(cookies).toContain("mira_student_access=access-secret");
    expect(cookies).toContain("mira_student_refresh=refresh-secret");
    expect(cookies).toContain("mira_student_device=device-secret");
    expect(cookies).toMatch(/mira_student_qr_challenge=;.*Max-Age=0/);
    expect(cookies).toMatch(/mira_student_qr_verifier=;.*Max-Age=0/);
  });

  it("does not call the backend without both temporary cookies", async () => {
    const response = await POST(new NextRequest("https://learn.mira.test/api/auth/qr/exchange", { method: "POST" }));
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ status: "expired" });
    expect(backendJsonRequest).not.toHaveBeenCalled();
  });

  it.each([
    [410, "student_qr_challenge_expired", "expired"],
    [403, "student_qr_challenge_rejected", "rejected"],
    [409, "student_qr_challenge_consumed", "consumed"],
  ] as const)("maps terminal %s %s precisely and clears QR cookies", async (httpStatus, code, status) => {
    const response = studentQrBackendErrorResponse({ status: httpStatus, code, message: "终态提示" });

    expect(response.status).toBe(httpStatus);
    expect(await response.json()).toMatchObject({ ok: false, status, error: code });
    const cookies = response.headers.getSetCookie().join("\n");
    expect(cookies).toMatch(/mira_student_qr_challenge=;.*Max-Age=0/);
    expect(cookies).toMatch(/mira_student_qr_verifier=;.*Max-Age=0/);
  });

  it("requires deviceToken on a successful QR exchange and clears the consumed challenge", async () => {
    backendJsonRequest.mockResolvedValue({
      status: 200,
      payload: { ...authPayload(Date.now()), deviceToken: undefined },
    });

    const response = await POST(exchangeRequest());

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ error: "invalid_backend_response" });
    const cookies = response.headers.getSetCookie().join("\n");
    expect(cookies).toContain("mira_student_qr_challenge=");
    expect(cookies).toContain("Max-Age=0");
  });
});

function authPayload(now: number) {
  return {
    ok: true,
    student: { id: "student-1", childId: "child-1", displayName: "乐乐", gradeCode: "primary_1" },
    device: { id: "device-1", label: "学习网页", trustedUntil: now + 86_400_000, lastActiveAt: now },
    tokens: {
      accessToken: "access-secret",
      refreshToken: "refresh-secret",
      accessTokenExpiresAt: now + 900_000,
      refreshTokenExpiresAt: now + 86_400_000,
      expiresInSeconds: 900,
    },
    deviceToken: "device-secret",
  };
}
