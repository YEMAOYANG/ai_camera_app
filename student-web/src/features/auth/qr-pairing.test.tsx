import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QrPairing } from "@/features/auth/qr-pairing";

const replace = vi.fn();
const refresh = vi.fn();
const fetchMock = vi.fn<typeof fetch>();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

vi.mock("motion/react", () => ({
  useReducedMotion: () => true,
}));

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("QrPairing", () => {
  beforeEach(() => {
    replace.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("renders the server-provided QR inside a stable border without a decorative orbit or verifier", async () => {
    const expiresAt = Date.now() + 120_000;
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        qrValue: "https://learn.mira.test/pair/qr?challengeId=challenge-123",
        displayCode: "4826",
        expiresAt,
        pollingIntervalMs: 1_500,
      }),
    );

    render(<QrPairing />);

    const qrCode = await screen.findByTitle("Mira 学生登录二维码");
    const qrFrame = qrCode.closest("svg")?.parentElement;
    expect(qrCode).toBeInTheDocument();
    expect(qrFrame).toHaveClass("border-2", "border-[var(--mira-brand-wash)]");
    expect(qrFrame?.childElementCount).toBe(1);
    expect(screen.getByText("请家长用 Mira App 扫一扫")).toBeInTheDocument();
    expect(screen.getByLabelText("核对码 4826")).toHaveTextContent("4826");
    expect(screen.getByText("请家长确认 App 里也是这 4 位数字，再同意登录。")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("verifier");
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/qr/start", { method: "POST" });
  });

  it("polls for approval and enters the learning space after exchange succeeds", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-14T10:00:00+08:00"));
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          qrValue: "https://learn.mira.test/pair/qr?challengeId=challenge-123",
          displayCode: "4826",
          expiresAt: Date.now() + 120_000,
          pollingIntervalMs: 500,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    render(<QrPairing />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByTitle("Mira 学生登录二维码")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/auth/qr/exchange",
      expect.objectContaining({ method: "POST", signal: expect.any(AbortSignal) }),
    );
    expect(replace).toHaveBeenCalledWith("/today");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it.each([
    [410, { status: "expired", error: "student_qr_challenge_expired" }, "二维码过期啦"],
    [403, { status: "rejected", error: "student_qr_challenge_rejected" }, "家长这次没有确认"],
    [409, { status: "consumed", error: "student_qr_challenge_consumed" }, "二维码已经用过啦"],
  ] as const)("shows the precise terminal state for HTTP %i", async (httpStatus, terminalPayload, expectedTitle) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-14T10:00:00+08:00"));
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          qrValue: "https://learn.mira.test/pair/qr?challengeId=challenge-123",
          displayCode: "4826",
          expiresAt: Date.now() + 120_000,
          pollingIntervalMs: 250,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: false, ...terminalPayload, message: "终态提示" }, httpStatus));

    render(<QrPairing />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(screen.getByText(expectedTitle)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新二维码" })).toBeEnabled();
  });
});
