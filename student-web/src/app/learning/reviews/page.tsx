import type { Metadata } from "next";
import { StudentSessionGate } from "@/features/auth/student-session-gate";
export const metadata: Metadata = { title: "我的复习" };
export default function ReviewPage() { return <StudentSessionGate learningView="reviews" />; }
