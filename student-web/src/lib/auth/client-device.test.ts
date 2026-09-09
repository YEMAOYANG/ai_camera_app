import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { studentBrowserFingerprint, studentClientDevice } from "@/lib/auth/client-device";

describe("student client device metadata", () => {
  it("derives browser and OS metadata from the BFF request user-agent", () => {
    const request = new NextRequest("https://learn.mira.test/api/auth/qr/start", {
      headers: {
        "user-agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/127.0.0.0 Safari/537.36",
        cookie: `mira_student_browser_fingerprint=mfp_${"C".repeat(43)}`,
      },
    });
    const fingerprint = studentBrowserFingerprint(request);

    expect(fingerprint).toEqual({ value: `mfp_${"C".repeat(43)}`, isNew: false });
    expect(studentClientDevice(request, fingerprint.value)).toMatchObject({
      fingerprint: fingerprint.value,
      browserName: "Chrome",
      osName: "macOS",
      platform: "macos-web",
    });
  });

  it("creates a high-entropy server-side fingerprint when the browser has none", () => {
    const request = new NextRequest("https://learn.mira.test/api/auth/qr/start");

    expect(studentBrowserFingerprint(request)).toMatchObject({
      value: expect.stringMatching(/^mfp_[A-Za-z0-9_-]{43}$/),
      isNew: true,
    });
  });
});
