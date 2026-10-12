import type { Metadata } from "next";
import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "国际教材测试" };

export default function InternationalLearningPage() {
  return <StudentSessionGate learningView="international" />;
}
