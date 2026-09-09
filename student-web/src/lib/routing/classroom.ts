export function openMaicLessonPath(taskId: string) {
  return `/lesson/${encodeURIComponent(taskId)}/classroom`;
}
