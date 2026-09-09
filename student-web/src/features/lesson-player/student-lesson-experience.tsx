"use client";

import { ArrowLeft, ArrowRight, Check, CircleHelp, Eraser, Lightbulb, LoaderCircle, PartyPopper, PenLine, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { MiraMark } from "@/components/student/mira-mark";
import { Button } from "@/components/ui/button";
import { getLatestLearningReport, startLearningSession, submitLearningAnswer } from "@/features/learning/learning-client";
import { masteryLabel, subjectPresentation } from "@/features/learning/learning-presenters";
import type {
  LearningAnswerResponse,
  LearningLesson,
  LearningQuestion,
  LearningReport,
  LearningSession,
  LearningStartResponse,
} from "@/lib/contracts/learning";
import type { Student } from "@/lib/contracts/student-session";

type LessonStage = "teach" | "demo" | "practice" | "report";

const stages: Array<{ id: LessonStage; label: string }> = [
  { id: "teach", label: "老师讲" },
  { id: "demo", label: "看示范" },
  { id: "practice", label: "我来练" },
  { id: "report", label: "小总结" },
];

export function StudentLessonExperience({
  student,
  taskId,
  initialStart,
  initialError = "",
}: {
  student: Student;
  taskId: string;
  initialStart?: LearningStartResponse;
  initialError?: string;
}) {
  const [lesson, setLesson] = useState<LearningLesson | null>(null);
  const [session, setSession] = useState<LearningSession | null>(null);
  const [question, setQuestion] = useState<LearningQuestion | null>(null);
  const [report, setReport] = useState<LearningReport | null>(null);
  const [stage, setStage] = useState<LessonStage>("teach");
  const [error, setError] = useState(initialError);
  const [loading, setLoading] = useState(!initialStart && !initialError);

  useEffect(() => {
    let active = true;
    async function start() {
      if (initialError) return;
      setLoading(true);
      setError("");
      try {
        const payload = initialStart || await startLearningSession(taskId);
        if (!active) return;
        setLesson(payload.lesson);
        setSession(payload.session);
        setQuestion(payload.session.currentQuestion);
        if (payload.session.status === "completed") {
          setReport(await getLatestLearningReport(payload.lesson.subject));
          setStage("report");
        } else if (!payload.lesson.teachingFlow || payload.session.currentQuestionIndex > 0) {
          setStage("practice");
        }
      } catch (caught) {
        if (active) setError(caught instanceof Error ? caught.message : "这节课暂时打不开");
      } finally {
        if (active) setLoading(false);
      }
    }
    void start();
    return () => { active = false; };
  }, [initialError, initialStart, taskId]);

  if (loading) return <LessonLoading />;
  if (error || !lesson || !session) return <LessonError message={error || "这节课暂时打不开"} />;

  const presentation = subjectPresentation(lesson.subject);
  const activeStageIndex = stages.findIndex((item) => item.id === stage);
  return (
    <div className="mira-doodle-grid min-h-screen bg-[linear-gradient(145deg,var(--mira-bg),#fffdf4)] px-4 pb-10 pt-4 sm:px-7 sm:pt-6">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3">
        <Link href="/today" className="focus-ring inline-flex min-h-12 items-center gap-2 rounded-[16px] bg-white/85 px-4 font-extrabold text-[var(--mira-ink)] shadow-sm">
          <ArrowLeft className="size-5" /> 回到今天
        </Link>
        <MiraMark compact />
        <span className="hidden rounded-full bg-white/80 px-4 py-2 text-sm font-bold text-[var(--mira-muted)] sm:block">{student.displayName}的课堂</span>
      </header>

      <main id="main-content" className="mx-auto mt-5 w-full max-w-6xl">
        <section className="overflow-hidden rounded-[32px] border-2 border-white bg-white shadow-[var(--mira-shadow-card)]">
          <div className={`h-2 ${presentation.surface}`} aria-hidden="true" />
          <div className="border-b border-[var(--mira-border-soft)] px-5 py-5 sm:px-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className={`text-sm font-extrabold ${presentation.strong}`}>{presentation.label} · {presentation.eyebrow}</p>
                <h1 className="mt-1 text-[clamp(25px,4vw,38px)] font-black tracking-[-.045em]">{lesson.title}</h1>
              </div>
              <StageRail activeIndex={activeStageIndex} />
            </div>
          </div>

          <div className="min-h-[560px] p-5 sm:p-8 lg:p-10">
            {stage === "teach" ? (
              <TeachScene lesson={lesson} onNext={() => setStage("demo")} />
            ) : null}
            {stage === "demo" ? (
              <DemoScene lesson={lesson} onBack={() => setStage("teach")} onNext={() => setStage("practice")} />
            ) : null}
            {stage === "practice" ? (
              <PracticeScene
                lesson={lesson}
                session={session}
                question={question}
                onSession={setSession}
                onQuestion={setQuestion}
                onComplete={(value) => {
                  setReport(value);
                  setStage("report");
                }}
              />
            ) : null}
            {stage === "report" ? <ReportScene lesson={lesson} report={report} /> : null}
          </div>
        </section>
      </main>
    </div>
  );
}

function StageRail({ activeIndex }: { activeIndex: number }) {
  return (
    <ol className="flex items-center gap-1.5" aria-label="课堂进度">
      {stages.map((item, index) => (
        <li key={item.id} className={`grid min-h-10 min-w-10 place-items-center rounded-full px-3 text-xs font-extrabold transition-colors ${index === activeIndex ? "bg-[var(--mira-brand)] text-white" : index < activeIndex ? "bg-[var(--mira-mint)] text-[var(--mira-mint-deep)]" : "bg-[var(--mira-bg)] text-[var(--mira-subtle)]"}`} aria-current={index === activeIndex ? "step" : undefined}>
          <span className="sm:hidden">{index < activeIndex ? <Check className="size-4" /> : index + 1}</span>
          <span className="hidden sm:inline">{index < activeIndex ? "✓ " : ""}{item.label}</span>
        </li>
      ))}
    </ol>
  );
}

function TeachScene({ lesson, onNext }: { lesson: LearningLesson; onNext: () => void }) {
  const flow = lesson.teachingFlow;
  if (!flow) return null;
  return (
    <div className="grid items-center gap-8 lg:grid-cols-[250px_1fr]">
      <div className="relative mx-auto">
        <MiraBuddy mood="reading" className="w-[210px] sm:w-[240px]" label="Mira 老师正在讲课" />
        <span className="absolute -right-5 top-4 rounded-[18px_18px_18px_5px] bg-[var(--mira-sun-soft)] px-4 py-2 text-sm font-extrabold text-[#8b651d] shadow-sm">先听我讲</span>
      </div>
      <div>
        <p className="text-sm font-extrabold text-[var(--mira-brand-deep)]">今天要学会</p>
        <h2 className="mt-2 text-[clamp(30px,5vw,48px)] font-black leading-tight tracking-[-.05em]">{flow.teach.title || lesson.title}</h2>
        <div className="mt-6 rounded-[24px] bg-[var(--mira-brand-wash)]/72 p-5 text-[17px] leading-8 text-[var(--mira-ink)] sm:p-6">
          {flow.teach.sayText || lesson.intro}
        </div>
        {flow.teach.keyPoints.length ? (
          <ul className="mt-5 grid gap-3 sm:grid-cols-2">
            {flow.teach.keyPoints.map((point, index) => (
              <li key={point} className="flex items-start gap-3 rounded-[18px] border-2 border-[var(--mira-border-soft)] bg-white p-4 font-bold leading-6">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[var(--mira-sun)] text-sm text-[var(--mira-ink)]">{index + 1}</span>{point}
              </li>
            ))}
          </ul>
        ) : null}
        <Button className="mt-7 w-full sm:w-auto" onClick={onNext}>一起看个例子 <ArrowRight className="size-5" /></Button>
      </div>
    </div>
  );
}

function DemoScene({ lesson, onBack, onNext }: { lesson: LearningLesson; onBack: () => void; onNext: () => void }) {
  const demo = lesson.teachingFlow?.workedExample;
  if (!demo) return null;
  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-[18px] bg-[var(--mira-sun-soft)] text-[#9c6a13]"><Lightbulb className="size-6" /></span>
        <div><p className="text-sm font-extrabold text-[#9c6a13]">Mira 示范题</p><h2 className="text-3xl font-black tracking-[-.04em]">看一看是怎么想的</h2></div>
      </div>
      <div className="mt-7 rounded-[28px] border-2 border-[var(--mira-border-soft)] bg-[var(--mira-bg)] p-6 sm:p-8">
        <p className="text-[clamp(22px,4vw,32px)] font-black leading-relaxed">{demo.prompt}</p>
        {demo.choices.length ? (
          <div className="mt-5 grid gap-2 sm:grid-cols-2">{demo.choices.map((choice, index) => <div key={choice.id} className="rounded-[16px] bg-white px-4 py-3 font-bold"><span className="mr-2 text-[var(--mira-subtle)]">{String.fromCharCode(65 + index)}.</span>{choice.label}</div>)}</div>
        ) : null}
        <div className="mt-6 rounded-[20px] bg-[var(--mira-mint)] p-5">
          <p className="text-sm font-extrabold text-[var(--mira-mint-deep)]">答案是</p>
          <p className="mt-1 text-2xl font-black text-[var(--mira-ink)]">{demo.answerDisplayText}</p>
          <p className="mt-3 leading-7 text-[var(--mira-muted)]">{demo.explanation}</p>
        </div>
      </div>
      <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <Button variant="quiet" onClick={onBack}>再听一遍</Button>
        <Button onClick={onNext}>轮到我来试试 <ArrowRight className="size-5" /></Button>
      </div>
    </div>
  );
}

function PracticeScene({
  lesson,
  session,
  question,
  onSession,
  onQuestion,
  onComplete,
}: {
  lesson: LearningLesson;
  session: LearningSession;
  question: LearningQuestion | null;
  onSession: (session: LearningSession) => void;
  onQuestion: (question: LearningQuestion | null) => void;
  onComplete: (report: LearningReport | null) => void;
}) {
  const [text, setText] = useState("");
  const [selected, setSelected] = useState("");
  const [sequence, setSequence] = useState<string[]>([]);
  const [result, setResult] = useState<LearningAnswerResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const flow = lesson.teachingFlow;
  const guided = question ? flow?.guidedQuestionIds.includes(question.id) : false;
  const responseReady = useMemo(() => {
    if (!question) return false;
    if (question.type === "single_choice") return Boolean(selected);
    if (question.type === "sequence") return sequence.length === question.choices.length;
    return Boolean(text.trim());
  }, [question, selected, sequence, text]);

  function clearResponse() {
    setText(""); setSelected(""); setSequence([]); setResult(null); setError("");
  }

  async function submit() {
    if (!question || !responseReady || submitting) return;
    setSubmitting(true); setError("");
    try {
      const body = question.type === "single_choice"
        ? { response: { kind: "single_choice", optionId: selected } }
        : question.type === "sequence"
          ? { response: { kind: "sequence", items: sequence } }
          : { answer: text.trim() };
      const answerResult = await submitLearningAnswer(session.id, body);
      setResult(answerResult);
      onSession(answerResult.session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "答案没有提交成功");
    } finally {
      setSubmitting(false);
    }
  }

  function continueAfterFeedback() {
    if (!result) return;
    if (result.canRetry) {
      onQuestion(result.nextQuestion || result.session.currentQuestion || question);
      clearResponse();
      return;
    }
    if (result.completed) {
      onComplete(result.report);
      return;
    }
    onQuestion(result.nextQuestion || result.session.currentQuestion);
    clearResponse();
  }

  if (!question && session.status !== "completed") {
    return <div className="mx-auto max-w-xl py-16 text-center"><MiraBuddy mood="thinking" className="mx-auto w-32" /><h2 className="mt-4 text-2xl font-black">题目正在准备</h2><p className="mt-2 text-[var(--mira-muted)]">先回到今天，过一会儿再试试。</p><Button asChild className="mt-6"><Link href="/today">回到今天</Link></Button></div>;
  }

  if (!question) return null;
  const currentNumber = Math.min(session.currentQuestionIndex + 1, session.totalQuestions);
  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3"><MiraBuddy mood={result ? (result.correct ? "celebrate" : "thinking") : "hello"} className="w-20" /><div><p className="text-sm font-extrabold text-[var(--mira-brand-deep)]">{guided ? "一起练习" : "独立挑战"}</p><h2 className="text-2xl font-black">第 {currentNumber} 题 / 共 {session.totalQuestions} 题</h2></div></div>
        <div className="h-3 w-full overflow-hidden rounded-full bg-[var(--mira-border-soft)] sm:w-52"><div className="h-full rounded-full bg-[var(--mira-brand)] transition-[width]" style={{ width: `${((session.currentQuestionIndex + (result && !result.canRetry ? 1 : 0)) / Math.max(1, session.totalQuestions)) * 100}%` }} /></div>
      </div>

      <div className="mt-6 rounded-[28px] bg-[var(--mira-bg)] p-5 sm:p-8">
        <p className="text-[clamp(22px,4vw,34px)] font-black leading-relaxed tracking-[-.025em]">{question.prompt}</p>
        <div className="mt-7">
          {question.type === "single_choice" ? (
            <div className="grid gap-3 sm:grid-cols-2">{question.choices.map((choice, index) => <button key={choice.id} type="button" disabled={Boolean(result)} onClick={() => setSelected(choice.id)} className={`focus-ring min-h-16 rounded-[20px] border-2 px-5 text-left font-extrabold transition ${selected === choice.id ? "border-[var(--mira-brand)] bg-[var(--mira-brand-wash)] text-[var(--mira-brand-deep)]" : "border-white bg-white hover:border-[var(--mira-border)]"}`}><span className="mr-3 text-[var(--mira-subtle)]">{String.fromCharCode(65 + index)}.</span>{choice.label}</button>)}</div>
          ) : null}
          {question.type === "sequence" ? (
            <div>
              <div className="min-h-16 rounded-[20px] border-2 border-dashed border-[var(--mira-border)] bg-white p-3">{sequence.length ? <div className="flex flex-wrap gap-2">{sequence.map((id, index) => { const choice = question.choices.find((item) => item.id === id); return <span key={id} className="rounded-full bg-[var(--mira-brand-wash)] px-3 py-2 font-bold text-[var(--mira-brand-deep)]">{index + 1}. {choice?.label}</span>; })}</div> : <p className="py-2 text-center text-[var(--mira-subtle)]">按正确顺序点击下面的内容</p>}</div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">{question.choices.map((choice) => <button key={choice.id} type="button" disabled={sequence.includes(choice.id) || Boolean(result)} onClick={() => setSequence((items) => [...items, choice.id])} className="focus-ring min-h-14 rounded-[17px] border-2 border-white bg-white px-4 font-bold disabled:opacity-40">{choice.label}</button>)}</div>
              {!result && sequence.length ? <Button variant="quiet" size="compact" className="mt-3" onClick={() => setSequence([])}><Eraser className="size-4" />重新排列</Button> : null}
            </div>
          ) : null}
          {!question.choices.length ? (
            <label className="block"><span className="sr-only">我的答案</span><input value={text} disabled={Boolean(result)} onChange={(event) => setText(event.target.value)} inputMode={question.type === "numeric" ? "decimal" : "text"} className="focus-ring h-16 w-full rounded-[20px] border-2 border-white bg-white px-5 text-xl font-extrabold outline-none focus:border-[var(--mira-brand)]" placeholder="把答案写在这里" /></label>
          ) : null}
        </div>
      </div>

      {error ? <p className="mt-4 rounded-[16px] bg-[#fff1ee] p-4 font-bold text-[var(--mira-danger)]" role="alert">{error}</p> : null}
      {result ? (
        <div className={`mt-5 rounded-[24px] p-5 ${result.correct ? "bg-[var(--mira-mint)]" : "bg-[var(--mira-sun-soft)]"}`} role="status">
          <div className="flex items-start gap-3"><span className={`grid size-10 shrink-0 place-items-center rounded-full bg-white ${result.correct ? "text-[var(--mira-mint-deep)]" : "text-[#9c6a13]"}`}>{result.correct ? <Check className="size-5" /> : <CircleHelp className="size-5" />}</span><div><p className="text-lg font-black">{result.feedback}</p>{result.hint ? <p className="mt-2 leading-7 text-[var(--mira-muted)]"><strong>小提示：</strong>{result.hint}</p> : null}</div></div>
          <Button className="mt-5 w-full sm:w-auto" onClick={continueAfterFeedback}>{result.canRetry ? "按照提示再试一次" : result.completed ? "看看我的小总结" : "下一题"}<ArrowRight className="size-5" /></Button>
        </div>
      ) : (
        <Button className="mt-6 w-full sm:w-auto" onClick={submit} disabled={!responseReady || submitting}>{submitting ? <LoaderCircle className="size-5 animate-spin" /> : <PenLine className="size-5" />}{submitting ? "正在看看答案…" : "提交答案"}</Button>
      )}
    </div>
  );
}

function ReportScene({ lesson, report }: { lesson: LearningLesson; report: LearningReport | null }) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <MiraBuddy mood="celebrate" className="mx-auto w-44" label="Mira 在为你庆祝" />
      <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-[var(--mira-sun-soft)] px-4 py-2 text-sm font-extrabold text-[#8b651d]"><PartyPopper className="size-4" />这节课完成啦</p>
      <h2 className="mt-4 text-[clamp(34px,6vw,52px)] font-black tracking-[-.05em]">学会一点，就是很棒！</h2>
      {report ? (
        <div className="mt-7 grid gap-4 text-left sm:grid-cols-3">
          <div className="rounded-[22px] bg-[var(--mira-brand-wash)] p-5"><p className="text-sm font-bold text-[var(--mira-muted)]">独立答对</p><p className="mt-2 text-3xl font-black text-[var(--mira-brand-deep)]">{report.independentCorrectCount}/{report.totalQuestions}</p></div>
          <div className="rounded-[22px] bg-[var(--mira-mint)] p-5"><p className="text-sm font-bold text-[var(--mira-muted)]">掌握情况</p><p className="mt-2 text-xl font-black text-[var(--mira-mint-deep)]">{masteryLabel(report.masteryLevel)}</p></div>
          <div className="rounded-[22px] bg-[var(--mira-sun-soft)] p-5"><p className="text-sm font-bold text-[var(--mira-muted)]">用到提示</p><p className="mt-2 text-3xl font-black text-[#9c6a13]">{report.hintCount} 次</p></div>
        </div>
      ) : null}
      <div className="mt-5 rounded-[24px] bg-[var(--mira-bg)] p-6 text-left">
        <p className="flex items-center gap-2 font-extrabold text-[var(--mira-brand-deep)]"><Sparkles className="size-5" />Mira 的小总结</p>
        <p className="mt-3 text-lg leading-8">{lesson.teachingFlow?.recap.sayText || report?.summary || "今天的学习已经保存好了。"}</p>
        {report?.nextStep ? <p className="mt-3 leading-7 text-[var(--mira-muted)]">下次：{report.nextStep}</p> : null}
      </div>
      <Button asChild className="mt-7"><Link href="/today">回到今天的课程 <ArrowRight className="size-5" /></Link></Button>
    </div>
  );
}

function LessonLoading() {
  return <main id="main-content" className="grid min-h-screen place-items-center px-5"><div className="text-center"><MiraBuddy mood="reading" className="mx-auto w-36" /><p className="mt-4 flex items-center gap-2 font-extrabold text-[var(--mira-muted)]"><LoaderCircle className="size-5 animate-spin" />Mira 正在打开课件</p></div></main>;
}

function LessonError({ message }: { message: string }) {
  return <main id="main-content" className="grid min-h-screen place-items-center px-5"><div className="max-w-md rounded-[28px] border-2 border-white bg-white p-7 text-center shadow-[var(--mira-shadow-card)]"><MiraBuddy mood="thinking" className="mx-auto w-32" /><h1 className="mt-4 text-3xl font-black">这节课刚刚走神了</h1><p className="mt-3 leading-7 text-[var(--mira-muted)]">{message}</p><Button asChild className="mt-6"><Link href="/today">回到今天</Link></Button></div></main>;
}
