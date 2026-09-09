import type { Metadata } from "next";

import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "今日学习" };

export default function TodayPage() {
  return <StudentSessionGate />;
}
