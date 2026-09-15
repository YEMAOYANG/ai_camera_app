"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, CircleHelp, LoaderCircle, Orbit, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SpaceShell, SpacePageHeading } from "@/components/student/space-shell";
import { SpaceCourseArt } from "@/components/student/space-course-art";
import { SpaceSuccessBurst } from "@/components/student/space-success-burst";
import { practiceResponseSchema, type PracticeResponse } from "@/lib/contracts/learning-practice";
import type { Student } from "@/lib/contracts/student-session";

const subjects = [{ id: "chinese", label: "语文" }, { id: "math", label: "数学" }, { id: "english", label: "英语" }] as const;
async function practiceRequest(path: string, body?: object): Promise<PracticeResponse> {
  const response = await fetch(path, { method: body ? "POST" : "GET", cache: "no-store",
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "练习暂时没有连接上");
  return practiceResponseSchema.parse(payload);
}

export function LearningPractice({ student, sessionId }: { student: Student; sessionId?: string }) {
  const router = useRouter();
  const [subject, setSubject] = useState<"chinese" | "math" | "english">("math");
  const [result, setResult] = useState<PracticeResponse | null>(null);
  const [feedback, setFeedback] = useState<PracticeResponse["evaluation"]>();
  const [answer, setAnswer] = useState("");
  const [sequence, setSequence] = useState<string[]>([]);
  const [busy, setBusy] = useState(Boolean(sessionId));
  const [error, setError] = useState("");
  const [celebration, setCelebration] = useState(0);
  const [completedNow, setCompletedNow] = useState(false);
  const [subjectPicked, setSubjectPicked] = useState(false);
  const requestId = useRef<string | null>(null);
  const loadedSessionId = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId || loadedSessionId.current === sessionId) return;
    let active = true;
    practiceRequest(`/api/learning/practice/sessions/${encodeURIComponent(sessionId)}`)
      .then(value => { if (active) { loadedSessionId.current = sessionId; setResult(value); if (value.session) setSubject(value.session.subject); } })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : "暂时无法恢复练习"); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [sessionId]);

  async function start() {
    if (busy) return;
    setBusy(true); setError(""); setFeedback(undefined); setAnswer(""); setSequence([]); setCompletedNow(false);
    requestId.current ??= crypto.randomUUID();
    try {
      const value = await practiceRequest("/api/learning/practice/sessions", { requestId: requestId.current, subject, count: 5 });
      loadedSessionId.current = value.session?.id ?? null;
      setResult(value);
      if (value.session) router.replace(`/learning/practice?session=${value.session.id}`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "暂时无法开始练习"); }
    finally { setBusy(false); }
  }
  async function submit() {
    const session = result?.session, question = session?.currentQuestion;
    if (!session || !question || busy) return;
    setBusy(true); setError("");
    try {
      const value = await practiceRequest(`/api/learning/practice/sessions/${session.id}/answers`, {
        questionId: question.id, response: question.type === "sequence" ? sequence : answer,
      });
      setResult(value); setFeedback(value.evaluation); setAnswer(""); setSequence([]);
      if (value.evaluation?.correct) setCelebration(current => current + 1);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "答案还没保存，请再试一次"); }
    finally { setBusy(false); }
  }
  function chooseSubject(value: typeof subject) {
    setSubject(value); setSubjectPicked(true); requestId.current = null; setResult(null); setError("");
  }
  function continuePractice() {
    if (result?.session?.status === "completed") setCompletedNow(true);
    setFeedback(undefined);
  }
  const session = result?.session;
  const question = session?.currentQuestion;
  return (
    <SpaceShell student={student} active="practice" className={`space-practice-page ${question ? "is-answering" : ""}`}>
      <SpacePageHeading eyebrow={`${student.displayName}的复习时间`} title="学过的内容，练一练" description="每次最多五题，只复习已经学完的课程。" backHref="/learning" backLabel="回到学习书架" />
      <section className="space-practice-stage" aria-live="polite">
        {error && <p role="alert" className="space-inline-error">{error}</p>}
        {busy && !result ? <div className="space-page-state space-practice-launching"><span className="space-launch-signal" aria-hidden="true"><Orbit /><i /></span><h2>正在取出复习题…</h2></div> : feedback ? (
          <div className={`space-practice-feedback ${feedback.correct ? "is-correct" : "is-review"}`}>
            <div className="space-feedback-emblem"><span className="space-result-icon">{feedback.correct ? <CheckCircle2 aria-hidden="true" /> : <CircleHelp aria-hidden="true" />}</span><SpaceSuccessBurst key={celebration} active={feedback.correct && celebration > 0} /></div>
            <p className="space-eyebrow">{feedback.correct ? "这道题答对了" : "一起看看这道题"}</p>
            <h2>{feedback.message}</h2>
            {feedback.explanation && <p className="space-answer-explanation">{feedback.explanation}</p>}
            <Button className="space-practice-action" onClick={continuePractice}>{session?.status === "completed" ? "看看这次练习" : "下一题"}<ArrowRight className="size-5" aria-hidden="true" /></Button>
          </div>
        ) : session?.status === "completed" ? (
          <div className="space-practice-complete">
            <div className="space-feedback-emblem"><span className="space-result-icon"><CheckCircle2 aria-hidden="true" /></span><SpaceSuccessBurst active={completedNow} /></div>
            <p className="space-eyebrow">探索完成</p>
            <h2>这次复习完成啦！</h2>
            <p className="space-answer-explanation">完成 {session.totalQuestions} 题，答对 {session.correctCount} 题。</p>
            <div className="space-practice-score" aria-hidden="true"><strong>{session.correctCount}</strong><span>/ {session.totalQuestions}</span></div>
            <div className="space-inline-actions"><Button asChild><Link href="/learning">回到学习书架<ArrowRight className="size-5" aria-hidden="true" /></Link></Button><Button variant="secondary" onClick={() => { requestId.current = null; setResult(null); router.replace("/learning/practice"); }}>再选一组</Button></div>
          </div>
        ) : question ? (
          <div className="space-practice-question">
            <div className="space-question-topline"><p className="space-eyebrow">{subjects.find(item => item.id === subject)?.label} · 复习</p><span>第 {(session?.currentQuestionIndex ?? 0) + 1} 题 / {session?.totalQuestions} 题</span></div>
            <div className="space-question-progress space-progress-orbit" role="progressbar" aria-label="复习进度" aria-valuemin={0} aria-valuemax={session?.totalQuestions} aria-valuenow={session?.currentQuestionIndex ?? 0}>
              <span style={{ width: `${((session?.currentQuestionIndex ?? 0) / Math.max(1, session?.totalQuestions ?? 1)) * 100}%` }} />
              <div className="space-progress-nodes" aria-hidden="true">{Array.from({ length: session?.totalQuestions ?? 0 }, (_, index) => <i key={index} className={index < (session?.currentQuestionIndex ?? 0) ? "is-complete" : index === (session?.currentQuestionIndex ?? 0) ? "is-current" : ""} />)}</div>
            </div>
            <h2>{question.prompt}</h2>
            {(question.type === "single_choice" || question.type === "sequence") && question.choices.length ? (
              <div className="space-answer-choices" role="group" aria-label={question.type === "sequence" ? "按顺序选择" : "选择答案"}>
                {question.choices.map((choice, index) => {
                  const position = sequence.indexOf(choice.id), selected = question.type === "sequence" ? position >= 0 : answer === choice.id;
                  return <button key={choice.id} disabled={busy || (question.type === "sequence" && selected)} aria-pressed={selected} className={`focus-ring space-answer-choice ${selected ? "is-selected" : ""}`} onClick={() => question.type === "sequence" ? setSequence(current => [...current, choice.id]) : setAnswer(choice.id)}>
                    <span className="space-answer-letter" aria-hidden="true">{question.type === "sequence" ? (selected ? position + 1 : "–") : String.fromCharCode(65 + index)}</span><span>{choice.label}</span>{selected && <CheckCircle2 className="space-choice-check" aria-hidden="true" />}
                  </button>;
                })}
                {question.type === "sequence" && <Button variant="quiet" disabled={busy} onClick={() => setSequence([])}><RotateCcw className="size-5" aria-hidden="true" />重新排列</Button>}
              </div>
            ) : <label className="space-answer-input-label">你的答案<input autoComplete="off" value={answer} disabled={busy} onChange={event => setAnswer(event.target.value)} inputMode={question.type === "numeric" ? "decimal" : "text"} className="focus-ring space-answer-input" /></label>}
            <div className="space-question-submit"><Button className="space-practice-action" data-busy={busy} disabled={busy || (question.type === "sequence" ? sequence.length !== question.choices.length : !answer.trim())} onClick={() => void submit()}>{busy ? "正在保存…" : "提交答案"}{busy ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <ArrowRight className="size-5" aria-hidden="true" />}</Button></div>
          </div>
        ) : (
          <div className="space-practice-start">
            {result?.session === null && <p className="space-inline-note">{result.message}</p>}
            <h2>想复习哪一科？</h2>
            <div className="space-practice-subjects" role="group" aria-label="复习学科">
              {subjects.map(item => <button key={item.id} disabled={busy} aria-label={item.label} aria-pressed={subject === item.id} className={`focus-ring space-practice-subject space-destination-${item.id} ${subject === item.id ? `is-selected ${subjectPicked ? "is-picked" : ""}` : ""}`} onClick={() => chooseSubject(item.id)}><SpaceCourseArt subject={item.id} className="space-practice-subject-art" /><i className="space-destination-orbit" aria-hidden="true" /><span className="space-destination-label"><strong>{item.label}</strong><small>{subject === item.id ? "已选择这个星球" : "前往这个星球"}</small></span>{subject === item.id && <CheckCircle2 aria-hidden="true" />}</button>)}
            </div>
            <div className="space-inline-actions"><Button className="space-practice-action" data-busy={busy} disabled={busy} onClick={() => void start()}>{busy ? "正在准备…" : "开始复习"}<ArrowRight className="size-5" aria-hidden="true" /></Button>{result?.session === null && <Button variant="secondary" asChild><Link href="/learning">先复习学过的课程</Link></Button>}</div>
          </div>
        )}
      </section>
    </SpaceShell>
  );
}
