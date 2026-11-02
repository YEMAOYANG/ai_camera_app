import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRawRequest } from "@/lib/auth/student-backend-session";
import { reviewId } from "@/lib/contracts/learning-review";
export async function GET(request: NextRequest, context: { params: Promise<{ reviewId: string; asset: string }> }) {
  const p = await context.params;
  if (!reviewId.safeParse(p.reviewId).success || !/^[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,191}\.(?:wav|mp3|png|jpg|webp)$/.test(p.asset) || p.asset.includes("..") || request.nextUrl.searchParams.size) return new NextResponse(null, { status: 400 });
  try {
    const { response, refreshed } = await studentBackendRawRequest(request, `/api/v2/student/learning/reviews/${encodeURIComponent(p.reviewId)}/media/${encodeURIComponent(p.asset)}`, { cache: "no-store" });
    const mime = response.headers.get("Content-Type")?.split(";", 1)[0];
    const allowed: Record<string, string[]> = { wav: ["audio/wav", "audio/x-wav"], mp3: ["audio/mpeg"], png: ["image/png"], jpg: ["image/jpeg"], webp: ["image/webp"] };
    if (!mime || !allowed[p.asset.split(".").at(-1)!]?.includes(mime)) return new NextResponse(null, { status: 502 });
    return applyRefreshedStudentSession(new NextResponse(response.body, { status: response.status, headers: { "Content-Type": mime, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } }), refreshed);
  } catch (error) { return studentRouteError(error, "图片或声音暂时没准备好，请再试一次"); }
}
