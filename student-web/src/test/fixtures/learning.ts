import type { LearningLesson, LearningSession } from "@/lib/contracts/learning";

export const lessonFixture: LearningLesson = {
  courseId: "course-pinyin-1",
  version: "1",
  title: "拼音声母小侦探",
  subject: "chinese",
  subjectLabel: "语文",
  objective: "认识 b、p、m，并能听音辨认",
  intro: "声母站在音节最前面。",
  estimatedMinutes: 10,
  questionCount: 4,
  sessionKind: "lesson",
  outcomeMode: "scored_deterministic",
  teachingFlow: {
    schemaVersion: "mira.learning.teaching-flow.v1",
    teach: {
      title: "声母住在音节的最前面",
      sayText: "先听声音，再观察嘴巴怎样发音。b 像广播，p 像泼水，m 像摸一摸。",
      keyPoints: ["看清声母的形状", "听清开头的声音"],
    },
    workedExample: {
      id: "q1",
      type: "single_choice",
      prompt: "“妈妈”的“妈”开头是什么声母？",
      skill: "拼音声母",
      inputMode: "single_choice",
      choices: [
        { id: "a", label: "m" },
        { id: "b", label: "p" },
      ],
      answerDisplayText: "m",
      explanation: "读“妈”时，嘴唇先合起来，发出的开头声音是 m。",
    },
    guidedQuestionIds: ["q2", "q3"],
    independentQuestionIds: ["q4", "q5"],
    recap: { sayText: "今天学会了先听开头的声音，再找声母。" },
  },
};

export const sessionFixture: LearningSession = {
  id: "session-1",
  taskId: "task-1",
  courseId: lessonFixture.courseId,
  courseVersion: "1",
  status: "in_progress",
  currentQuestionIndex: 0,
  totalQuestions: 4,
  correctCount: 0,
  attemptedCount: 0,
  hintCount: 0,
  currentQuestion: {
    id: "q2",
    index: 0,
    type: "single_choice",
    prompt: "“苹果”的“苹”开头是什么声母？",
    skill: "拼音声母",
    attemptNumber: 1,
    inputMode: "single_choice",
    choices: [
      { id: "choice-p", label: "p" },
      { id: "choice-b", label: "b" },
    ],
  },
  startedAt: 1,
};
