import { afterEach, describe, expect, it, vi } from "vitest";

import {
  StudentWebPublicUrlError,
  studentWebPublicOrigin,
} from "@/lib/auth/student-web-public-url";

describe("studentWebPublicOrigin", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("accepts an explicitly enabled private-LAN HTTP origin in the local production stack", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("MIRA_LOCAL_LAN_PRODUCTION_MODE", "1");
    vi.stubEnv("MIRA_STUDENT_WEB_PUBLIC_URL", "http://192.168.228.95:3000");

    expect(studentWebPublicOrigin()).toBe("http://192.168.228.95:3000");
  });

  it("still rejects public or named HTTP origins in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("MIRA_LOCAL_LAN_PRODUCTION_MODE", "1");
    vi.stubEnv("MIRA_STUDENT_WEB_PUBLIC_URL", "http://learn.mira.example:3000");

    expect(() => studentWebPublicOrigin()).toThrow(StudentWebPublicUrlError);
  });

  it("still requires HTTPS when the local production flag is absent", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("MIRA_STUDENT_WEB_PUBLIC_URL", "http://192.168.228.95:3000");

    expect(() => studentWebPublicOrigin()).toThrow("正式环境的学生网页公开地址必须使用 HTTPS");
  });
});
