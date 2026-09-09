import { type NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { studentRouteError } from "@/lib/api/route-response";
import {
  applyRefreshedStudentSession,
  studentBackendRequest,
} from "@/lib/auth/student-backend-session";
import { openMaicFormalRuntimeLaunchSchema } from "@/lib/contracts/openmaic-runtime";
import {
  isTrustedOpenMaicLaunchUrl,
  openMaicLaunchUrlForRequest,
  resolveOpenMaicRuntimeOrigin,
} from "@/lib/security/openmaic-runtime-policy";

const CLASSROOM_ERROR_FALLBACK = "完整互动课堂暂时没有准备好，请稍后重试。";

function studentFacingClassroomError(error: unknown) {
  if (error instanceof BackendApiError && /open\s*maic/iu.test(error.message)) {
    return new BackendApiError(error.status, error.code, CLASSROOM_ERROR_FALLBACK);
  }
  return error;
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/sessions/${encodeURIComponent(sessionId)}/openmaic-launch`,
      { method: "POST", body: JSON.stringify({}) },
    );
    const parsed = openMaicFormalRuntimeLaunchSchema.safeParse(payload);
    if (!parsed.success) {
      throw new BackendApiError(
        502,
        "openmaic_runtime_contract_invalid",
        "课堂暂时无法打开，请稍后重试；若仍无法打开，请联系管理员。",
      );
    }
    const launch = parsed.data;
    const runtimeOrigin = resolveOpenMaicRuntimeOrigin();
    if (!runtimeOrigin) {
      throw new BackendApiError(
        503,
        "openmaic_runtime_origin_not_configured",
        "完整课堂的麦克风安全域名尚未配置，请让家长或管理员完成课堂运行地址配置。",
      );
    }
    if (!isTrustedOpenMaicLaunchUrl(launch.launchUrl, runtimeOrigin)) {
      throw new BackendApiError(
        502,
        "openmaic_runtime_origin_untrusted",
        "课堂返回的运行地址未通过安全检查，已阻止打开。请让管理员核对课堂运行地址配置。",
      );
    }
    // Next's production server can normalize nextUrl to its listen address
    // (0.0.0.0). Retain the browser Host, then apply only the fixed alias list.
    const browserUrl = new URL(request.nextUrl);
    browserUrl.host = request.headers.get("host") || browserUrl.host;
    const launchUrl = openMaicLaunchUrlForRequest(launch.launchUrl, runtimeOrigin, browserUrl);
    const response = NextResponse.json({ ...launch, launchUrl });
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(
      studentFacingClassroomError(error),
      "完整互动课堂暂时打不开",
    );
  }
}
