import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRawRequest } from "@/lib/auth/student-backend-session";
import { reviewId } from "@/lib/contracts/learning-review";
export async function GET(request: NextRequest, context: { params: Promise<{ reviewId: string; asset: string }> }) {
  const p = await context.params;
  if (!reviewId.safeParse(p.reviewId).success || !/^[a-zA-Z0-9_-]+\.wav$/.test(p.asset) || request.nextUrl.searchParams.size) return new NextResponse(null, { status: 400 });
  try {
    const { response, refreshed } = await studentBackendRawRequest(request, `/api/v2/student/learning/reviews/${encodeURIComponent(p.reviewId)}/media/${encodeURIComponent(p.asset)}`, { cache: "no-store" });
    return applyRefreshedStudentSession(new NextResponse(response.body, { status: response.status, headers: { "Content-Type": "audio/wav", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } }), refreshed);
  } catch (error) { return studentRouteError(error, "声音暂时没准备好，请再听一次"); }
}
