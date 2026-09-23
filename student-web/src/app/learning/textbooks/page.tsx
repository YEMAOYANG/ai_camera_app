import { StudentSessionGate } from "@/features/auth/student-session-gate";
import "@/styles/space-textbooks.css";

export default function TextbooksPage() {
  return <StudentSessionGate learningView="textbooks" />;
}
