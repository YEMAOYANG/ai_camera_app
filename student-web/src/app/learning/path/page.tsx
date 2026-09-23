import type { Metadata } from "next";

import { StudentSessionGate } from "@/features/auth/student-session-gate";
import "@/styles/space-learning-path.css";

export const metadata: Metadata = { title: "我的学习路线" };

export default function LearningPathPage() {
  return <StudentSessionGate learningView="path" />;
}
