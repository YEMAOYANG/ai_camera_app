import { NextRequest } from "next/server";
import { homeworkRoute } from "@/lib/api/homework-route";
export async function POST(request: NextRequest, context: { params: Promise<{ submissionId: string; itemId: string }> }) { const p = await context.params; return homeworkRoute(request, p.submissionId, p.itemId, "actions"); }
