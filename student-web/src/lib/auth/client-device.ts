import { randomBytes } from "node:crypto";

import type { NextRequest } from "next/server";

import { STUDENT_BROWSER_FINGERPRINT_COOKIE } from "@/lib/auth/cookies";

const fingerprintPattern = /^mfp_[A-Za-z0-9_-]{43}$/;

export function studentClientDevice(request: NextRequest, fingerprint = studentBrowserFingerprint(request).value) {
  const userAgent = request.headers.get("user-agent") || "";
  const osName = parseOsName(userAgent);
  const browserName = parseBrowserName(userAgent);
  const platform = platformForOs(osName);

  return {
    label: `${osName} · ${browserName}`,
    type: "browser",
    platform,
    fingerprint,
    browserName,
    osName,
    model: "",
    hardware: "",
    osVersion: "",
    appVersion: process.env.npm_package_version || "0.1.0",
  };
}

export function studentBrowserFingerprint(request: NextRequest) {
  const existing = request.cookies.get(STUDENT_BROWSER_FINGERPRINT_COOKIE)?.value || "";
  if (fingerprintPattern.test(existing)) return { value: existing, isNew: false };
  return { value: `mfp_${randomBytes(32).toString("base64url")}`, isNew: true };
}

function parseBrowserName(userAgent: string) {
  if (/EdgA?\//i.test(userAgent)) return "Microsoft Edge";
  if (/OPR\//i.test(userAgent)) return "Opera";
  if (/FxiOS\//i.test(userAgent) || /Firefox\//i.test(userAgent)) return "Firefox";
  if (/CriOS\//i.test(userAgent) || /Chrome\//i.test(userAgent)) return "Chrome";
  if (/Safari\//i.test(userAgent) && /Version\//i.test(userAgent)) return "Safari";
  return "浏览器";
}

function parseOsName(userAgent: string) {
  if (/iPad/i.test(userAgent) || (/Macintosh/i.test(userAgent) && /Mobile\//i.test(userAgent))) return "iPadOS";
  if (/iPhone|iPod/i.test(userAgent)) return "iOS";
  if (/Android/i.test(userAgent)) return "Android";
  if (/Windows NT/i.test(userAgent)) return "Windows";
  if (/CrOS/i.test(userAgent)) return "ChromeOS";
  if (/Macintosh|Mac OS X/i.test(userAgent)) return "macOS";
  if (/Linux/i.test(userAgent)) return "Linux";
  return "Web";
}

function platformForOs(osName: string) {
  if (osName === "iOS" || osName === "iPadOS") return "ios-web";
  if (osName === "Android") return "android-web";
  if (osName === "macOS") return "macos-web";
  if (osName === "Windows") return "windows-web";
  if (osName === "ChromeOS") return "chromeos-web";
  if (osName === "Linux") return "linux-web";
  return "web";
}
