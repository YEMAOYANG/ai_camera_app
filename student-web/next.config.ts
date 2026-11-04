import type { NextConfig } from "next";

// The config is transpiled and loaded directly by Node before the app bundle
// exists. Keep this dependency runtime-JavaScript so ESM resolution is stable.
import { buildStudentSecurityHeaderRules } from "./src/lib/security/openmaic-runtime-policy-runtime.mjs";

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
  async rewrites() {
    return {
      // These compatibility URLs are frozen into published textbook data.
      // Resolve them before public/ so live requests use verified MinIO bytes;
      // the old files remain only as an operator recovery copy.
      beforeFiles: [
        { source: "/textbooks/:path*", destination: "/api/learning/textbooks/assets/textbooks/:path*" },
        { source: "/images/schoolbag/covers-v3/:path*", destination: "/api/learning/textbooks/assets/images/schoolbag/covers-v3/:path*" },
        { source: "/images/storybook/welcome-school-hero.webp", destination: "/api/learning/textbooks/assets/images/storybook/welcome-school-hero.webp" },
        { source: "/images/space/subject-chinese.png", destination: "/api/learning/textbooks/assets/images/space/subject-chinese.png" },
        { source: "/images/space/subject-english.png", destination: "/api/learning/textbooks/assets/images/space/subject-english.png" },
        { source: "/images/space/subject-math-lab.png", destination: "/api/learning/textbooks/assets/images/space/subject-math-lab.png" },
      ],
      afterFiles: [],
      fallback: [],
    };
  },
  async headers() {
    return buildStudentSecurityHeaderRules();
  },
};

export default nextConfig;
