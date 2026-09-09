const LOCAL_LAN_PRODUCTION_FLAG = "MIRA_LOCAL_LAN_PRODUCTION_MODE";

type RuntimeEnvironment = "development" | "test" | "production" | string | undefined;

function isPrivateIpv4(hostname: string) {
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

function isPrivateIpv6(hostname: string) {
  const normalized = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return normalized === "::1" || normalized.startsWith("fc") || normalized.startsWith("fd");
}

export function isLocalLanHttpOrigin(url: URL) {
  return url.protocol === "http:"
    && !url.username
    && !url.password
    && (isPrivateIpv4(url.hostname) || isPrivateIpv6(url.hostname));
}

export function allowsLocalLanProductionHttp(
  url: URL,
  environment: RuntimeEnvironment = process.env.NODE_ENV,
  enabled = process.env[LOCAL_LAN_PRODUCTION_FLAG],
) {
  return environment === "production" && enabled === "1" && isLocalLanHttpOrigin(url);
}

export function studentCookiesUseSecureTransport(
  configuredUrl = process.env.MIRA_STUDENT_WEB_PUBLIC_URL,
  environment: RuntimeEnvironment = process.env.NODE_ENV,
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
