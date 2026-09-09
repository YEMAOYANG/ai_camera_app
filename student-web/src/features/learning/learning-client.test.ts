import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  launchFullOpenMaicRuntime,
  LearningClientError,
} from "@/features/learning/learning-client";
import {
  formalRuntimeLaunchFixture,
  sampleRuntimeLaunchFixture,
} from "@/test/fixtures/openmaic-runtime";

const fetchMock = vi.fn();

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("formal classroom launch client", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("rejects a legacy sample launch from the student BFF", async () => {
    fetchMock.mockResolvedValue(jsonResponse(sampleRuntimeLaunchFixture));

    await expect(launchFullOpenMaicRuntime("session-1")).rejects.toEqual(
      expect.objectContaining<Partial<LearningClientError>>({
        status: 502,
        code: "openmaic_runtime_contract_invalid",
      }),
    );
  });

  it("accepts a fully bound formal launch from the student BFF", async () => {
    fetchMock.mockResolvedValue(jsonResponse(formalRuntimeLaunchFixture));

    await expect(launchFullOpenMaicRuntime("session-1")).resolves.toEqual(formalRuntimeLaunchFixture);
  });
});
