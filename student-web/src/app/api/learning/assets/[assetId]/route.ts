import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import {
  applyRefreshedStudentSession,
  studentBackendRawRequest,
} from "@/lib/auth/student-backend-session";

const paramsSchema = z.object({
  assetId: z.string().trim().min(1).max(160).refine((value) => !/[\\/]/.test(value), "素材 ID 不正确"),
});

export async function GET(request: NextRequest, context: { params: Promise<{ assetId: string }> }) {
  const parsed = paramsSchema.safeParse(await context.params);
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "invalid_asset", message: "素材地址不正确" }, { status: 400 });
  }
  try {
    const upstreamHeaders = new Headers({ Accept: request.headers.get("accept") || "*/*" });
    const range = request.headers.get("range");
    const ifNoneMatch = request.headers.get("if-none-match");
    if (range) upstreamHeaders.set("Range", range);
    if (ifNoneMatch) upstreamHeaders.set("If-None-Match", ifNoneMatch);
    const { response: upstream, refreshed } = await studentBackendRawRequest(
      request,
      `/api/v2/student/learning/assets/${encodeURIComponent(parsed.data.assetId)}`,
      { headers: upstreamHeaders },
    );
    const headers = new Headers();
    for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("Cache-Control", "private, max-age=300");
    headers.set("X-Content-Type-Options", "nosniff");
    const response = new NextResponse(upstream.body, { status: upstream.status, headers });
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "课程素材暂时没有准备好");
  }
}
