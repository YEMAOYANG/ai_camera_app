import type { Metadata } from "next";
import { StudentSessionGate } from "@/features/auth/student-session-gate";
export const metadata: Metadata = { title: "周末小复习" };
export default async function ReviewPage({ params }: { params: Promise<{ reviewId: string }> }) {
  return <StudentSessionGate learningView="reviews" reviewId={(await params).reviewId} />;
}
