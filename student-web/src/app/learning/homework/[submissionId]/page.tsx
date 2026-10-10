import { StudentSessionGate } from "@/features/auth/student-session-gate";
export default async function HomeworkPage({ params }: { params: Promise<{ submissionId: string }> }) { return <StudentSessionGate learningView="homework" submissionId={(await params).submissionId} />; }
