import type { LearningSubject } from "@/lib/contracts/learning";

export type ClassroomGradeBand = "lower" | "middle" | "upper";

const stageCopy: Record<LearningSubject, Record<ClassroomGradeBand, string>> = {
  chinese: {
    lower: "听读纸上剧场 · 看字形、听声音",
    middle: "阅读发现剧场 · 找线索、说理解",
    upper: "表达思辨剧场 · 读深一点、说清依据",
  },
  math: {
    lower: "操作实验台 · 摆一摆、数一数",
    middle: "推理实验台 · 画一画、找规律",
    upper: "数学建模台 · 设想、验证、表达",
  },
  english: {
    lower: "听说小舞台 · 听一听、跟着说",
    middle: "情境对话台 · 听懂、回应、表达",
    upper: "英语任务场 · 获取信息、完成表达",
  },
};

export function classroomStagePresentation(subjectValue: string, gradeCode?: string | null) {
  const subject = normalizeSubject(subjectValue);
  const gradeBand = classroomGradeBand(gradeCode);
  return {
    subject,
    gradeBand,
    subjectClass: `classroom-subject-${subject}`,
    gradeBandClass: `classroom-grade-${gradeBand}`,
    stageCopy: stageCopy[subject][gradeBand],
  } as const;
}

export function classroomGradeBand(gradeCode?: string | null): ClassroomGradeBand {
  const grade = Number.parseInt(String(gradeCode || "").match(/(\d)$/)?.[1] || "1", 10);
  if (grade >= 5) return "upper";
  if (grade >= 3) return "middle";
  return "lower";
}

function normalizeSubject(subject: string): LearningSubject {
  if (subject === "math" || subject === "english") return subject;
  return "chinese";
}
