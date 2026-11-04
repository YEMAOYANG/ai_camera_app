import { NextRequest, NextResponse } from "next/server";

import { backendRawRequest } from "@/lib/api/server";

type Context = { params: Promise<{ path: string[] }> };

function validPath(parts: string[]) {
  return parts.length > 1 && parts.length <= 12 && parts.every(part =>
    part.length > 0 && part.length <= 255 && part !== "." && part !== ".."
    && !/[\\\u0000-\u001f\u007f]/.test(part),
  );
}

export async function GET(request: NextRequest, context: Context) {
  const { path } = await context.params;
  if (request.nextUrl.searchParams.size || !Array.isArray(path) || !validPath(path)) {
    return NextResponse.json(
      { ok: false, error: "courseware_asset_request_invalid", message: "课件资源请求无效" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const assetPath = path.map(encodeURIComponent).join("/");
    const upstream = await backendRawRequest(`/api/v2/student/learning/textbooks/assets/${assetPath}`, {
      headers: { Accept: request.headers.get("accept") || "*/*" },
    });
    if (!upstream.ok || !upstream.body) {
      const payload = await upstream.json().catch(() => ({}));
      return NextResponse.json(payload, {
        status: upstream.status,
        headers: { "Cache-Control": upstream.status === 404 ? "public, max-age=60" : "no-store" },
      });
    }
    const headers = new Headers();
    for (const name of ["content-type", "content-length", "cache-control", "etag", "x-mira-file-sha256", "x-mira-file-source", "x-content-type-options"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new NextResponse(upstream.body, { status: 200, headers });
  } catch {
    return NextResponse.json(
      { ok: false, error: "courseware_asset_unavailable", message: "课件资源暂时不可用" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
