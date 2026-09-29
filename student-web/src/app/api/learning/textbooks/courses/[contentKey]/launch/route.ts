import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { textbookLaunchSchema } from "@/lib/contracts/textbooks";
import { openMaicLaunchUrlForRequest, resolveOpenMaicRuntimeOrigin } from "@/lib/security/openmaic-runtime-policy";

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
    return applyRefreshedStudentSession(NextResponse.json({ ...data, launchUrl },
      { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) {
    return studentRouteError(error, "课堂暂时打不开，请返回教材目录再试");
  }
}
