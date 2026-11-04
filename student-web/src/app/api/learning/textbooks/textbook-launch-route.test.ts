import { createHash } from "node:crypto";

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { studentBackendRequest } = vi.hoisted(() => ({
  studentBackendRequest: vi.fn(),
}));

vi.mock("@/lib/auth/student-backend-session", () => ({
  studentBackendRequest,
  applyRefreshedStudentSession: (response: Response) => response,
}));

import { POST } from "@/app/api/learning/textbooks/courses/[contentKey]/launch/route";

const contentKey = "a".repeat(64);
const classroomId = "tbpub_0123456789abcdef01234567";
const token = "tbpr_local-runtime-token";
const launch = {
  ok: true as const,
  contentKey,
  title: "0的认识",
  editionId: "pep-math-g1-upper-2022-standard",
  revisionId: "directory-review-1",
  unitId: "unit-1",
  learningSessionId: "learning-session-1",
  launchUrl: "http://192.168.228.95:3101/mira/textbook-launch?ticket=one-time-secret",
};

function request(host = "localhost:3000") {
  return new NextRequest(`http://0.0.0.0:3000/api/learning/textbooks/courses/${contentKey}/launch`, {
    method: "POST",
    headers: { host },
  });
}

describe("textbook launch BFF", () => {
  beforeEach(() => {
    studentBackendRequest.mockReset();
    studentBackendRequest.mockResolvedValue({ payload: launch });
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("MIRA_LOCAL_LAN_PRODUCTION_MODE", "1");
    vi.stubEnv("OPENMAIC_FULL_RUNTIME_PUBLIC_URL", "http://192.168.228.95:3101");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("server-establishes the same-host runtime session without returning the ticket", async () => {
    const headers = new Headers({
      Location: `/classroom/${classroomId}?mira=1&textbook=1`,
    });
    headers.append("Set-Cookie",
      `mira_openmaic_runtime=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900`);
    const scoped = `mira_openmaic_runtime_classroom_${createHash("sha256")
      .update(classroomId).digest("hex").slice(0, 32)}`;
    headers.append("Set-Cookie", `${scoped}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900`);
    const runtimeFetch = vi.fn().mockResolvedValue(new Response(null, { status: 303, headers }));
    vi.stubGlobal("fetch", runtimeFetch);

    const response = await POST(request(), { params: Promise.resolve({ contentKey }) });
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(runtimeFetch).toHaveBeenCalledWith(launch.launchUrl, expect.objectContaining({
      method: "GET", redirect: "manual", cache: "no-store",
    }));
    expect(body.launchUrl).toBe(`http://localhost:3101/classroom/${classroomId}?mira=1&textbook=1`);
    expect(JSON.stringify(body)).not.toContain("one-time-secret");
    expect(response.headers.get("set-cookie")).toContain("mira_openmaic_runtime=");
    expect(response.headers.get("set-cookie")).toContain(`${scoped}=`);
    expect(response.headers.get("set-cookie")).toContain("SameSite=lax");
    expect(response.headers.get("set-cookie")).not.toContain("Partitioned");
  });

  it("accepts the backend's four-hour fixed-textbook runtime lifetime", async () => {
    const headers = new Headers({
      Location: `/classroom/${classroomId}?mira=1&textbook=1`,
    });
    const scoped = `mira_openmaic_runtime_classroom_${createHash("sha256")
      .update(classroomId).digest("hex").slice(0, 32)}`;
    headers.append("Set-Cookie",
      `mira_openmaic_runtime=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=14400`);
    headers.append("Set-Cookie",
      `${scoped}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=14400`);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 303, headers })));

    const response = await POST(request(), { params: Promise.resolve({ contentKey }) });

    expect(response.status).toBe(200);
    expect((await response.json()).launchUrl).toBe(
      `http://localhost:3101/classroom/${classroomId}?mira=1&textbook=1`,
    );
  });

  it("keeps the pinned launch flow for a different browser hostname", async () => {
    const runtimeFetch = vi.fn();
    vi.stubGlobal("fetch", runtimeFetch);

    const response = await POST(request("attacker.example:3000"), {
      params: Promise.resolve({ contentKey }),
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(launch);
    expect(runtimeFetch).not.toHaveBeenCalled();
  });

  it("fails closed when the runtime redirect contract is invalid", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, {
      status: 303,
      headers: { Location: "https://attacker.example/classroom/other" },
    })));

    const response = await POST(request(), { params: Promise.resolve({ contentKey }) });

    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(JSON.stringify(await response.json())).not.toContain("one-time-secret");
  });
});
