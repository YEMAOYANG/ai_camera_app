const LOCAL_LAN_PRODUCTION_FLAG = "MIRA_LOCAL_LAN_PRODUCTION_MODE";
const DEVELOPMENT_RUNTIME_ORIGIN = "http://127.0.0.1:3101";

export const STUDENT_PERMISSIONS_POLICY = "camera=(), microphone=(self), geolocation=()";

function isPrivateIpv4(hostname) {
  const octets = hostname.split(".").map((part) => Number(part));
  if (
    octets.length !== 4
    || octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)
  ) {
    return false;
  }

  return octets[0] === 10
    || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31)
    || (octets[0] === 192 && octets[1] === 168)
    || octets[0] === 127;
}

function isPrivateIpv6(hostname) {
  const normalized = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return normalized === "::1" || normalized.startsWith("fc") || normalized.startsWith("fd");
}

export function isLocalLanHttpOrigin(url) {
  return url.protocol === "http:"
    && !url.username
    && !url.password
    && (isPrivateIpv4(url.hostname) || isPrivateIpv6(url.hostname));
}

export function allowsLocalLanProductionHttp(
  url,
  environment = process.env.NODE_ENV,
  enabled = process.env[LOCAL_LAN_PRODUCTION_FLAG],
) {
  return environment === "production" && enabled === "1" && isLocalLanHttpOrigin(url);
}

export function studentCookiesUseSecureTransport(
  configuredUrl = process.env.MIRA_STUDENT_WEB_PUBLIC_URL,
  environment = process.env.NODE_ENV,
  enabled = process.env[LOCAL_LAN_PRODUCTION_FLAG],
) {
  if (environment !== "production") return false;
  try {
    const url = new URL(configuredUrl?.trim() ?? "");
    return !allowsLocalLanProductionHttp(url, environment, enabled);
  } catch {
    return true;
  }
}

export function resolveOpenMaicRuntimeOrigin(
  configuredUrl = process.env.OPENMAIC_FULL_RUNTIME_PUBLIC_URL,
  environment = process.env.NODE_ENV,
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

function runtimeBrowserOrigins(runtimeOrigin, localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE) {
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
  runtimeOrigin,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
  if (!runtimeOrigin) return STUDENT_PERMISSIONS_POLICY;
  const origins = runtimeBrowserOrigins(runtimeOrigin, localLanProductionMode);
  return `camera=(), microphone=(self ${origins.map((origin) => `"${origin}"`).join(" ")}), geolocation=()`;
}

export function isTrustedOpenMaicLaunchUrl(launchUrl, runtimeOrigin) {
  if (!runtimeOrigin) return false;
  try {
    return new URL(launchUrl).origin === runtimeOrigin;
  } catch {
    return false;
  }
}

export function openMaicLaunchUrlForRequest(
  launchUrl,
  runtimeOrigin,
  requestUrl,
  localLanProductionMode = process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE,
) {
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

export function buildStudentSecurityHeaderRules(options = {}) {
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
        { key: "Permissions-Policy", value: openMaicRuntimePermissionsPolicy(runtimeOrigin, options.localLanProductionMode) },
      ],
    },
  ];
}
