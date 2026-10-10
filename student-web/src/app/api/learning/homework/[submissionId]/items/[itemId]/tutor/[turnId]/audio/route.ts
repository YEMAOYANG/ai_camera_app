import { NextRequest } from "next/server";
import { homeworkTutorAudioRoute, type HomeworkTutorParams } from "@/lib/api/homework-tutor-route";
export async function GET(request: NextRequest, context: { params: Promise<HomeworkTutorParams & { turnId: string }> }) { return homeworkTutorAudioRoute(request, await context.params); }
export async function POST(request: NextRequest, context: { params: Promise<HomeworkTutorParams & { turnId: string }> }) { return homeworkTutorAudioRoute(request, await context.params); }
