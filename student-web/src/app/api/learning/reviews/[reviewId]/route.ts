import { NextRequest } from "next/server";
import { reviewRoute } from "@/lib/api/review-route";
export async function GET(request: NextRequest, context: { params: Promise<{ reviewId: string }> }) {
  return reviewRoute(request, (await context.params).reviewId);
}
