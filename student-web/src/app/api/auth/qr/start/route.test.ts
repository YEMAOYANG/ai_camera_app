import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { backendRequest, validChallengeId, validVerifier, validFingerprint } = vi.hoisted(() => ({
  backendRequest: vi.fn(),
  validChallengeId: `msc_${"A".repeat(43)}`,
  validVerifier: `msv_${"B".repeat(43)}`,
  validFingerprint: `mfp_${"C".repeat(43)}`,
}));

vi.mock("@/lib/api/server", () => ({ backendRequest }));
vi.mock("@/lib/auth/client-device", () => ({
  studentBrowserFingerprint: () => ({ value: validFingerprint, isNew: true }),
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

import { POST } from "@/app/api/auth/qr/start/route";

describe("student QR start BFF", () => {
  beforeEach(() => {
    backendRequest.mockReset();
    vi.stubEnv("MIRA_STUDENT_WEB_PUBLIC_URL", "https://learn.mira.test");
  });

  it("keeps the verifier server-only and returns the configured public QR URL", async () => {
    backendRequest.mockResolvedValue({
      challengeId: validChallengeId,
      verifier: validVerifier,
      displayCode: "4826",
      expiresAt: Date.now() + 120_000,
      pollingIntervalMs: 1_500,
    });

    const response = await POST(new NextRequest("http://localhost:3000/api/auth/qr/start", { method: "POST" }));
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload).toEqual({
      ok: true,
      qrValue: `https://learn.mira.test/pair/qr?challengeId=${validChallengeId}`,
      displayCode: "4826",
      expiresAt: expect.any(Number),
      pollingIntervalMs: 1_500,
    });
    expect(payload).not.toHaveProperty("challengeId");
    expect(JSON.stringify(payload)).not.toContain(validVerifier);
    expect(JSON.stringify(payload)).not.toContain(validFingerprint);
    expect(backendRequest).toHaveBeenCalledOnce();
    const [path, init] = backendRequest.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v2/student/auth/qr/challenges");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      clientDevice: {
        type: "browser",
        platform: "web",
        fingerprint: validFingerprint,
        browserName: "Safari",
        osName: "macOS",
      },
    });

    const cookies = response.headers.getSetCookie().join("\n");
    expect(cookies).toContain(`mira_student_qr_challenge=${validChallengeId}`);
    expect(cookies).toContain(`mira_student_qr_verifier=${validVerifier}`);
    expect(cookies).toContain(`mira_student_browser_fingerprint=${validFingerprint}`);
    expect(cookies).toContain("mira_student_qr_display_code=4826");
    expect(cookies).toContain("mira_student_qr_expires_at=");
    expect(cookies).toContain("mira_student_qr_polling_interval=1500");
    expect(cookies.match(/HttpOnly/g)).toHaveLength(6);
    expect(cookies.match(/SameSite=lax/gi)).toHaveLength(6);
    expect(cookies).toContain("Path=/api/auth/qr");
  });

  it("restores the same pending challenge after a page reload without creating another one", async () => {
    const expiresAt = Date.now() + 120_000;
    const request = new NextRequest("https://learn.mira.test/api/auth/qr/start", {
      method: "POST",
      headers: {
        Cookie: [
          `mira_student_qr_challenge=${validChallengeId}`,
          `mira_student_qr_verifier=${validVerifier}`,
          "mira_student_qr_display_code=4826",
          `mira_student_qr_expires_at=${expiresAt}`,
          "mira_student_qr_polling_interval=1500",
        ].join("; "),
      },
    });

    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      ok: true,
      qrValue: `https://learn.mira.test/pair/qr?challengeId=${validChallengeId}`,
      displayCode: "4826",
      expiresAt,
      pollingIntervalMs: 1_500,
    });
    expect(backendRequest).not.toHaveBeenCalled();
  });

  it.each([250, 120_000])("accepts backend-safe polling interval %i without returning 502", async (pollingIntervalMs) => {
    backendRequest.mockResolvedValue({
      challengeId: validChallengeId,
      verifier: validVerifier,
      displayCode: "4826",
      expiresAt: Date.now() + 120_000,
      pollingIntervalMs,
    });

    const response = await POST(new NextRequest("https://learn.mira.test/api/auth/qr/start", { method: "POST" }));

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ pollingIntervalMs });
  });

  it("fails closed when the public student URL is not a safe origin", async () => {
    vi.stubEnv("MIRA_STUDENT_WEB_PUBLIC_URL", "https://learn.mira.test/redirect?next=bad");
    backendRequest.mockResolvedValue({
      challengeId: validChallengeId,
      verifier: validVerifier,
      displayCode: "4826",
      expiresAt: Date.now() + 120_000,
      pollingIntervalMs: 1_500,
    });

    const response = await POST(new NextRequest("http://localhost:3000/api/auth/qr/start", { method: "POST" }));

    expect(response.status).toBe(503);
    expect(await response.json()).toMatchObject({ error: "student_web_public_url_invalid" });
  });
});
