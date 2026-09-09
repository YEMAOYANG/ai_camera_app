import { describe, expect, it } from "vitest";

import {
  allowsLocalLanProductionHttp,
  isLocalLanHttpOrigin,
  studentCookiesUseSecureTransport,
} from "@/lib/security/local-lan-production";

describe("explicit local-LAN production mode", () => {
  it("allows only an explicitly enabled private IP over HTTP", () => {
    expect(allowsLocalLanProductionHttp(
      new URL("http://192.168.228.95:3000"),
      "production",
      "1",
    )).toBe(true);
    expect(allowsLocalLanProductionHttp(
      new URL("http://10.0.0.8:3000"),
      "production",
      "1",
    )).toBe(true);
    expect(allowsLocalLanProductionHttp(
      new URL("http://172.31.5.4:3000"),
      "production",
      "1",
    )).toBe(true);
  });

  it("fails closed for public hosts, DNS names, disabled flags, and credentials", () => {
    expect(isLocalLanHttpOrigin(new URL("http://8.8.8.8:3000"))).toBe(false);
    expect(isLocalLanHttpOrigin(new URL("http://classroom.example:3000"))).toBe(false);
    expect(isLocalLanHttpOrigin(new URL("http://user:pass@192.168.1.2:3000"))).toBe(false);
    expect(allowsLocalLanProductionHttp(
      new URL("http://192.168.1.2:3000"),
      "production",
      "0",
    )).toBe(false);
    expect(allowsLocalLanProductionHttp(
      new URL("http://192.168.1.2:3000"),
      "development",
      "1",
    )).toBe(false);
  });

  it("keeps cookies Secure except for the exact explicit private-LAN mode", () => {
    expect(studentCookiesUseSecureTransport(
      "http://192.168.228.95:3000",
      "production",
      "1",
    )).toBe(false);
    expect(studentCookiesUseSecureTransport(
      "http://public.example:3000",
      "production",
      "1",
    )).toBe(true);
    expect(studentCookiesUseSecureTransport(
      "https://learn.mira.example",
      "production",
      "1",
    )).toBe(true);
    expect(studentCookiesUseSecureTransport(undefined, "production", "1")).toBe(true);
  });
});
