import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { backendRequest } = vi.hoisted(() => ({ backendRequest: vi.fn() }));

vi.mock("@/lib/api/server", () => ({ backendRequest }));
vi.mock("@/lib/auth/client-device", () => ({
  studentBrowserFingerprint: () => ({ value: `mfp_${"C".repeat(43)}`, isNew: true }),
  studentClientDevice: (_request: NextRequest, fingerprint: string) => ({
    label: "学习网页",
    type: "browser",
    platform: "web",
    fingerprint,
    browserName: "Safari",
    osName: "macOS",
    model: "",
    hardware: "",
    osVersion: "",
    appVersion: "0.1.0",
  }),
}));

import { POST } from "@/app/api/auth/pair/route";

describe("student pair BFF", () => {
  beforeEach(() => {
    backendRequest.mockReset();
  });

  it("forwards the backend pairingCode contract and keeps credentials in HttpOnly cookies", async () => {
    const now = Date.now();
    backendRequest.mockResolvedValue({
      ok: true,
      student: {
        id: "student-1",
        childId: "child-1",
        displayName: "乐乐",
        gradeCode: "primary_1",
      },
      device: {
        id: "device-1",
        label: "学习网页",
        trustedUntil: now + 86_400_000,
        lastActiveAt: now,
      },
      tokens: {
        accessToken: "access-secret",
        refreshToken: "refresh-secret",
        accessTokenExpiresAt: now + 900_000,
        refreshTokenExpiresAt: now + 86_400_000,
        expiresInSeconds: 900,
      },
      deviceToken: "device-secret",
    });

    const response = await POST(
      new NextRequest("http://localhost/api/auth/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: "ABCD2345" }),
      }),
    );

    expect(response.status).toBe(200);
    expect(backendRequest).toHaveBeenCalledOnce();
    const [, init] = backendRequest.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      pairingCode: "ABCD2345",
      clientDevice: {
        type: "browser",
        platform: "web",
        fingerprint: `mfp_${"C".repeat(43)}`,
        browserName: "Safari",
        osName: "macOS",
      },
    });
    expect(String(init.body)).not.toContain('"code"');

    const setCookies = response.headers.getSetCookie().join("\n");
    expect(setCookies).toContain("mira_student_access=access-secret");
    expect(setCookies).toContain("mira_student_refresh=refresh-secret");
    expect(setCookies).toContain("mira_student_device=device-secret");
    expect(setCookies).toMatch(/mira_student_qr_challenge=;.*Max-Age=0/);
    expect(setCookies).toMatch(/mira_student_qr_verifier=;.*Max-Age=0/);
    expect(setCookies).toMatch(/mira_student_qr_display_code=;.*Max-Age=0/);
    expect(setCookies).toMatch(/mira_student_qr_expires_at=;.*Max-Age=0/);
    expect(setCookies).toMatch(/mira_student_qr_polling_interval=;.*Max-Age=0/);
    expect(setCookies).toContain(`mira_student_browser_fingerprint=mfp_${"C".repeat(43)}`);
    expect(setCookies.match(/HttpOnly/g)).toHaveLength(9);
  });
});
