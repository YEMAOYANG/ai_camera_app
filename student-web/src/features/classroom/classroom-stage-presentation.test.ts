import { describe, expect, it } from "vitest";

import { classroomStagePresentation } from "@/features/classroom/classroom-stage-presentation";

describe("classroom subject and grade-band presentation", () => {
  it.each([
    ["chinese", "primary_1", "classroom-subject-chinese", "classroom-grade-lower", "听读纸上剧场"],
    ["math", "primary_4", "classroom-subject-math", "classroom-grade-middle", "推理实验台"],
    ["english", "primary_6", "classroom-subject-english", "classroom-grade-upper", "英语任务场"],
  ])("maps %s %s to stable semantic classes", (subject, grade, subjectClass, bandClass, copy) => {
    const presentation = classroomStagePresentation(subject, grade);
    expect(presentation.subjectClass).toBe(subjectClass);
    expect(presentation.gradeBandClass).toBe(bandClass);
    expect(presentation.stageCopy).toContain(copy);
  });
});
