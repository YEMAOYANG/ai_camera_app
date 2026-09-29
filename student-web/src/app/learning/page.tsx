import type { Metadata } from "next";
import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "我的书包" };

export default function LearningPage() {
  return <StudentSessionGate learningView="schoolbag" />;
}
