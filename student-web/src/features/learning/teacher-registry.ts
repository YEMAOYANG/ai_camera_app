import type { LearningSubject, LearningTeacherProfile } from "@/lib/contracts/learning";

/**
 * A build-time mirror of the public v1 registry. It gives the classroom a
 * stable visual while the authenticated preference request is loading. The
 * server response remains authoritative for the selected profile.
 */
export const learningTeacherProfiles: LearningTeacherProfile[] = [
  {
    id: "mira_chinese_gentle",
    version: 1,
    displayName: "小语老师",
    avatarPath: "/teachers/mi-chinese-v1.png",
    subject: "chinese",
    languageCode: "zh-CN",
    teachingStyle: "gentle_guided",
    capabilities: ["explain_then_practice", "guided_reading", "standard_mandarin", "pinyin_review_gated"],
  },
  {
    id: "mira_math_clear",
    version: 1,
    displayName: "小数老师",
    avatarPath: "/teachers/ashu-math-v1.png",
    subject: "math",
    languageCode: "zh-CN",
    teachingStyle: "clear_structured",
    capabilities: ["worked_examples", "step_by_step_reasoning", "standard_mandarin"],
  },
  {
    id: "mira_english_standard",
    version: 1,
    displayName: "Mia 老师",
    avatarPath: "/teachers/coco-english-v1.png",
    subject: "english",
    languageCode: "en-US",
    teachingStyle: "standard_pronunciation",
    capabilities: ["listen_and_repeat", "phonics", "standard_english_pronunciation", "pronunciation_review_gated"],
  },
];

export type LearningBrowserVoice = {
  language: string;
  rate: number;
  pitch: number;
};

export function findLearningTeacher(teacherId: string | null | undefined) {
  return learningTeacherProfiles.find((teacher) => teacher.id === teacherId)
    || learningTeacherProfiles[0];
}

export function teacherForSubject(
  teacherId: string | null | undefined,
  subject: string,
  profiles: LearningTeacherProfile[] = learningTeacherProfiles,
) {
  const selected = profiles.find((teacher) => teacher.id === teacherId && teacher.subject === subject);
  return selected
    || profiles.find((teacher) => teacher.subject === subject)
    || learningTeacherProfiles.find((teacher) => teacher.subject === subject)
    || learningTeacherProfiles[0];
}

export function browserVoiceForTeacher(teacher?: LearningTeacherProfile): LearningBrowserVoice {
  if (teacher?.subject === "english") {
    return { language: teacher.languageCode || "en-US", rate: 0.86, pitch: 1.08 };
  }
  if (teacher?.subject === "math") {
    return { language: teacher.languageCode || "zh-CN", rate: 0.92, pitch: 1 };
  }
  return { language: teacher?.languageCode || "zh-CN", rate: 0.84, pitch: 1.04 };
}

export function teacherStyleDescription(profile: LearningTeacherProfile) {
  const descriptions: Record<LearningSubject, string> = {
    chinese: "耐心带读、先讲再练，陪你把语文学明白。",
    math: "把步骤拆清楚，用例子陪你理解数学。",
    english: "标准发音、多听多说，陪你大胆开口。",
  };
  return descriptions[profile.subject];
}

export function teacherTone(profile: LearningTeacherProfile) {
  if (profile.subject === "math") return "clear";
  if (profile.subject === "english") return "lively";
  return "gentle";
}
