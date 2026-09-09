import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { BackendApiError } from "@/lib/api/errors";
import { backendJsonRequest } from "@/lib/api/server";

describe("backendJsonRequest", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps a backend network failure to a usable service error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    await expect(backendJsonRequest("/api/v2/student/auth/unlock")).rejects.toEqual(
      new BackendApiError(503, "backend_unavailable", "学习服务暂时连不上，请稍后再试"),
    );
  });
});
