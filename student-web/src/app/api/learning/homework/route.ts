import { NextRequest } from "next/server";
import { homeworkRoute } from "@/lib/api/homework-route";
export async function GET(request: NextRequest) { return homeworkRoute(request); }
