import { createHash } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { textbookLaunchSchema } from "@/lib/contracts/textbooks";
import { openMaicLaunchUrlForRequest, resolveOpenMaicRuntimeOrigin } from "@/lib/security/openmaic-runtime-policy";

const classroomPath = /^\/classroom\/(tbpub_[a-f0-9]{24})$/;
const runtimeToken = /^tbpr_[A-Za-z0-9._~-]{1,512}$/;

function setCookies(headers: Headers) {
  const extended = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof extended.getSetCookie === "function") return extended.getSetCookie();
  const combined = headers.get("set-cookie");
  if (!combined) return [];
  // A comma inside Expires is not followed by a cookie-name assignment.
  return combined.split(/,(?=\s*[!#$%&'*+.^_`|~0-9A-Za-z-]+=)/).map(value => value.trim());
}

function verifiedRuntimeCookies(headers: Headers, classroomId: string, secure: boolean) {
  const scoped = `mira_openmaic_runtime_classroom_${createHash("sha256")
    .update(classroomId).digest("hex").slice(0, 32)}`;
  const expected = new Set(["mira_openmaic_runtime", scoped]);
  const found = new Map<string, { raw: string; value: string }>();
  for (const raw of setCookies(headers)) {
    const pieces = raw.split(";").map(value => value.trim());
    const separator = pieces[0].indexOf("=");
    if (separator <= 0) throw new Error("课堂凭证未通过检查");
    const name = pieces[0].slice(0, separator);
    const value = pieces[0].slice(separator + 1);
    if (!expected.has(name) || found.has(name) || !runtimeToken.test(value))
      throw new Error("课堂凭证未通过检查");
    const attributes = new Map<string, string>();
    const flags = new Set<string>();
    for (const piece of pieces.slice(1)) {
      const index = piece.indexOf("=");
      if (index < 0) flags.add(piece.toLowerCase());
      else attributes.set(piece.slice(0, index).toLowerCase(), piece.slice(index + 1).toLowerCase());
    }
    const age = Number(attributes.get("max-age"));
    if (attributes.get("path") !== "/" || attributes.get("samesite") !== "lax"
        || !flags.has("httponly") || flags.has("partitioned") || attributes.has("domain")
        || !Number.isInteger(age) || age < 1 || age > 3600
        || (secure ? !flags.has("secure") : flags.has("secure")))
      throw new Error("课堂凭证未通过检查");
    found.set(name, { raw: `${name}=${value}; Path=/; HttpOnly; SameSite=lax; Max-Age=${age}${secure ? "; Secure" : ""}`, value });
  }
  if (found.size !== 2 || found.get("mira_openmaic_runtime")?.value !== found.get(scoped)?.value)
    throw new Error("课堂凭证未通过检查");
  return [...found.values()].map(item => item.raw);
}

async function exchangeLocalLaunch(data: { launchUrl: string }, browserLaunchUrl: string) {
  const exchanged = await fetch(data.launchUrl, { method: "GET", redirect: "manual", cache: "no-store" });
  if (exchanged.status !== 303) throw new Error("课堂启动未通过检查");
  const location = exchanged.headers.get("location");
  if (!location) throw new Error("课堂启动未通过检查");
  const upstream = new URL(location, data.launchUrl);
  const match = classroomPath.exec(upstream.pathname);
  if (upstream.origin !== new URL(data.launchUrl).origin || upstream.username || upstream.password
      || upstream.hash || !match || upstream.searchParams.size !== 2
      || upstream.searchParams.get("mira") !== "1" || upstream.searchParams.get("textbook") !== "1")
    throw new Error("课堂启动未通过检查");
  const launch = new URL(browserLaunchUrl);
  launch.pathname = upstream.pathname;
  launch.search = upstream.search;
  launch.hash = "";
  return { launchUrl: launch.toString(), cookies: verifiedRuntimeCookies(
    exchanged.headers, match[1], launch.protocol === "https:") };
}

export async function POST(request: NextRequest, context: { params: Promise<{ contentKey: string }> }) {
  const { contentKey } = await context.params;
  if (!/^[a-f0-9]{64}$/.test(contentKey) || request.nextUrl.searchParams.size)
    return NextResponse.json({ ok: false, error: "textbook_query_invalid", message: "课程地址无效" }, { status: 400 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request,
      `/api/v2/student/learning/textbooks/courses/${contentKey}/launch`, { method: "POST", body: "{}" });
    const data = textbookLaunchSchema.parse(payload);
    const origin = resolveOpenMaicRuntimeOrigin();
    if (!origin || data.contentKey !== contentKey || new URL(data.launchUrl).pathname !== "/mira/textbook-launch")
      throw new Error("课堂地址未通过检查");
    const browserUrl = new URL(request.nextUrl);
    browserUrl.host = request.headers.get("host") || browserUrl.host;
    const launchUrl = openMaicLaunchUrlForRequest(data.launchUrl, origin, browserUrl);
    if (!launchUrl) throw new Error("课堂地址未通过检查");
    const browserLaunch = new URL(launchUrl);
    const sameHost = browserLaunch.hostname === browserUrl.hostname && browserLaunch.protocol === browserUrl.protocol;
    if (!sameHost) return applyRefreshedStudentSession(NextResponse.json({ ...data, launchUrl },
      { headers: { "Cache-Control": "private, no-store" } }), refreshed);
    const exchanged = await exchangeLocalLaunch(data, launchUrl);
    const response = NextResponse.json({ ...data, launchUrl: exchanged.launchUrl },
      { headers: { "Cache-Control": "private, no-store" } });
    for (const cookie of exchanged.cookies) response.headers.append("Set-Cookie", cookie);
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "课堂暂时打不开，请返回教材目录再试");
  }
}
