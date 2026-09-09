import { allowsLocalLanProductionHttp, isLocalLanHttpOrigin } from "./local-lan-production";

const DEVELOPMENT_RUNTIME_ORIGIN = "http://127.0.0.1:3101";

export const OPENMAIC_RUNTIME_HEADER_SOURCE = "/lesson/:taskId/classroom";
export const BLOCKED_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()";

type RuntimeEnvironment = "development" | "test" | "production" | string | undefined;

type SecurityHeader = {
  key: string;
  value: string;
};

export type SecurityHeaderRule = {
  source: string;
  headers: SecurityHeader[];
};

export function resolveOpenMaicRuntimeOrigin(
  configuredUrl = process.env.OPENMAIC_FULL_RUNTIME_PUBLIC_URL,
  environment: RuntimeEnvironment = process.env.NODE_ENV,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
  const candidate = configuredUrl?.trim()
    || (environment === "development" ? DEVELOPMENT_RUNTIME_ORIGIN : "");
  if (!candidate) return null;

  try {
    const url = new URL(candidate);
    if (url.username || url.password) return null;
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (
      environment === "production"
      && url.protocol !== "https:"
      && !allowsLocalLanProductionHttp(url, environment, localLanProductionMode)
    ) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function runtimeBrowserOrigins(
  runtimeOrigin: string,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
  const origins = new Set([runtimeOrigin]);
  const configured = new URL(runtimeOrigin);
  if (localLanProductionMode === "1" && isLocalLanHttpOrigin(configured)) {
    for (const hostname of ["localhost", "127.0.0.1"]) {
      const alias = new URL(configured);
      alias.hostname = hostname;
      origins.add(alias.origin);
    }
  }
  return [...origins];
}

export function openMaicRuntimePermissionsPolicy(
  runtimeOrigin: string | null,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
  if (!runtimeOrigin) return BLOCKED_PERMISSIONS_POLICY;
  const origins = runtimeBrowserOrigins(runtimeOrigin, localLanProductionMode);
  return `camera=(), microphone=(self ${origins.map((origin) => `"${origin}"`).join(" ")}), geolocation=()`;
}

export function isTrustedOpenMaicLaunchUrl(launchUrl: string, runtimeOrigin: string | null) {
  if (!runtimeOrigin) return false;
  try {
    return new URL(launchUrl).origin === runtimeOrigin;
  } catch {
    return false;
  }
}

export function openMaicLaunchUrlForRequest(
  launchUrl: string,
  runtimeOrigin: string,
  requestUrl: URL,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
  // Validate the backend destination before applying the bounded local aliases.
  // The request can select a fixed alias, never add an arbitrary destination.
  if (!isTrustedOpenMaicLaunchUrl(launchUrl, runtimeOrigin)) return null;
  const matchingOrigin = runtimeBrowserOrigins(runtimeOrigin, localLanProductionMode)
    .find((origin) => {
      const candidate = new URL(origin);
      return candidate.hostname === requestUrl.hostname && candidate.protocol === requestUrl.protocol;
    });
  if (!matchingOrigin) return launchUrl;
  const result = new URL(launchUrl);
  result.host = new URL(matchingOrigin).host;
  return result.toString();
}

export function buildStudentSecurityHeaderRules(options: {
  runtimePublicUrl?: string;
  environment?: RuntimeEnvironment;
  localLanProductionMode?: string;
} = {}): SecurityHeaderRule[] {
  const runtimeOrigin = resolveOpenMaicRuntimeOrigin(
    options.runtimePublicUrl,
    options.environment,
    options.localLanProductionMode,
  );

  return [
    {
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: BLOCKED_PERMISSIONS_POLICY },
      ],
    },
    {
      // This rule must remain after the global rule. Next applies the last
      // matching value when two header rules set the same header.
      source: OPENMAIC_RUNTIME_HEADER_SOURCE,
      headers: [
        {
          key: "Permissions-Policy",
          value: openMaicRuntimePermissionsPolicy(runtimeOrigin, options.localLanProductionMode),
        },
      ],
    },
  ];
}
