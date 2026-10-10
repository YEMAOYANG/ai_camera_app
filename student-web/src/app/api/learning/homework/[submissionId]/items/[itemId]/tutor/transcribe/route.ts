import { NextRequest } from "next/server";
import { homeworkTutorTranscribeRoute, type HomeworkTutorParams } from "@/lib/api/homework-tutor-route";
export async function POST(request: NextRequest, context: { params: Promise<HomeworkTutorParams> }) { return homeworkTutorTranscribeRoute(request, await context.params); }
export async function GET(request: NextRequest, context: { params: Promise<HomeworkTutorParams> }) { return homeworkTutorTranscribeRoute(request, await context.params); }
