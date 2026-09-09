import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { POST } from "@/app/api/auth/unlock/route";

function unlockRequest() {
  return new NextRequest("http://localhost/api/auth/unlock", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: "mira_student_device=device-secret",
    },
    body: JSON.stringify({ pin: "1357" }),
  });
}

describe("student unlock BFF", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("passes through the backend-unavailable error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    const response = await POST(unlockRequest());

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      ok: false,
      error: "backend_unavailable",
      message: "学习服务暂时连不上，请稍后再试",
    });
  });

  it("keeps a malformed successful backend payload as invalid_backend_response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 })),
    );

    const response = await POST(unlockRequest());

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({
      ok: false,
      error: "invalid_backend_response",
      message: "解锁服务返回了无法识别的数据",
    });
  });
});
