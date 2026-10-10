import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRawRequest, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { homeworkIdSchema, homeworkItemIdSchema } from "@/lib/contracts/homework";
import { homeworkTranscriptionSchema, homeworkTutorRequestSchema, homeworkTutorResponseSchema, homeworkTutorTurnIdSchema } from "@/lib/contracts/homework-tutor";

export type HomeworkTutorParams = { submissionId: string; itemId: string };
function valid(request: NextRequest, params: HomeworkTutorParams) {
  return !request.nextUrl.searchParams.size && homeworkIdSchema.safeParse(params.submissionId).success && homeworkItemIdSchema.safeParse(params.itemId).success;
}
const backendPath = (p: HomeworkTutorParams) => `/api/v2/student/learning/homework/${p.submissionId}/items/${p.itemId}/tutor`;
const privateHeaders = { "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" };
export async function homeworkTutorRoute(request: NextRequest, p: HomeworkTutorParams) {
  if (!valid(request, p)) return NextResponse.json({ ok: false, message: "请重新打开原题" }, { status: 400 });
  let body: string | undefined;
  if (request.method === "POST") {
    if (Number(request.headers.get("content-length") ?? 0) > 8192) return NextResponse.json({ ok: false, message: "问题太长了，请说短一点" }, { status: 413 });
    const parsed = homeworkTutorRequestSchema.safeParse(await request.json().catch(() => null));
    if (!parsed.success) return NextResponse.json({ ok: false, message: "请重新打开原题，再问老师" }, { status: 400 });
    body = JSON.stringify(parsed.data);
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(request, backendPath(p), { method: body ? "POST" : "GET", ...(body ? { body } : {}), cache: "no-store" });
    const parsed = homeworkTutorResponseSchema.parse(payload);
    if (parsed.tutor.itemId !== p.itemId) return NextResponse.json({ ok: false, message: "原题已更新，请重新打开" }, { status: 502 });
    return applyRefreshedStudentSession(NextResponse.json(parsed, { status: body ? 202 : 200, headers: privateHeaders }), refreshed);
  } catch (error) { return studentRouteError(error, "老师暂时没连接上，请先查看准备情况"); }
}
export async function homeworkTutorAudioRoute(request: NextRequest, p: HomeworkTutorParams & { turnId: string }) {
  if (!valid(request, p) || !homeworkTutorTurnIdSchema.safeParse(p.turnId).success) return new NextResponse(null, { status: 400 });
  try {
    if (request.method === "POST") {
      const raw = await request.json().catch(() => null);
      if (!raw || typeof raw !== "object" || Object.keys(raw).some(key => !["itemRevision", "idempotencyKey"].includes(key)) || !Number.isInteger(raw.itemRevision) || raw.itemRevision < 1 || typeof raw.idempotencyKey !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(raw.idempotencyKey)) return NextResponse.json({ ok: false, message: "请重新打开老师讲解" }, { status: 400 });
      const { payload, refreshed } = await studentBackendRequest(request, `${backendPath(p)}/${p.turnId}/audio`, { method: "POST", body: JSON.stringify(raw), cache: "no-store" });
      return applyRefreshedStudentSession(NextResponse.json(homeworkTutorResponseSchema.parse(payload), { status: 202, headers: privateHeaders }), refreshed);
    }
    const { response, refreshed } = await studentBackendRawRequest(request, `${backendPath(p)}/${p.turnId}/audio`, { cache: "no-store" });
    const contentType = response.headers.get("content-type") ?? "audio/wav";
    if (!/^audio\/(wav|mpeg|x-wav)(;|$)/i.test(contentType)) return new NextResponse(null, { status: 502 });
    return applyRefreshedStudentSession(new NextResponse(response.body, { status: response.status, headers: { ...privateHeaders, "Content-Type": contentType } }), refreshed);
  } catch (error) { return studentRouteError(error, "老师的声音暂时没打开，请再听一次"); }
}
export async function homeworkTutorTranscribeRoute(request: NextRequest, p: HomeworkTutorParams) {
  if (!homeworkIdSchema.safeParse(p.submissionId).success || !homeworkItemIdSchema.safeParse(p.itemId).success) return NextResponse.json({ ok: false, message: "请重新打开原题" }, { status: 400 });
  if (request.method === "GET") {
    const revision = request.nextUrl.searchParams.get("itemRevision"), key = request.nextUrl.searchParams.get("idempotencyKey");
    if (request.nextUrl.searchParams.size !== 2 || !revision || !/^[1-9][0-9]{0,8}$/.test(revision) || !key || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(key)) return NextResponse.json({ ok: false, message: "录音查询无效" }, { status: 400 });
    try {
      const { payload, refreshed } = await studentBackendRequest(request, `${backendPath(p)}/transcribe?${new URLSearchParams({ itemRevision: revision, idempotencyKey: key })}`, { cache: "no-store" });
      return applyRefreshedStudentSession(NextResponse.json(homeworkTranscriptionSchema.parse(payload), { headers: privateHeaders }), refreshed);
    } catch (error) { return studentRouteError(error, "正在核实这段录音，请稍后查看"); }
  }
  if (request.nextUrl.searchParams.size) return NextResponse.json({ ok: false, message: "录音请求无效" }, { status: 400 });
  const maxBytes = 2 * 1024 * 1024;
  if (Number(request.headers.get("content-length") ?? 0) > maxBytes + 8192) return NextResponse.json({ ok: false, message: "录音太长了，请控制在一分钟内" }, { status: 413 });
  try {
    const form = await request.formData();
    const audio = form.get("audio"), revision = form.get("itemRevision"), key = form.get("idempotencyKey");
    if (Array.from(form.keys()).some(name => !["audio", "itemRevision", "idempotencyKey"].includes(name)) || !(audio instanceof File) || audio.size <= 44 || audio.size > maxBytes || !/^audio\/(wav|x-wav)(;|$)/i.test(audio.type) || typeof revision !== "string" || !/^[1-9][0-9]{0,8}$/.test(revision) || typeof key !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(key)) return NextResponse.json({ ok: false, message: "录音没有保存好，请重新录一小段" }, { status: 400 });
    const { response, refreshed } = await studentBackendRawRequest(request, `${backendPath(p)}/transcribe`, { method: "POST", body: form, cache: "no-store" });
    return applyRefreshedStudentSession(NextResponse.json(homeworkTranscriptionSchema.parse(await response.json()), { headers: privateHeaders }), refreshed);
  } catch (error) { return studentRouteError(error, "这段话还没听清，请查看录音状态"); }
}
