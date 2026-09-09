import { describe, expect, it } from "vitest";

import {
  studentQrChallengeSchema,
  studentQrPollingIntervalSchema,
} from "@/lib/contracts/student-session";

const validChallenge = {
  challengeId: `msc_${"A".repeat(43)}`,
  verifier: `msv_${"B".repeat(43)}`,
  displayCode: "4826",
  expiresAt: Date.now() + 120_000,
  pollingIntervalMs: 1_500,
};

describe("student QR contracts", () => {
  it("requires backend-compatible challenge, verifier and four-digit display code formats", () => {
    expect(studentQrChallengeSchema.safeParse(validChallenge).success).toBe(true);
    expect(studentQrChallengeSchema.safeParse({ ...validChallenge, challengeId: "challenge-123" }).success).toBe(false);
    expect(studentQrChallengeSchema.safeParse({ ...validChallenge, verifier: "server-only-verifier" }).success).toBe(false);
    expect(studentQrChallengeSchema.safeParse({ ...validChallenge, displayCode: "48261" }).success).toBe(false);
  });

  it("accepts every polling interval allowed by backend config while rejecting unsafe sub-250ms values", () => {
    expect(studentQrPollingIntervalSchema.safeParse(250).success).toBe(true);
    expect(studentQrPollingIntervalSchema.safeParse(120_000).success).toBe(true);
    expect(studentQrPollingIntervalSchema.safeParse(249).success).toBe(false);
  });
});
