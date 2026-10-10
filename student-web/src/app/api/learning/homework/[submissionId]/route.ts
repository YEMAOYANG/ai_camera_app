import { NextRequest } from "next/server";
import { homeworkRoute } from "@/lib/api/homework-route";
export async function GET(request: NextRequest, context: { params: Promise<{ submissionId: string }> }) { return homeworkRoute(request, (await context.params).submissionId); }
