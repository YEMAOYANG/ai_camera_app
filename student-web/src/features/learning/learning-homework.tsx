"use client";
import Link from "next/link";
import Image from "next/image";
import { QuantityPicture } from "./quantity-picture";
import { ArrowLeft, ArrowRight, Backpack, Camera, Check, Hand, Lightbulb, PencilLine, RefreshCw, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { z } from "zod";
import { useRouter } from "next/navigation";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import type { Student } from "@/lib/contracts/student-session";
import { homeworkAudioPath, homeworkDetailSchema, homeworkListSchema, type HomeworkDetail, type HomeworkItem, type HomeworkSubmission, captureTaskSchema } from "@/lib/contracts/homework";
import { SubjectPicture } from "./learning-picture-navigation";
import { useReviewVoice } from "./learning-reviews";
import { HomeworkCollection, HomeworkPaperOverview, HomeworkOriginalQuestion, homeworkTutorQuestions } from "./homework-paper-overview";
import { HomeworkAiTutor } from "./homework-ai-tutor";
import { homeworkAvailability, homeworkAvailabilityLabels, homeworkProcessing } from "./homework-availability";
import { teacherForSubject } from "./teacher-registry";
import { HomeworkMathText } from "./homework-math-text";
import { homeworkStudentCopy } from "./homework-student-copy";
import { homeworkCorrectionWorkflowDone } from "./homework-correction-status";

async function read(response: Response) {
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.message === "string" ? body.message : "暂时没连接上，请再试一次");
  return body;
}

export function HomeworkInvitation({ compact = false }: { compact?: boolean }) {
  const [captureTasks, setCaptureTasks] = useState<z.infer<typeof captureTaskSchema>[]>([]);
  const [submissions, setSubmissions] = useState<HomeworkSubmission[] | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    fetch("/api/learning/homework", { signal: c.signal, cache: "no-store" }).then(read).then(value => { const parsed = homeworkListSchema.parse(value); setSubmissions(parsed.submissions); setCaptureTasks(parsed.captureTasks); setError(""); })
      .catch(error => { if (!c.signal.aborted) setError(error instanceof Error ? error.message : "小任务还没打开"); });
    return () => c.abort();
  }, [reload]);
  const pending = submissions?.filter(item => !["completed", "completed_partial", "clear", "self_reported"].includes(homeworkAvailability(item)));
  const records = compact ? pending : submissions;
  if (compact && !pending?.length && !captureTasks.length) return null;
  return <section className="homework-invitation" aria-label={homeworkStudentCopy.title}>
    {captureTasks.map(task => <HomeworkCapture key={task.taskId} task={task} />)}
    {error ? <div role="alert"><p>{error}</p><Button size="compact" onClick={() => setReload(v => v + 1)}><RefreshCw />再试一次</Button></div>
      : !submissions ? <p role="status">正在整理小练习…</p>
      : !records?.length && captureTasks.length ? null : !records?.length ? <div className="learning-review-rest"><Check className="learning-review-state-icon" /><h2>暂时没有需要订正的题目</h2><p>上传的作业准备好后，老师会在这里陪你讲题、再试一试。</p><Button asChild><Link href="/learning"><Backpack />回到书包</Link></Button></div>
      : <><HomeworkCollection records={records.slice(0, compact ? 1 : 50)} compact={compact} />{compact && pending && pending.length > 1 && <Button asChild size="compact" variant="quiet"><Link href="/learning/homework">其他作业<ArrowRight /></Link></Button>}</>}
  </section>;
}

function HomeworkCapture({ task }: { task: z.infer<typeof captureTaskSchema> }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const key = useRef<string | null>(null);
  const sending = useRef(false);
  async function capture() {
    if (sending.current || !task.available) return;
    sending.current = true; setBusy(true); setError("");
    key.current ??= crypto.randomUUID();
    try {
      const response = homeworkDetailSchema.parse(await fetch("/api/learning/homework-captures", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ taskId: task.taskId, idempotencyKey: key.current }) }).then(read));
      router.push(`/learning/homework/${response.submission.id}`);
    } catch (error) { setError(error instanceof Error ? error.message : "请在家长 App 上传作业"); }
    finally { sending.current = false; setBusy(false); }
  }
  return <div className="homework-capture" aria-busy={busy}>
    <svg viewBox="0 0 360 170" role="img" aria-label="把作业纸平放在摄像头下，让整张纸进入画面">
      <rect x="8" y="16" width="120" height="134" rx="12" fill="#eee5d3" /><rect x="37" y="39" width="66" height="88" rx="3" fill="#fffaf0" stroke="#788675" strokeWidth="2" /><path d="M49 57h42M49 71h42M49 85h28" stroke="#788675" strokeWidth="4" />
      <path d="M145 84h35m-10-10 10 10-10 10" fill="none" stroke="#57705c" strokeWidth="5" />
      <rect x="198" y="16" width="154" height="134" rx="12" fill="#e1eadc" /><path d="M263 43v-12h30v12" fill="none" stroke="#57705c" strokeWidth="5" /><rect x="253" y="41" width="49" height="26" rx="7" fill="#57705c" /><circle cx="278" cy="54" r="6" fill="#fffaf0" /><path d="m263 68-22 28h72l-22-28" fill="#ccdbc9" /><rect x="243" y="98" width="66" height="38" rx="3" fill="#fffaf0" stroke="#788675" strokeWidth="2" /><path d="M254 111h43M254 122h28" stroke="#788675" strokeWidth="3" />
    </svg>
    <div><h3>{task.title}</h3><p>{task.available ? "把作业放好，点相机拍一张" : "这台设备暂不支持拍作业，请用家长 App 上传"}</p><Button size="compact" disabled={busy || !task.available} onClick={() => void capture()}><Camera />{busy ? "正在拍摄…" : "拍作业"}</Button>{error && <p role="alert">{error}</p>}</div>
  </div>;
}

export function LearningHomework({ student, submissionId }: { student: Student; submissionId?: string }) {
  return <SchoolbagShell student={student} className={`learning-review-shell${submissionId ? " learning-homework-shell" : ""}`}><div className="learning-review-heading"><div><p>作业与试卷</p><h1>{homeworkStudentCopy.title}</h1></div><Button asChild size="compact" variant="quiet"><Link href="/learning"><Backpack />回到书包</Link></Button></div>
    {submissionId ? <HomeworkWorkspace key={submissionId} id={submissionId} /> : <HomeworkInvitation />}
  </SchoolbagShell>;
}

export function HomeworkWorkspace({ id }: { id: string }) {
  const [data, setData] = useState<HomeworkDetail | null>(null);
  const [error, setError] = useState("");
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [tutorItemId, setTutorItemId] = useState<string | null>(null);
  const revisionRef = useRef<number | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => homeworkDetailSchema.parse(await fetch(`/api/learning/homework/${id}`, { signal, cache: "no-store" }).then(read)), [id]);
  const receive = useCallback((value: HomeworkDetail) => {
    if (revisionRef.current !== null && revisionRef.current !== value.submission.revision) { setActiveItemId(null); setTutorItemId(null); }
    revisionRef.current = value.submission.revision;
    setData(value); setError("");
  }, []);
  async function refresh() { try { receive(await load()); } catch (e) { setError(e instanceof Error ? e.message : "作业还没打开"); } }
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(value => { if (!controller.signal.aborted) receive(value); }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "作业还没打开"); });
    return () => controller.abort();
  }, [load, receive]);
  const processing = data ? homeworkProcessing(data.submission) : false;
  useEffect(() => {
    if (!processing || activeItemId || tutorItemId) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => { if (!document.hidden) load(controller.signal).then(value => { if (!controller.signal.aborted) receive(value); }).catch(() => {}); }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [activeItemId, tutorItemId, load, processing, receive]);
  function openTutor(itemId: string) {
    window.dispatchEvent(new Event("mira:learner-narration"));
    setTutorItemId(itemId);
  }
  const tutorItem = data && homeworkTutorQuestions(data.submission).find(item => item.id === tutorItemId && item.tutorAvailable);
  if (activeItemId && data) return <HomeworkActivity id={id} initialData={data} initialItemId={activeItemId} onBackToOverview={() => { setActiveItemId(null); setData(value => value ? { ...value, feedback: undefined } : value); }} onData={receive} onTutor={itemId => { setActiveItemId(null); setTutorItemId(itemId); }} />;
  return <><section className="homework-workspace" hidden={!!tutorItem}>
    {error && <p role="alert" className="learning-review-error">{error}<Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />再试一次</Button></p>}
    {!data ? !error && <p role="status">正在整理原作业…</p> : <HomeworkPaperOverview key={`${id}:${data.submission.revision}`} submission={data.submission} onData={receive} onStart={itemId => { setData(value => value ? { ...value, feedback: undefined } : value); setActiveItemId(itemId); }} onTutor={openTutor} onRefresh={() => void refresh()} />}
  </section>{data && tutorItem && <HomeworkAiTutor key={`${id}:${tutorItem.id}:${tutorItem.revision}`} submission={data.submission} item={tutorItem} startOnOpen onData={receive} onBack={() => { setTutorItemId(null); void refresh(); }} />}</>;
}

export function HomeworkActivity({ id, initialData, initialItemId, onBackToOverview, onData, onTutor }: { id: string; initialData?: HomeworkDetail; initialItemId?: string; onBackToOverview?: () => void; onData?: (value: HomeworkDetail) => void; onTutor?: (itemId: string) => void }) {
  const [data, setData] = useState<HomeworkDetail | null>(initialData ?? null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [currentId, setCurrentId] = useState<string | null>(initialItemId ?? null);
  const [answer, setAnswer] = useState("");
  const pending = useRef<{ hash: string; key: string } | null>(null);
  const voice = useReviewVoice();
  const onDataRef = useRef(onData);
  useEffect(() => { onDataRef.current = onData; }, [onData]);
  const receive = useCallback((value: HomeworkDetail) => { setData(value); onDataRef.current?.(value); }, []);
  const load = useCallback(async (signal?: AbortSignal) => homeworkDetailSchema.parse(await fetch(`/api/learning/homework/${id}`, { signal, cache: "no-store" }).then(read)), [id]);
  useEffect(() => {
    const c = new AbortController();
    load(c.signal).then(value => { if (!c.signal.aborted) receive(value); }).catch(e => { if (!c.signal.aborted) setError(e instanceof Error ? e.message : "小任务还没打开"); });
    return () => c.abort();
  }, [load, receive]);
  const availability = data ? homeworkAvailability(data.submission) : null;
  const processing = data ? homeworkProcessing(data.submission) : false;
  useEffect(() => {
    if (!processing) return;
    const c = new AbortController();
    const timer = window.setInterval(() => {
      if (!document.hidden && !busyRef.current) load(c.signal).then(value => { if (!c.signal.aborted) receive(value); }).catch(() => { /* The last saved state remains usable; explicit refresh can show an error. */ });
    }, 5000);
    return () => { c.abort(); window.clearInterval(timer); };
  }, [load, processing, receive]);

  const submission = data?.submission;
  const lowReading = ["primary_1", "primary_2"].includes(submission?.gradeCode ?? "primary_1");
  const canPractice = (item: HomeworkItem) => item.readyForStudent && (!lowReading || !!item.picture);
  const question = submission?.items.find(item => item.id === currentId && (canPractice(item) || item.correctionStatus === "corrected"))
    ?? submission?.items.find(item => !homeworkCorrectionWorkflowDone(item.studentCorrection) && item.correctionStatus !== "corrected" && canPractice(item))
    ?? submission?.items.find(item => !homeworkCorrectionWorkflowDone(item.studentCorrection) && item.correctionStatus !== "corrected");
  async function refresh() { try { receive(await load()); setError(""); } catch (e) { setError(e instanceof Error ? e.message : "暂时没连接上"); } }
  function play(item: HomeworkItem, kind: keyof HomeworkItem["voice"]) { voice.play(homeworkAudioPath(item.voice[kind]?.assetUrl, id, item.id)); }

  async function send(operation: "actions" | "answers", response: string) {
    if (!question || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); voice.stop(); setCurrentId(question.id);
    const key = JSON.stringify([question.id, question.revision, response]);
    if (pending.current?.hash !== key) pending.current = { hash: key, key: crypto.randomUUID() };
    try {
      const body = operation === "answers" ? { itemRevision: question.revision, answer: response, idempotencyKey: pending.current.key } : { itemRevision: question.revision, action: response };
      const result = await fetch(`/api/learning/homework/${id}/items/${question.id}/${operation}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (result.status === 409) { await refresh(); throw new Error("题目已更新，请再看看当前这道题"); }
      const value = homeworkDetailSchema.parse(await read(result)); receive(value); pending.current = null;
      const item = value.submission.items.find(item => item.id === question.id);
      if (item) play(item, operation === "answers" ? value.feedback?.audioKind ?? "retry" : response === "explanation" ? "explanation" : "hint");
    } catch (e) { setError(e instanceof Error ? e.message : "答案还没保存，请再试一次"); }
    finally { busyRef.current = false; setBusy(false); }
  }
  function next() {
    setData(value => value ? { ...value, feedback: undefined } : value);
    voice.stop(); setAnswer(""); setError("");
    const nextQuestion = submission?.items.find(item => !homeworkCorrectionWorkflowDone(item.studentCorrection) && item.correctionStatus !== "corrected" && canPractice(item))
      ?? submission?.items.find(item => !homeworkCorrectionWorkflowDone(item.studentCorrection) && item.correctionStatus !== "corrected");
    if (nextQuestion) { setCurrentId(nextQuestion.id); if (canPractice(nextQuestion)) play(nextQuestion, "prompt"); }
    else setCurrentId(null);
  }
  const showingSavedAnswer = question?.correctionStatus === "corrected" && !!data?.feedback;
  const ready = (availability === "ready" || showingSavedAnswer) && question?.readyForStudent && (!lowReading || !!question.picture);
  const teacher = teacherForSubject(null, submission?.subject ?? "math");
  const demonstrationCount = question?.explanationViewed && question.expectedAnswer !== undefined ? Number(question.expectedAnswer) : null;
  const showDemonstration = question?.picture && demonstrationCount !== null && Number.isInteger(demonstrationCount) && demonstrationCount >= 0 && demonstrationCount <= 20;
  return <section className="learning-review-activity" aria-busy={busy}>
    {onBackToOverview && <Button size="compact" variant="quiet" className="homework-back-to-paper" disabled={busy} onClick={() => { voice.stop(); onBackToOverview(); }}><ArrowLeft />回到错题概览</Button>}
    {error && <p role="alert" className="learning-review-error">{error}<Button variant="quiet" size="compact" onClick={() => void refresh()}><RefreshCw />刷新</Button></p>}
    {!submission ? <p role="status">正在打开老师的订正课…</p>
      : availability === "clear" ? <div className="learning-review-rest"><Check className="learning-review-state-icon" /><h2>{homeworkAvailabilityLabels.clear}</h2><p>老师已检查这份作业，结果已经保存。</p><Button asChild><Link href="/learning"><Backpack />回到书包</Link></Button></div>
      : availability === "self_reported" && !showingSavedAnswer ? <div className="learning-review-rest"><PencilLine className="learning-review-state-icon" /><h2>纸上订正标记已保存</h2><p>老师还没核对新答案，复习时再试试；也可以回到原作业继续订正。</p>{onBackToOverview && <Button size="compact" variant="secondary" onClick={onBackToOverview}><ArrowLeft />看原作业</Button>}</div>
      : availability === "completed_partial" && !showingSavedAnswer ? <div className="learning-review-rest"><Check className="learning-review-state-icon" /><h2>可订正的 {submission.summary.corrected} 道题完成啦</h2><p>另外 {(submission.originalSummary?.unsupported ?? 0) + (submission.studentSummary?.unsupportedCorrection ?? 0)} 道题的原题讲解尚未准备好，尚未计作订正或全对。</p><p>你和老师一起完成的记录已保存，家长也能看到。</p><Button asChild><Link href="/learning"><Backpack />回到书包</Link></Button></div>
      : availability === "completed" && !showingSavedAnswer ? <div className="learning-review-rest"><Check className="learning-review-state-icon" /><h2>这次订正完成啦</h2><p>你和老师一起完成的记录已保存，家长也能看到。</p><Button asChild><Link href="/learning"><Backpack />回到书包</Link></Button></div>
      : !question || !ready ? <div className="learning-review-rest"><SubjectPicture subject="math" /><h2>{homeworkAvailabilityLabels[availability ?? "unavailable"]}</h2><p>{availability === "needs_check" ? "原作业已保存。可以回到原作业，选择原题请老师讲解。" : processing ? "照片已收到，老师准备好后，会在这里陪你讲解和作答。" : availability === "unsupported" ? "原作业已保存，这道原题的讲解还没准备好。" : "这份作业的图片或声音尚未准备好，再看看准备情况。"}</p><div className="learning-review-actions">{onBackToOverview && <Button size="compact" variant="secondary" onClick={onBackToOverview}><ArrowLeft />看原作业</Button>}<Button onClick={() => void refresh()}><RefreshCw />再看看</Button><Button asChild variant="secondary"><Link href="/learning"><Backpack />回到书包</Link></Button></div></div>
      : <><div className="learning-review-progress"><span>{submission.title}</span><progress max={Math.max(1, submission.items.length)} value={submission.summary.corrected} aria-label="订正进度" /><span>{submission.summary.corrected} / {submission.items.length}</span></div>
        <HomeworkOriginalQuestion submission={submission} item={question} />
        {question.tutorAvailable && onTutor && <Button size="compact" variant="secondary" onClick={() => { voice.stop(); onTutor(question.id); }}><Volume2 />{homeworkStudentCopy.originalQuestionLecture}</Button>}
        <div className="homework-teacher" aria-label={homeworkStudentCopy.correctionRegion}><Image src={teacher.avatarPath} width={76} height={76} alt={homeworkStudentCopy.teacherAlt} /><div><p>用圆片想一想原作业这道题</p><h2>{question.explanationViewed ? "听完讲解，自己再试试" : "老师陪你把这道题弄明白"}</h2><div className="homework-teacher-steps" aria-label="看题、听老师讲解、自己作答"><span><Hand />看题</span><ArrowRight /><span><Volume2 />听讲解</span><ArrowRight /><span><Check />再试试</span></div></div><Button variant="secondary" size="compact" disabled={busy || question.correctionStatus === "corrected"} onClick={() => { if (question.explanationViewed) play(question, "explanation"); else void send("actions", "explanation"); }}><Volume2 />{question.explanationViewed ? "再听老师讲" : homeworkStudentCopy.title}</Button></div>
        <div className="learning-review-task-heading"><h2><HomeworkMathText text={question.prompt} /></h2><Button size="compact" variant="secondary" onClick={() => play(question, "prompt")}><Volume2 />{voice.failed ? "再听一次" : "听老师说"}</Button></div>
        {question.picture ? <><div className="homework-quantity-scene" aria-label="数一数圆片"><QuantityPicture count={question.picture.left} removed={question.picture.operation === "subtract" ? question.picture.right : 0} />{question.picture.operation === "add" && <><span aria-label="加上">+</span><QuantityPicture count={question.picture.right} /></>}<span aria-hidden="true">= ?</span></div>
          {showDemonstration && <div className="homework-teacher-demonstration" aria-label="老师讲解后的数量演示"><Volume2 aria-hidden="true" /><ArrowRight aria-hidden="true" /><QuantityPicture count={demonstrationCount!} /><span>{demonstrationCount} 个</span></div>}
          <div className="learning-review-choices homework-quantity-choices" role="group" aria-label="点图片，选择圆片的数量">{question.picture.choices.map(choice => <button key={choice.id} disabled={busy || question.correctionStatus === "corrected"} type="button" aria-label={`${choice.count} 个圆片`} aria-pressed={answer === choice.id} onClick={() => { setAnswer(choice.id); void send("answers", choice.id); }}><QuantityPicture count={choice.count} /></button>)}</div></>
          : <form className="homework-answer-form" onSubmit={event => { event.preventDefault(); void send("answers", answer); }}><label htmlFor="homework-answer">你的答案</label><input id="homework-answer" value={answer} onChange={event => setAnswer(event.target.value)} inputMode="decimal" maxLength={128} autoComplete="off" disabled={busy || question.correctionStatus === "corrected"} /><Button type="submit" disabled={!answer.trim() || busy || question.correctionStatus === "corrected"}>选好了<Check /></Button></form>}
        {(question.hintViewed || question.explanationViewed) && <div className="learning-review-feedback"><Lightbulb /><p><HomeworkMathText text={(question.explanationViewed ? question.explanation : question.hint) ?? ""} /></p><Button variant="secondary" size="icon" aria-label="再听一遍提示" onClick={() => play(question, question.explanationViewed ? "explanation" : "hint")}><Volume2 /></Button></div>}
        {data?.feedback && <div className="learning-review-feedback" aria-live="polite">{data.feedback.correct ? <Check /> : <RefreshCw />}<p>{data.feedback.correct ? "这一次你会啦！" : "一起再数一数。"}</p></div>}
        <div className="learning-review-actions">{question.correctionStatus === "corrected" ? <Button onClick={next}>继续<ArrowRight /></Button> : <Button size="compact" variant="secondary" disabled={busy} onClick={() => void send("actions", "hint")}><Lightbulb />我想自己试，给一点提示</Button>}<Button asChild size="compact" variant="quiet"><Link href="/learning"><Backpack />休息一下</Link></Button></div>
      </>}
  </section>;
}
