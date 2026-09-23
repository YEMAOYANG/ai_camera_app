import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { textbookContentsSchema, textbookIdSchema } from "@/lib/contracts/textbooks";

const querySchema = z.object({ alignmentRevisionId: textbookIdSchema }).strict();

export async function GET(request: NextRequest, context: { params: Promise<{ editionId: string }> }) {
  const edition = textbookIdSchema.safeParse((await context.params).editionId);
  const query = querySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!edition.success || !query.success || request.nextUrl.searchParams.size !== 1) {
    return NextResponse.json({ ok: false, error: "textbook_query_invalid", message: "请选择有效的教材版本" }, { status: 400 });
  }
  try {
    const search = new URLSearchParams(query.data);
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/learning/textbooks/${encodeURIComponent(edition.data)}/contents?${search}`, { cache: "no-store" });
    const data = textbookContentsSchema.parse(payload);
    if (data.book.editionId !== edition.data || data.book.revisionId !== query.data.alignmentRevisionId) throw new Error("Textbook response scope mismatch");
    return applyRefreshedStudentSession(NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) {
    return studentRouteError(error, "教材目录暂时没有加载成功，请再试一次");
  }
}
