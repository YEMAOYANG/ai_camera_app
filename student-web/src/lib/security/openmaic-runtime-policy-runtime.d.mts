export type RuntimeEnvironment = "development" | "test" | "production" | string | undefined;

type SecurityHeader = {
  key: string;
  value: string;
};

export type SecurityHeaderRule = {
  source: string;
  headers: SecurityHeader[];
};

export const STUDENT_PERMISSIONS_POLICY: string;
export function isLocalLanHttpOrigin(url: URL): boolean;
export function allowsLocalLanProductionHttp(url: URL, environment?: RuntimeEnvironment, enabled?: string): boolean;
export function studentCookiesUseSecureTransport(configuredUrl?: string, environment?: RuntimeEnvironment, enabled?: string): boolean;
export function resolveOpenMaicRuntimeOrigin(configuredUrl?: string, environment?: RuntimeEnvironment, localLanProductionMode?: string): string | null;
export function openMaicRuntimePermissionsPolicy(runtimeOrigin: string | null, localLanProductionMode?: string): string;
export function isTrustedOpenMaicLaunchUrl(launchUrl: string, runtimeOrigin: string | null): boolean;
export function openMaicLaunchUrlForRequest(launchUrl: string, runtimeOrigin: string, requestUrl: URL, localLanProductionMode?: string): string | null;
export function buildStudentSecurityHeaderRules(options?: {
  runtimePublicUrl?: string;
  environment?: RuntimeEnvironment;
  localLanProductionMode?: string;
}): SecurityHeaderRule[];
