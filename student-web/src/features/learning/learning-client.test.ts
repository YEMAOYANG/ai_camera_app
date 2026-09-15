import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  launchFullOpenMaicRuntime,
  LearningClientError,
  startLearningCourse,
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

  it("starts the exact published course version through the same-origin BFF with no client authority", async () => {
    const result = { ok: true, courseId: "course / 1", courseVersion: "2 beta", taskId: "task-2", created: false };
    fetchMock.mockResolvedValue(jsonResponse(result));
    await expect(startLearningCourse(result.courseId, result.courseVersion)).resolves.toEqual(result);
    expect(fetchMock).toHaveBeenCalledWith("/api/learning/courses/course%20%2F%201/versions/2%20beta/start",
      expect.objectContaining({ method: "POST", body: "{}" }));
  });

  it("rejects a start response bound to a different course or version", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true, courseId: "other", courseVersion: "2", taskId: "task-2", created: true }));
    await expect(startLearningCourse("requested", "2")).rejects.toMatchObject({ code: "learning_course_start_invalid" });
  });
});
