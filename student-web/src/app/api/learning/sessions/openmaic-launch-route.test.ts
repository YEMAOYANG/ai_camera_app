import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BackendApiError } from "@/lib/api/errors";
import {
  formalRuntimeLaunchFixture,
  sampleRuntimeLaunchFixture,
} from "@/test/fixtures/openmaic-runtime";

const { studentBackendRequest } = vi.hoisted(() => ({
  studentBackendRequest: vi.fn(),
}));

vi.mock("@/lib/auth/student-backend-session", () => ({
  studentBackendRequest,
  applyRefreshedStudentSession: (response: Response) => response,
}));

import { POST } from "@/app/api/learning/sessions/[sessionId]/openmaic-launch/route";

const validLaunch = formalRuntimeLaunchFixture;

function request() {
  return new NextRequest("https://learn.mira.test/api/learning/sessions/session-1/openmaic-launch", {
    method: "POST",
  });
}

describe("OpenMAIC launch BFF trust gate", () => {
  beforeEach(() => {
    studentBackendRequest.mockReset();
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("OPENMAIC_FULL_RUNTIME_PUBLIC_URL", "https://classroom.mira.test");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns a schema-verified launch from the exact configured runtime origin", async () => {
    studentBackendRequest.mockResolvedValue({ payload: validLaunch });

    const response = await POST(request(), { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(validLaunch);
  });

  it("returns a same-host local launch after validating the configured gateway", async () => {
    vi.stubEnv("MIRA_LOCAL_LAN_PRODUCTION_MODE", "1");
    vi.stubEnv("OPENMAIC_FULL_RUNTIME_PUBLIC_URL", "http://192.168.228.95:3101");
    const launchUrl = "http://192.168.228.95:3101/mira/launch?ticket=one-time";
    studentBackendRequest.mockResolvedValue({ payload: { ...validLaunch, launchUrl } });
    const localRequest = new NextRequest("http://0.0.0.0:3000/api/learning/sessions/session-1/openmaic-launch", {
      method: "POST", headers: { host: "localhost:3000" },
    });

    const response = await POST(localRequest, { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ...validLaunch, launchUrl: "http://localhost:3101/mira/launch?ticket=one-time" });
  });

  it("does not let request headers introduce a new gateway destination", async () => {
    vi.stubEnv("MIRA_LOCAL_LAN_PRODUCTION_MODE", "1");
    vi.stubEnv("OPENMAIC_FULL_RUNTIME_PUBLIC_URL", "http://192.168.228.95:3101");
    const launch = { ...validLaunch, launchUrl: "http://192.168.228.95:3101/mira/launch?ticket=one-time" };
    studentBackendRequest.mockResolvedValue({ payload: launch });
    const hostileRequest = new NextRequest("http://0.0.0.0:3000/api/learning/sessions/session-1/openmaic-launch", {
      method: "POST", headers: { host: "attacker.example:3000", "x-forwarded-host": "other.example" },
    });

    const response = await POST(hostileRequest, { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(launch);
  });

  it("rejects a sample launch even when its origin and legacy contract are otherwise valid", async () => {
    studentBackendRequest.mockResolvedValue({ payload: sampleRuntimeLaunchFixture });

    const response = await POST(request(), { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({
      error: "openmaic_runtime_contract_invalid",
    });
  });

  it("blocks a valid-looking launch ticket from any other origin", async () => {
    studentBackendRequest.mockResolvedValue({
      payload: {
        ...validLaunch,
        launchUrl: "https://classroom.mira.test.attacker.example/mira/launch?ticket=one-time",
      },
    });

    const response = await POST(request(), { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({
      error: "openmaic_runtime_origin_untrusted",
    });
  });

  it("returns an actionable contract error instead of forwarding an unverified manifest", async () => {
    studentBackendRequest.mockResolvedValue({
      payload: {
        ...validLaunch,
        features: { ...validLaunch.features, speechAudio: { verified: false } },
      },
    });

    const response = await POST(request(), { params: Promise.resolve({ sessionId: "session-1" }) });

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({
      error: "openmaic_runtime_contract_invalid",
      message: "课堂暂时无法打开，请稍后重试；若仍无法打开，请联系管理员。",
    });
  });

  it("keeps backend protocol codes while removing upstream branding from the public body", async () => {
    studentBackendRequest.mockRejectedValue(
      new BackendApiError(
        503,
        "openmaic_runtime_not_available",
        "暂时无法连接 OpenMAIC 课堂服务",
      ),
    );

    const response = await POST(request(), { params: Promise.resolve({ sessionId: "session-1" }) });
    const body = await response.json();

    expect(response.status).toBe(503);
    expect(body).toMatchObject({
      error: "openmaic_runtime_not_available",
      message: "完整互动课堂暂时没有准备好，请稍后重试。",
    });
    expect(body.message).not.toMatch(/open\s*maic/iu);
  });
});
