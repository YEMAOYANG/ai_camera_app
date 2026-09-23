import type { LearningLibraryItem } from "@/lib/contracts/learning";
import { learningProgressionCanResume, learningProgressionLocked } from "./learning-progression";

export type LearningLibraryGroup = {
  key: string;
  item: LearningLibraryItem;
  items: LearningLibraryItem[];
  exerciseSetCount: number;
  completedExerciseSetCount: number;
  historyCount: number;
};

export function learningLibraryGroupKey(item: LearningLibraryItem) {
  const { course, progression } = item;
  // A title or coarse skill can describe several different lessons. Only
  // the server's exact versioned lesson identity permits cross-course grouping.
  return progression?.granularity === "lesson" && progression.lessonId
    ? JSON.stringify(["lesson", course.gradeCode, course.subject, progression.curriculumVersion, progression.lessonId])
    : JSON.stringify(["course", course.id, course.version]);
}

export function learningLibraryCourseKey(item: LearningLibraryItem) {
  return JSON.stringify([item.course.id, item.course.version]);
}

function priority(item: LearningLibraryItem) {
  const completed = Boolean(item.report || item.session?.status === "completed" || item.taskStatus === "completed");
  const allowed = !learningProgressionLocked(item.progression);
  if (!completed && item.fullClassroomAvailable && (learningProgressionCanResume(item)
    || (allowed && item.taskId && item.session?.status === "in_progress"))) return 0;
  if (!completed && allowed && item.fullClassroomAvailable) return item.taskId ? 1 : 2;
  if (!completed && allowed) return 3;
  return completed ? 4 : 5;
}

function compareAttempts(a: LearningLibraryItem, b: LearningLibraryItem) {
  // A resumed older task can be the most recently updated record. Only the
  // immutable start time determines the latest actual learning attempt.
  const stopped = (item: LearningLibraryItem) => ["cancelled", "rejected", "expired"].includes(item.taskStatus);
  return Number(stopped(a)) - Number(stopped(b))
    || Number(Boolean(b.session)) - Number(Boolean(a.session))
    || (b.session?.startedAt ?? 0) - (a.session?.startedAt ?? 0)
    || (!a.session && !b.session ? b.learningDate.localeCompare(a.learningDate) : 0)
    || (b.taskId ?? "").localeCompare(a.taskId ?? "");
}

export function groupLearningLibraryItems(items: LearningLibraryItem[]): LearningLibraryGroup[] {
  const groups = new Map<string, LearningLibraryItem[]>();
  for (const item of items) {
    const key = learningLibraryGroupKey(item);
    const members = groups.get(key) ?? [];
    const duplicate = members.findIndex(candidate => learningLibraryCourseKey(candidate) === learningLibraryCourseKey(item)
      && candidate.taskId === item.taskId && candidate.session?.id === item.session?.id);
    if (duplicate < 0) members.push(item);
    else if ((item.lastActivityAt ?? 0) > (members[duplicate].lastActivityAt ?? 0)) members[duplicate] = item;
    groups.set(key, members);
  }
  return [...groups].map(([key, members]) => {
    const latestByCourse = new Map<string, LearningLibraryItem>();
    for (const member of [...members].sort(compareAttempts)) {
      const courseKey = learningLibraryCourseKey(member);
      if (!latestByCourse.has(courseKey)) latestByCourse.set(courseKey, member);
    }
    const current = [...latestByCourse.values()].sort((a, b) => priority(a) - priority(b)
      || (b.lastActivityAt ?? 0) - (a.lastActivityAt ?? 0)
      || `${a.course.id}:${a.course.version}:${a.taskId ?? ""}`.localeCompare(`${b.course.id}:${b.course.version}:${b.taskId ?? ""}`));
    const sorted = [...current, ...members.filter(item => !current.includes(item)).sort(compareAttempts)];
    return { key, item: current[0], items: sorted,
      exerciseSetCount: new Set(members.map(learningLibraryCourseKey)).size,
      completedExerciseSetCount: current.filter(item => item.report || item.session?.status === "completed" || item.taskStatus === "completed").length,
      historyCount: new Set(members.filter(item => item.session).map(item => item.session!.id)).size };
  });
}
