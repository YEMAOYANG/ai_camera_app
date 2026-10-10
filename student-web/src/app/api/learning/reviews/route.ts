import { NextRequest } from "next/server";
import { reviewRoute } from "@/lib/api/review-route";
export async function GET(request: NextRequest) { return reviewRoute(request); }
