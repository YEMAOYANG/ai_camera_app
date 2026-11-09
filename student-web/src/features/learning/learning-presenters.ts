export function subjectPresentation(subject: string) {
  switch (subject) {
    case "chinese":
      return {
        label: "语文",
        eyebrow: "文字小冒险",
      };
    case "english":
      return {
        label: "英语",
        eyebrow: "英语新发现",
      };
    default:
      return {
        label: "数学",
        eyebrow: "数字实验室",
      };
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
