import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRawRequest } from "@/lib/auth/student-backend-session";
import { homeworkIdSchema, homeworkPageIdSchema } from "@/lib/contracts/homework";

const privateHeaders = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
const imageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);

export async function GET(request: NextRequest, context: { params: Promise<{ submissionId: string; pageId: string }> }) {
  const params = await context.params;
  if (request.nextUrl.searchParams.size || !homeworkIdSchema.safeParse(params.submissionId).success || !homeworkPageIdSchema.safeParse(params.pageId).success) {
    return new NextResponse(null, { status: 400, headers: privateHeaders });
  }
  try {
    const { response, refreshed } = await studentBackendRawRequest(
      request,
      `/api/v2/student/learning/homework/${params.submissionId}/pages/${params.pageId}/image`,
      { cache: "no-store" },
    );
    const contentType = response.headers.get("content-type") || "";
    const mimeType = contentType.split(";", 1)[0].trim().toLowerCase();
    if (!imageTypes.has(mimeType)) {
      return applyRefreshedStudentSession(new NextResponse(null, { status: 502, headers: privateHeaders }), refreshed);
    }
    return applyRefreshedStudentSession(new NextResponse(response.body, {
      status: response.status,
      headers: { ...privateHeaders, "Content-Type": contentType },
    }), refreshed);
  } catch (error) {
    const response = studentRouteError(error, "作业照片暂时没有打开，请再试一次");
    for (const [name, value] of Object.entries(privateHeaders)) response.headers.set(name, value);
    return response;
  }
}
