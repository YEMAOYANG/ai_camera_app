import type { LearningLibraryItem, LearningProgression } from "@/lib/contracts/learning";

export function learningProgressionLocked(progression?: LearningProgression) {
  return progression?.canStart === false || progression?.learningStatus === "locked";
}

export function learningProgressionCanResume(item: LearningLibraryItem) {
  return item.progression?.canResume === true && Boolean(item.taskId && item.session?.id)
    && item.session?.status === "in_progress" && item.taskStatus !== "completed";
}

export function learningProgressionMessage(progression: LearningProgression) {
  if (progression.message.trim()) return progression.message;
  if (learningProgressionLocked(progression)) return "先学好前面的知识，再来学习这一节。";
  if (progression.learningStatus === "needs_practice") return "这个知识点还需要巩固，先把基础练熟。";
  if (progression.learningStatus === "mastered") return "这个知识点已经掌握。";
  return "前面的基础已准备好，可以开始学习。";
}

export function LearningProgressionNote({ progression }: { progression?: LearningProgression }) {
  if (!progression) return null;
  return (
    <p className="space-course-readiness space-course-progression">
      {progression.sequence > 0 ? `知识点学习顺序 ${progression.sequence} · ` : ""}
      {learningProgressionMessage(progression)}
    </p>
  );
}
