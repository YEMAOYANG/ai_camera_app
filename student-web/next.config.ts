import type { NextConfig } from "next";

import { buildStudentSecurityHeaderRules } from "./src/lib/security/openmaic-runtime-policy";

function configuredDevOrigins() {
  const origins = new Set(["localhost", "127.0.0.1"]);
  const publicUrl = process.env.MIRA_STUDENT_WEB_PUBLIC_URL?.trim();
  if (!publicUrl) return [...origins];
  try {
    const hostname = new URL(publicUrl).hostname;
    if (hostname) origins.add(hostname);
  } catch {
    // Keep the loopback development origins available even when an optional
    // public URL is temporarily invalid. The public URL is validated again by
    // the QR route before it can be embedded in a pairing challenge.
  }
  return [...origins];
}

const nextConfig: NextConfig = {
  poweredByHeader: false,
  allowedDevOrigins: configuredDevOrigins(),
  async headers() {
    return buildStudentSecurityHeaderRules();
  },
};

export default nextConfig;
