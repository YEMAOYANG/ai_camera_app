import { NextRequest } from "next/server";
import { homeworkTutorRoute, type HomeworkTutorParams } from "@/lib/api/homework-tutor-route";
export async function GET(request: NextRequest, context: { params: Promise<HomeworkTutorParams> }) { return homeworkTutorRoute(request, await context.params); }
export async function POST(request: NextRequest, context: { params: Promise<HomeworkTutorParams> }) { return homeworkTutorRoute(request, await context.params); }
