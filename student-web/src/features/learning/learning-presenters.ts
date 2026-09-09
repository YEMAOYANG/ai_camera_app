import { BookOpenText, Languages, Sigma } from "lucide-react";

export function subjectPresentation(subject: string) {
  switch (subject) {
    case "chinese":
      return {
        icon: BookOpenText,
        label: "语文",
        eyebrow: "文字小冒险",
        surface: "bg-[var(--mira-peach)]",
        strong: "text-[#a84f38]",
        accent: "#f28c70",
      };
    case "english":
      return {
        icon: Languages,
        label: "英语",
        eyebrow: "英语新发现",
        surface: "bg-[var(--mira-lilac)]",
        strong: "text-[#6651ba]",
        accent: "#8b78dd",
      };
    default:
      return {
        icon: Sigma,
        label: "数学",
        eyebrow: "数字实验室",
        surface: "bg-[var(--mira-sky)]",
        strong: "text-[var(--mira-brand-deep)]",
        accent: "#2f6cf6",
      };
  }
}

export function gradeLabel(gradeCode?: string | null) {
  const grade = Number(gradeCode?.match(/^primary_(\d)$/)?.[1]);
  return grade >= 1 && grade <= 6 ? `${"一二三四五六"[grade - 1]}年级` : "小学学习";
}

export function stateLabel(state: string) {
  switch (state) {
    case "completed": return "完成啦";
    case "in_progress": return "继续学习";
    case "scheduled": return "可以开始";
    default: return "正在准备";
  }
}

export function masteryLabel(value: string) {
  switch (value) {
    case "mastered": return "已经掌握";
    case "developing": return "正在变熟练";
    case "needs_practice": return "再练一次会更好";
    default: return value;
  }
}
