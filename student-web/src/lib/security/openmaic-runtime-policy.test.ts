import { describe, expect, it } from "vitest";

import {
  STUDENT_PERMISSIONS_POLICY,
  buildStudentSecurityHeaderRules,
  isTrustedOpenMaicLaunchUrl,
  openMaicLaunchUrlForRequest,
  resolveOpenMaicRuntimeOrigin,
} from "@/lib/security/openmaic-runtime-policy";

function permissionsPolicy(rule: ReturnType<typeof buildStudentSecurityHeaderRules>[number]) {
  return rule.headers.find((header) => header.key === "Permissions-Policy")?.value;
}

describe("Student document Permissions-Policy", () => {
  it("keeps a route-independent policy for SPA recording and the exact classroom origin", () => {
    const rules = buildStudentSecurityHeaderRules({
      runtimePublicUrl: "https://classroom.mira.test/runtime/path",
      environment: "production",
    });
    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/(.*)");
    expect(permissionsPolicy(rules[0])).toBe(
      'camera=(), microphone=(self "https://classroom.mira.test"), geolocation=()',
    );
    expect(permissionsPolicy(rules[0])).not.toContain("*");
    expect(rules[0].headers).toContainEqual({ key: "X-Frame-Options", value: "DENY" });
  });

  it("keeps same-origin recording while refusing missing, insecure or invalid runtime delegation", () => {
    for (const runtimePublicUrl of ["", "http://classroom.mira.test", "not a URL", "https://user:password@classroom.mira.test"]) {
      expect(resolveOpenMaicRuntimeOrigin(runtimePublicUrl, "production")).toBeNull();
      const rules = buildStudentSecurityHeaderRules({ runtimePublicUrl, environment: "production" });
      expect(permissionsPolicy(rules[0])).toBe(STUDENT_PERMISSIONS_POLICY);
      expect(permissionsPolicy(rules[0])).toBe("camera=(), microphone=(self), geolocation=()");
    }
  });

  it("delegates private-LAN HTTP classroom origins only with explicit local production mode", () => {
    expect(resolveOpenMaicRuntimeOrigin(
      "http://192.168.228.95:3101", "production", "1",
    )).toBe("http://192.168.228.95:3101");
    expect(resolveOpenMaicRuntimeOrigin(
      "http://classroom.example:3101", "production", "1",
    )).toBeNull();
    const rules = buildStudentSecurityHeaderRules({
      runtimePublicUrl: "http://192.168.228.95:3101",
      environment: "production",
      localLanProductionMode: "1",
    });
    expect(permissionsPolicy(rules[0])).toBe(
      'camera=(), microphone=(self "http://192.168.228.95:3101" "http://localhost:3101" "http://127.0.0.1:3101"), geolocation=()',
    );
  });

  it("keeps local launch cookies on the student hostname without allowing arbitrary destinations", () => {
    const origin = "http://192.168.228.95:3101";
    const launch = `${origin}/mira/launch?ticket=one-time`;
    for (const hostname of ["localhost", "127.0.0.1", "192.168.228.95"]) {
      expect(openMaicLaunchUrlForRequest(launch, origin, new URL(`http://${hostname}:3000`), "1"))
        .toBe(`http://${hostname}:3101/mira/launch?ticket=one-time`);
    }
    for (const request of ["http://attacker.example:3000", "http://192.168.228.96:3000", "https://localhost:3000"]) {
      expect(openMaicLaunchUrlForRequest(launch, origin, new URL(request), "1")).toBe(launch);
    }
    expect(openMaicLaunchUrlForRequest(launch, origin, new URL("http://localhost:3000"), "0")).toBe(launch);
    expect(openMaicLaunchUrlForRequest("https://attacker.example/mira/launch", origin, new URL("http://localhost:3000"), "1")).toBeNull();
    const secureLaunch = "https://classroom.mira.test/mira/launch?ticket=one-time";
    expect(openMaicLaunchUrlForRequest(secureLaunch, "https://classroom.mira.test", new URL("http://localhost:3000"), "1"))
      .toBe(secureLaunch);
  });

  it("accepts launch tickets only from the exact configured runtime origin", () => {
    const runtimeOrigin = resolveOpenMaicRuntimeOrigin(
      "https://classroom.mira.test",
      "production",
    );
    expect(isTrustedOpenMaicLaunchUrl(
      "https://classroom.mira.test/mira/launch?ticket=one-time",
      runtimeOrigin,
    )).toBe(true);
    expect(isTrustedOpenMaicLaunchUrl(
      "https://classroom.mira.test.attacker.example/mira/launch?ticket=one-time",
      runtimeOrigin,
    )).toBe(false);
  });
});
