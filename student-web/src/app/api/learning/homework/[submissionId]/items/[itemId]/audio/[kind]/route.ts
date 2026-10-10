import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRawRequest } from "@/lib/auth/student-backend-session";
import { homeworkIdSchema, homeworkItemIdSchema } from "@/lib/contracts/homework";
export async function GET(request: NextRequest, context: { params: Promise<{ submissionId: string; itemId: string; kind: string }> }) {
  const p = await context.params;
  if (request.nextUrl.searchParams.size || !homeworkIdSchema.safeParse(p.submissionId).success || !homeworkItemIdSchema.safeParse(p.itemId).success || !["prompt", "hint", "explanation", "success", "retry"].includes(p.kind)) return new NextResponse(null, { status: 400 });
  try {
    const { response, refreshed } = await studentBackendRawRequest(request, `/api/v2/student/learning/homework/${p.submissionId}/items/${p.itemId}/audio/${p.kind}`, { cache: "no-store" });
    const contentType = response.headers.get("content-type") || "audio/wav";
    if (!/^audio\/(wav|mpeg|x-wav)(;|$)/i.test(contentType)) return new NextResponse(null, { status: 502 });
    return applyRefreshedStudentSession(new NextResponse(response.body, { status: response.status, headers: { "Content-Type": contentType, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } }), refreshed);
  } catch (error) { return studentRouteError(error, "声音暂时没准备好，请再听一次"); }
}
