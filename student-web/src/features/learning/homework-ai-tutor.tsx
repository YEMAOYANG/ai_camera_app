"use client";
import Image from "next/image";
import { ArrowDown, ArrowLeft, ArrowRight, BookOpen, ChevronDown, Hand, LoaderCircle, Pointer, HelpCircle, MessageCircle, Pause, RefreshCw, Send, Volume2, ZoomIn } from "lucide-react";
import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { homeworkTutorAudioPath, homeworkTutorResponseSchema, type HomeworkTutorResponse, type HomeworkTutorStep } from "@/lib/contracts/homework-tutor";
import { type HomeworkDetail, type HomeworkItem, type HomeworkSubmission } from "@/lib/contracts/homework";
import { HomeworkGradingDetails, HomeworkOriginalQuestion, HomeworkPaperImage, HomeworkQuestionPicture } from "./homework-paper-overview";
import { HomeworkQuestionRecorder } from "./homework-question-recorder";
import { useHomeworkTutorVoice } from "./use-homework-tutor-voice";
import { teacherForSubject } from "./teacher-registry";
import { homeworkTeachingNeedsReview } from "./homework-student-quality";
import { HomeworkMathText } from "./homework-math-text";
import { homeworkStudentCopy } from "./homework-student-copy";
import { HomeworkReviewExplorer } from "./homework-review-explorer";
import { HomeworkCorrectionStatus } from "./homework-correction-status";
import { HomeworkPaperCompletion } from "./homework-paper-completion";

const simplerExplanation = "我还没有听懂，请用更简单的图片和短句再讲一次。";
type TutorTurn = HomeworkTutorResponse["tutor"]["turns"][number];
type OutgoingReply = { mode: "followup" | "answer"; message: string; key: string; state: "sending" | "unknown" | "rejected" };

function legacyConfirmation(turn: HomeworkTutorResponse["tutor"]["turns"][number]) {
  if (turn.status !== "ready") return false;
  if (turn.teachingQuality && ["verified", "guidance"].includes(turn.teachingQuality.status)) return false;
  // The server explicitly distinguishes historical full-page reviews from the
  // current zoom review. A new unclear review must not become an automatic retry.
  if (turn.sourceImageReviewRequired !== undefined) return turn.sourceImageReviewRequired;
  return turn.status === "ready" && (turn.sourceConfirmationOnly || turn.assessment?.status === "needs_confirmation") && turn.teachingScope !== "original_image_guidance" && turn.sourceCheck?.basis !== "original_image";
}

function completedReviewRequired(turn: HomeworkTutorResponse["tutor"]["turns"][number] | undefined, item: HomeworkItem) {
  if (turn?.status !== "ready") return false;
  if (turn.reviewState === "required") return true;
  // A verified image lesson may explain the question while the child's
  // handwriting is unreadable. Source limitations cannot revoke the server's
  // verified teaching decision (including essay guidance).
  if (turn.teachingQuality && ["verified", "guidance"].includes(turn.teachingQuality.status)) return false;
  return homeworkTeachingNeedsReview(turn, item) || legacyConfirmation(turn)
    || turn.sourceConfirmationOnly === true || turn.assessment?.status === "needs_confirmation"
    || turn.sourceCheck?.questionReadable === false || turn.sourceCheck?.answerLocated === false;
}

/** Only the server can release an early text answer independently of audio. */
function teacherTextReady(turn: TutorTurn | undefined, item: HomeworkItem) {
  return !!turn && turn.replyReady !== false && (turn.status === "ready" || turn.replyReady === true)
    && turn.reviewState !== "required" && !completedReviewRequired(turn, item) && !homeworkTeachingNeedsReview(turn, item);
}

function ShapePicture({ shape, count, color = "amber" }: { shape: "circle" | "triangle" | "square" | "rectangle"; count: number; color?: "amber" | "green" | "blue" | "red" }) {
  const palette = { amber: "var(--mira-brand)", green: "var(--mira-success)", blue: "var(--mira-picture-blue)", red: "var(--mira-danger)" }, fill = palette[color];
  return <svg viewBox="0 0 260 130" role="img" aria-label={`${count} 个${{ circle: "圆形", triangle: "三角形", square: "正方形", rectangle: "长方形" }[shape]}`}>
    {Array.from({ length: count }, (_, i) => { const x = 12 + (i % 5) * 50, y = 6 + Math.floor(i / 5) * 30; return shape === "circle" ? <circle key={i} cx={x + 12} cy={y + 12} r="10" fill={fill} stroke="var(--mira-ink)" /> : shape === "triangle" ? <path key={i} d={`M${x + 12} ${y + 1}l12 23h-24z`} fill={fill} stroke="var(--mira-ink)" /> : <rect key={i} x={x} y={y + 2} width={shape === "rectangle" ? 34 : 22} height="22" rx="2" fill={fill} stroke="var(--mira-ink)" />; })}
  </svg>;
}
function TutorQuantity({ count }: { count: number }) {
  const rows = Math.max(1, Math.ceil(count / 10));
  return <svg viewBox={`0 0 320 ${rows * 32 + 16}`} role="img" aria-label={`${count} 个圆片`}><rect width="320" height={rows * 32 + 16} rx="10" fill="var(--mira-brand-wash)" />{Array.from({ length: count }, (_, i) => <circle key={i} cx={16 + (i % 10) * 32} cy={24 + Math.floor(i / 10) * 32} r="11" fill="var(--mira-brand)" stroke="var(--mira-warning)" />)}{!count && <ellipse cx="160" cy="24" rx="50" ry="16" fill="none" stroke="var(--mira-muted)" strokeDasharray="4 5" />}</svg>;
}
function TutorVisual({ step, stepIndex, submission, item, disabled, onAnswer }: { step: HomeworkTutorStep; stepIndex: number; submission: HomeworkSubmission; item: HomeworkItem; disabled?: boolean; onAnswer: (value: string) => void }) {
  const page = submission.pages.find(p => p.id === item.reviewContext?.pageId), visual = step.visual;
  if (visual.kind === "quantity" && visual.count !== undefined && visual.count <= 100) return <div className="homework-tutor-quantity"><TutorQuantity count={visual.count} /></div>;
  if (visual.kind === "groups" && visual.groups?.length) return <div className="homework-tutor-groups" aria-label="老师把数量分成了几组">{visual.groups.map((count, i) => <div key={i}><TutorQuantity count={count} /></div>)}</div>;
  if (visual.kind === "shapes" && visual.shapes?.length) return <div className="homework-tutor-groups">{visual.shapes.map((group, i) => <ShapePicture key={i} {...group} />)}</div>;
  if (visual.kind === "choices" && page && visual.choices?.length && visual.choices.every(choice => !!choice.region || choice.count !== undefined)) return <div className="homework-tutor-picture-choices" role="group" aria-label="点原题图片，说出我的选择">{visual.choices.map((choice, index) => <button key={choice.id} className="homework-tutor-picture-choice" type="button" disabled={disabled} aria-label={`选择第 ${index + 1} 张原题图片`} onClick={() => onAnswer(`在第 ${stepIndex + 1} 步（${step.id}），我选择第 ${index + 1} 张图，选项 ${choice.label ?? choice.id}。`)}>{choice.region ? <HomeworkPaperImage submissionId={submission.id} page={page} region={choice.region} alt={`原题选项 ${choice.id}`} allowRetry={false} /> : <TutorQuantity count={choice.count!} />}<HomeworkMathText text={choice.label ?? choice.id} /></button>)}</div>;
  return page ? <HomeworkQuestionPicture submission={submission} item={item} region={visual.region} alt="老师正在讲解的原题图片" /> : <p className="homework-tutor-no-photo">原题照片暂时没打开，请先查看原作业</p>;
}
export function HomeworkAiTutor({ submission, item, onBack, onData, startOnOpen = false }: { submission: HomeworkSubmission; item: HomeworkItem; onBack: () => void; onData?: (value: HomeworkDetail) => void; startOnOpen?: boolean }) {
  const endpoint = `/api/learning/homework/${submission.id}/items/${item.id}/tutor`;
  const itemRevision = item.revision;
  const isEssay = submission.analysisKind === "essay";
  const [data, setData] = useState<HomeworkTutorResponse["tutor"] | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false), [message, setMessage] = useState("");
  const [stepIndexes, setStepIndexes] = useState<Record<string, number>>({});
  const [replyMode, setReplyMode] = useState<"followup" | "answer">("followup");
  const [chatOpen, setChatOpen] = useState(false), [acknowledgedRequestKey, setAcknowledgedRequestKey] = useState("");
  const [outgoingReply, setOutgoingReply] = useState<OutgoingReply | null>(null);
  const [acceptedRequestKey, setAcceptedRequestKey] = useState("");
  const [originalExpanded, setOriginalExpanded] = useState(false), [showLatest, setShowLatest] = useState(false);
  const [composerLocked, setComposerLocked] = useState(false), [markLocked, setMarkLocked] = useState(false);
  const sending = useRef(false), pending = useRef<{ mode: "explain" | "followup" | "answer"; message: string; key: string } | null>(null), alive = useRef(true);
  const pendingAudio = useRef<{ turnId: string; key: string } | null>(null);
  const initialExplanationSent = useRef(false);
  const teacher = teacherForSubject(null, submission.subject);
  const voice = useHomeworkTutorVoice({ scopeKey: `${submission.id}:${item.id}:${item.revision}`, turns: data?.turns.map(saved => ({ id: saved.id, requestKey: saved.requestKey, audioPath: saved.status === "ready" && teacherTextReady(saved, item) && saved.audio.status === "ready" ? homeworkTutorAudioPath(saved.audio.assetUrl, submission.id, item.id, saved.id) : null })) ?? [] });
  const stopVoice = voice.stop;
  const tutorRoot = useRef<HTMLElement>(null), chatHeader = useRef<HTMLDivElement>(null), chatLog = useRef<HTMLDivElement>(null), chatEnd = useRef<HTMLDivElement>(null), followsLatest = useRef(true), lastChatVersion = useRef("");
  const positionedScope = useRef<string | null>(null);
  const previouslyChatOpen = useRef(false);
  useEffect(() => {
    const scope = `${submission.id}:${item.id}:${item.revision}`;
    if (!data || data.itemId !== item.id || data.itemRevision !== item.revision || positionedScope.current === scope) return;
    // Wait for the first saved response to render the full picture and composer;
    // scrolling the small loading placeholder would be clamped by the browser.
    positionedScope.current = scope;
    tutorRoot.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
  }, [data, submission.id, item.id, item.revision]);
  const receive = useCallback((value: unknown) => {
    const parsed = homeworkTutorResponseSchema.parse(value).tutor;
    if (parsed.itemId !== item.id || parsed.itemRevision !== item.revision) throw new Error("原题已更新，请回到原作业重新打开");
    if (alive.current) { setData(parsed); setError(""); }
    return parsed;
  }, [item.id, item.revision]);
  const query = useCallback(async (signal?: AbortSignal) => {
    const response = await fetch(endpoint, { signal, cache: "no-store" }), value = await response.json();
    if (!response.ok) throw new Error(value.message || "老师的准备情况还没打开");
    const parsed = receive(value), receipt = pending.current;
    const matched = receipt && parsed.turns.find(turn => turn.requestKey === receipt.key);
    const latest = parsed.turns.at(-1);
    // A terminal review returned by the server rejects further explanation
    // requests. A lost rejection receipt must not leave an endless paid-query
    // reconciliation state, or manufacture another request identity.
    const completedReview = receipt?.mode === "explain" && latest?.status === "ready" && latest.reviewState === "required" && latest.reviewRetryAllowed !== true ? latest : undefined;
    if (matched || completedReview) { pending.current = null; if (alive.current) { setOutgoingReply(null); if (matched?.requestKey) setAcceptedRequestKey(matched.requestKey); setUncertain(false); setMessage(""); } }
    if (pendingAudio.current && parsed.turns.some(turn => turn.id === pendingAudio.current?.turnId && turn.audio.status !== "unavailable")) { pendingAudio.current = null; if (alive.current) setUncertain(false); }
    return parsed;
  }, [endpoint, receive]);
  useEffect(() => { alive.current = true; const controller = new AbortController(); void query(controller.signal).catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "老师还没连接上"); }); return () => { alive.current = false; controller.abort(); }; }, [query]);
  const preparing = data?.turns.some(turn => ["queued", "working"].includes(turn.status) || (turn.status === "ready" && !completedReviewRequired(turn, item) && turn.audio.status === "pending")) ?? false;
  useEffect(() => { if (!preparing && !uncertain) return; const controller = new AbortController(), timer = window.setInterval(() => { if (!document.hidden && !sending.current) void query(controller.signal).catch(() => {}); }, 4000); return () => { clearInterval(timer); controller.abort(); }; }, [preparing, uncertain, query]);
  const orderedTurns = data?.turns ?? [];
  // The original lesson belongs beside the paper. The conversation preserves
  // every question and answer; source turns remain intact for receipt/audio gates.
  const conversationTurns = orderedTurns.filter(saved => saved.mode !== "explain");
  const latestExplain = orderedTurns.findLast(saved => saved.mode === "explain"), safeExplain = orderedTurns.findLast(saved => saved.mode === "explain" && teacherTextReady(saved, item));
  const turn = orderedTurns.at(-1);
  const completedReview = completedReviewRequired(turn, item);
  const needsReview = completedReview || homeworkTeachingNeedsReview(turn, item) === true || turn?.status === "ready" && turn.replyReady === false;
  const canReply = data?.enabled && !!turn && teacherTextReady(turn, item);
  const correction = data?.correction ?? item.studentCorrection;
  const hasReadStatusAction = completedReview || !!outgoingReply || (!!turn && ["queued", "working", "unknown", "failed"].includes(turn.status));
  const reviewedTemplate = Boolean(turn?.teachingQuality?.status === "verified" && turn.teachingQuality.method === "operator_reviewed_order_reversal.v1");
  const explanationBlocked = !!turn && turn.reviewRetryAllowed !== true;
  const limitReached = data?.remainingTurnsPerItem === 0 || data?.remainingCallsPerSubmission === 0;
  const unknownReceipt = data?.turns.some(saved => saved.status === "unknown") ?? false;
  const failedReceipt = turn?.status === "failed" || data?.turns.at(-1)?.status === "failed";
  const blocked = busy || preparing || uncertain || markLocked || !data?.enabled || unknownReceipt || failedReceipt || limitReached;
  const replyBlocked = blocked || needsReview || (!!turn && legacyConfirmation(turn));
  const chatVersion = conversationTurns.map(saved => `${saved.id}:${saved.status}:${saved.replyReady}:${saved.teacherText}:${saved.steps.map(step => step.text).join("|")}`).join(";") + `;${outgoingReply?.key}:${outgoingReply?.state}`;
  const scrollMessages = useCallback((behavior: ScrollBehavior = "auto") => {
    const log = chatLog.current;
    if (log && window.matchMedia?.("(min-width: 900px)").matches) {
      if (log.scrollTo) log.scrollTo({ top: log.scrollHeight, behavior });
      else log.scrollTop = log.scrollHeight;
    } else chatEnd.current?.scrollIntoView?.({ behavior, block: "nearest" });
  }, []);
  useEffect(() => {
    const wasOpen = previouslyChatOpen.current;
    previouslyChatOpen.current = chatOpen;
    if (!chatOpen) {
      if (wasOpen && !window.matchMedia?.("(min-width: 900px)").matches) tutorRoot.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
      return;
    }
    if (window.matchMedia?.("(min-width: 900px)").matches) { if (followsLatest.current) scrollMessages(); }
    else chatHeader.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
  }, [chatOpen, scrollMessages]);
  const scrollToLatest = useCallback(() => {
    followsLatest.current = true; setShowLatest(false);
    scrollMessages(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
  }, [scrollMessages]);
  useEffect(() => {
    if (!data || lastChatVersion.current === chatVersion) return;
    const initialRead = lastChatVersion.current === "";
    lastChatVersion.current = chatVersion;
    if (!chatOpen) return;
    // A saved read with unchanged text (including audio polling) never steals
    // the scroll position from a child looking at an earlier message.
    if (followsLatest.current) {
      // On a phone, enter at the original picture and its open lesson. Only
      // a new message should move the page down to the conversation.
      if (!initialRead || window.matchMedia?.("(min-width: 900px)").matches) scrollMessages();
    }
    else { const timer = window.setTimeout(() => setShowLatest(true), 0); return () => clearTimeout(timer); }
  }, [chatVersion, data, chatOpen, scrollMessages]);
  useEffect(() => {
    const readPagePosition = () => {
      if (!chatOpen) return;
      const log = chatLog.current;
      if (!log || log.scrollHeight > log.clientHeight + 2) return;
      followsLatest.current = (chatEnd.current?.getBoundingClientRect().top ?? 0) <= window.innerHeight + 120;
    };
    window.addEventListener("scroll", readPagePosition, { passive: true });
    return () => window.removeEventListener("scroll", readPagePosition);
  }, [chatOpen]);
  async function send(mode: "explain" | "followup" | "answer", text = "") {
    const clean = text.trim(); if (sending.current || blocked || (mode !== "explain" && (needsReview || !clean))) return;
    if (mode === "explain" && explanationBlocked) return;
    if (reviewedTemplate && ((mode === "followup" && clean !== simplerExplanation) || (mode === "answer" && !/^\d+$/.test(clean)))) return;
    const request = pending.current?.mode === mode && pending.current.message === clean ? pending.current : { mode, message: clean, key: crypto.randomUUID() };
    pending.current = request; sending.current = true; setBusy(true); setError(""); stopVoice();
    if (mode !== "explain") voice.arm(request.key);
    followsLatest.current = true; setShowLatest(false);
    if (mode !== "explain") setOutgoingReply({ mode, message: clean, key: request.key, state: "sending" });
    try {
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itemRevision, idempotencyKey: request.key, mode, message: clean }) }), value = await response.json();
      if (!response.ok) { if (response.status >= 400 && response.status < 500) { pending.current = null; voice.stop(); setUncertain(false); setOutgoingReply(saved => saved ? { ...saved, state: "rejected" } : saved); if (response.status === 409 && value.error === "homework_tutor_review_required") { try { await query(); } catch { /* The rejection is final even if the read fails. */ } } throw new Error(value.message || "问题没有提交成功，请重新查看原题"); } setUncertain(true); throw new Error(value.message || "正在核实老师是否收到问题"); }
      const parsed = receive(value), matching = parsed.turns.find(saved => saved.requestKey === request.key);
      if (mode !== "explain" && !matching) { setUncertain(true); setOutgoingReply(saved => saved ? { ...saved, state: "unknown" } : saved); throw new Error("正在核实老师是否收到这个问题，不会重复发送"); }
      pending.current = null; setOutgoingReply(null); if (mode !== "explain") setAcceptedRequestKey(request.key); setMessage(""); setUncertain(false);
    } catch (error) {
      let reconciled = false;
      if (pending.current) { setUncertain(true); setOutgoingReply(saved => saved ? { ...saved, state: "unknown" } : saved); try { await query(); reconciled = pending.current === null; } catch { /* Only read the receipt. Never resubmit a paid request after response loss. */ } }
      if (alive.current && !reconciled) setError(error instanceof Error ? error.message : "正在核实问题状态，不会重复发送");
    } finally { sending.current = false; if (alive.current) setBusy(false); }
  }
  const explainOnEntry = useEffectEvent(() => { void send("explain"); });
  useEffect(() => {
    // Workspace teacher clicks authorize one initial explanation, including a
    // saved source review explicitly allowed by the server. Reading a saved
    // result or losing a POST receipt never authorizes another paid request.
    const latest = data?.turns.at(-1);
    const allowedSourceReview = latest?.status === "ready" && latest.reviewState === "required" && latest.reviewRetryAllowed === true;
    if (!startOnOpen || !data || (data.turns.length && !allowedSourceReview) || blocked || initialExplanationSent.current) return;
    initialExplanationSent.current = true;
    explainOnEntry();
  }, [startOnOpen, data, blocked, item]);
  async function refresh() { try { await query(); } catch (error) { setError(error instanceof Error ? error.message : "准备情况还没打开"); } }
  async function prepareAudio() {
    if (!turn || needsReview || sending.current || blocked || turn.audio.status !== "unavailable" || turn.audio.errorCode !== "homework_audio_unconfigured") return;
    pendingAudio.current ??= { turnId: turn.id, key: crypto.randomUUID() }; sending.current = true; setBusy(true); setError("");
    try {
      const response = await fetch(`${endpoint}/${turn.id}/audio`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itemRevision: item.revision, idempotencyKey: pendingAudio.current.key }) }), value = await response.json();
      if (!response.ok) { if (response.status >= 400 && response.status < 500) pendingAudio.current = null; throw new Error(value.message || "老师的声音还没准备好"); }
      receive(value); pendingAudio.current = null;
    } catch (error) { if (pendingAudio.current) { setUncertain(true); try { await query(); } catch {} } setError(error instanceof Error ? error.message : "正在核实声音准备状态"); }
    finally { sending.current = false; if (alive.current) setBusy(false); }
  }
  function audioControls(saved: TutorTurn) {
    const path = saved.status === "ready" && teacherTextReady(saved, item) && saved.audio.status === "ready" ? homeworkTutorAudioPath(saved.audio.assetUrl, submission.id, item.id, saved.id) : null;
    const speaking = voice.playingTurnId === saved.id, failed = voice.failedTurnId === saved.id;
    const label = saved.mode === "explain" ? "老师完整讲解" : "老师回答";
    return <div className="homework-tutor-reply-audio" aria-label={`第 ${orderedTurns.indexOf(saved) + 1} 条老师消息的语音`}>
      <Button size="compact" variant="secondary" disabled={!path || composerLocked} onClick={() => voice.toggle(saved.id, path!)}>{speaking ? <Pause /> : <Volume2 />}{speaking ? `暂停${label}` : `听${label}`}</Button>
      {path && <Button size="compact" variant="quiet" disabled={composerLocked} onClick={() => voice.play(saved.id, path)}><RefreshCw />重听</Button>}
      {failed && <p role="status">老师的声音没有播放，可以点听一听。</p>}
      {saved.audio.status !== "ready" && <p role="status">{saved.audio.status === "pending" ? "文字回答已经准备好，老师的语音还在准备。" : "文字回答已保留，老师的语音暂时不可用。"}</p>}
      {saved === turn && ["unknown", "failed"].includes(saved.status) && <Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />查看回答状态</Button>}
      {saved === turn && saved.mode === "explain" && saved.audio.status === "unavailable" && saved.audio.errorCode === "homework_audio_unconfigured" && <Button size="compact" variant="secondary" disabled={blocked} onClick={() => void prepareAudio()}><Volume2 />准备老师语音</Button>}
    </div>;
  }
  function teacherContent(saved: TutorTurn) {
    const current = saved === turn;
    if (!teacherTextReady(saved, item)) {
      const review = saved.reviewState === "required" || saved.status === "ready" && (completedReviewRequired(saved, item) || homeworkTeachingNeedsReview(saved, item) || saved.replyReady === false);
      if (review) return current ? <div className="homework-tutor-review" role="region" aria-label="原题暂未核实"><Pointer aria-hidden="true" /><h3>先看原图，点一点做标记</h3><p>{saved.reviewRetryAllowed === true ? "圈圈帮你数和比，答案还没核对清楚。标记不会当成订正结果。" : "这道题暂时不能确认，先看原图或换一道题；照片看不清时可以补拍。"}</p>{(saved.reviewRetryAllowed === true || uncertain) && <div className="homework-tutor-controls"><Button size="compact" variant="secondary" onClick={() => void refresh()}><RefreshCw />看看核对状态</Button>{saved.reviewRetryAllowed === true && <Button size="compact" variant="secondary" disabled={blocked} onClick={() => void send("explain")}><ZoomIn />{homeworkStudentCopy.reviewAgainAction}</Button>}</div>}</div> : <p className="homework-tutor-source-note">这段讲解还需核对，先看原图。</p>;
      return <div className="homework-tutor-reply-status" role="status">{["queued", "working"].includes(saved.status) ? <LoaderCircle aria-hidden="true" /> : <HelpCircle aria-hidden="true" />}<p>{["queued", "working"].includes(saved.status) ? saved.mode === "explain" ? "老师正在看这道原题，准备图片讲解和声音…" : saved.mode === "answer" ? "老师正在核对你的答案…" : "老师正在回答这个问题…" : saved.status === "unknown" ? "这次问题的处理结果还在核实，原问题已保留。" : "这次回答还没准备好，原问题已保留。"}</p>{current && <Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />{saved.mode === "explain" ? ["queued", "working"].includes(saved.status) ? "看看准备情况" : "查看讲解状态" : "查看回答状态"}</Button>}</div>;
    }
    if (saved.mode !== "explain") {
      const paragraphs = [...new Set([saved.teacherText, ...saved.steps.map(step => step.text)].map(text => text.trim()).filter(Boolean))];
      const visual = saved.steps.find(step => step.visual.kind !== "paper_region");
      return <section className="homework-tutor-followup" aria-label={saved.mode === "answer" ? "老师回应这次作答" : "老师回答这次问题"}><h3>{saved.mode === "answer" ? "老师看了你的答案" : "老师回答"}</h3><div className="homework-tutor-full-reply">{paragraphs.map((text, index) => <p key={index}><HomeworkMathText text={text} /></p>)}</div>{visual && <figure className="homework-tutor-reply-visual"><TutorVisual step={visual} stepIndex={saved.steps.indexOf(visual)} submission={submission} item={item} disabled onAnswer={() => {}} /></figure>}{audioControls(saved)}</section>;
    }
    const index = Math.min(stepIndexes[saved.id] ?? 0, Math.max(0, saved.steps.length - 1)), step = saved.steps[index];
    return <div className="homework-tutor-original-lesson"><div className="homework-tutor-step-caption"><span>第 {Math.min(index + 1, saved.steps.length)} / {saved.steps.length} 步</span></div>{step && <figure className="homework-tutor-step"><TutorVisual step={step} stepIndex={index} submission={submission} item={item} disabled={replyBlocked} onAnswer={value => void send("answer", value)} /><figcaption><HomeworkMathText text={step.text} /></figcaption></figure>}<div className="homework-tutor-controls"><Button size="compact" variant="quiet" disabled={index <= 0} onClick={() => setStepIndexes(previous => ({ ...previous, [saved.id]: Math.max(0, index - 1) }))}><ArrowLeft />上一步</Button><Button size="compact" variant="secondary" disabled={index >= saved.steps.length - 1} onClick={() => setStepIndexes(previous => ({ ...previous, [saved.id]: index + 1 }))}>下一步<ArrowRight /></Button></div>{saved.teachingScope === "original_image_guidance" && <p className="homework-tutor-source-note">{saved.sourceCheck?.status === "mismatch" ? "老师重新看原图，发现和先前识别有不同；这次按原图讲解。" : "老师直接看原图讲解，原作业的批改记录仍保留。"}</p>}{!saved.teachingQuality && saved.gradingReferenceComparison?.status === "conflict" && <p className="homework-tutor-source-note">参考结果有不同，老师陪你看原图核实</p>}{!saved.teachingQuality && saved.gradingReferenceComparison?.status === "unverified" && !!saved.gradingReferenceComparison.reason.trim() && <p className="homework-tutor-source-note">批改参考暂时无法核实，老师陪你看原图。</p>}</div>;
  }
  function childMessage(saved: Pick<TutorTurn, "mode" | "message">, key: string) {
    return <div key={key} className="homework-chat-message is-child" aria-label={saved.mode === "answer" ? "本次提交的答案" : "本次向老师提问"}><Image className="homework-chat-avatar" src="/images/space/student-avatar.png" width={36} height={36} alt="我" /><div className="homework-chat-bubble"><strong>{saved.mode === "answer" ? "你的答案：" : "你问："}</strong><HomeworkMathText text={saved.message} /></div></div>;
  }
  const showComposer = data?.enabled && (canReply || orderedTurns.some(saved => teacherTextReady(saved, item)));
  const acceptedReplyReady = !!acceptedRequestKey && orderedTurns.some(saved => saved.mode !== "explain" && saved.requestKey === acceptedRequestKey && saved.status === "ready" && teacherTextReady(saved, item));
  const unreadReply = !chatOpen && acceptedReplyReady && acceptedRequestKey !== acknowledgedRequestKey;
  const chatId = `homework-tutor-chat-${item.id}`;
  function openChat(mode: "followup" | "answer") {
    if (composerLocked) return;
    if (!replyBlocked) { setReplyMode(mode); setMessage(""); }
    setChatOpen(true);
  }
  function closeChat() {
    if (composerLocked) return;
    voice.stop();
    if (acceptedReplyReady) setAcknowledgedRequestKey(acceptedRequestKey);
    setChatOpen(false);
  }
  return <section ref={tutorRoot} className="homework-ai-tutor" aria-label={homeworkStudentCopy.tutorRegion} aria-busy={busy || preparing && !orderedTurns.some(saved => teacherTextReady(saved, item))}>
    <Button variant="quiet" size="compact" disabled={busy} onClick={() => { voice.stop(); onBack(); }}><ArrowLeft />{completedReview ? "换一道题" : "回到原作业"}</Button>
    <div className={`homework-tutor-layout${chatOpen ? " is-chat-open" : " is-chat-closed"}`}><aside className={`homework-tutor-original${originalExpanded ? " is-expanded" : ""}`} aria-label="原题与订正操作">
      <div className="homework-tutor-study-scroll">
        <div className="homework-tutor-reference-preview"><HomeworkQuestionPicture submission={submission} item={item} alt="正在订正的原题小图" /><Button size="compact" variant="secondary" aria-expanded={originalExpanded} onClick={() => setOriginalExpanded(value => !value)}><BookOpen />{originalExpanded ? "收起原题" : "展开原题"}<ChevronDown /></Button></div>
        <div className="homework-tutor-original-content">{completedReview ? <HomeworkReviewExplorer key={`${submission.id}:${item.id}:${item.revision}`} submission={submission} item={item} /> : <HomeworkOriginalQuestion submission={submission} item={item} neutralAnswer />}<HomeworkGradingDetails item={item} /></div>
        <section className="homework-tutor-explanation" aria-label="原题讲解">
          <div className="homework-tutor-explanation-heading"><Image src={teacher.avatarPath} width={32} height={32} alt="老师" /><h2>原题讲解</h2>{safeExplain && audioControls(safeExplain)}</div>
          {error && !chatOpen && <div role="alert" className="homework-tutor-error"><p>{error}</p>{!hasReadStatusAction && <Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />查看准备情况</Button>}</div>}
          {!data ? !error && <p role="status">正在打开已保存的讲解…</p> : !data.enabled ? <p>老师暂时还没准备好，请回到原作业查看</p> : !latestExplain && <div className="homework-tutor-lesson-start"><Button size="compact" disabled={blocked || explanationBlocked} onClick={() => void send("explain")}><Volume2 />{isEssay ? "老师看看我的作文" : "老师讲讲这道题"}</Button></div>}
          {latestExplain && latestExplain !== safeExplain && teacherContent(latestExplain)}
          {safeExplain && teacherContent(safeExplain)}
        </section>
      </div>
      <div className="homework-tutor-actions">
        {(showComposer || !!conversationTurns.length) && <div className="homework-tutor-reply-mode" role="group" aria-label="提问或提交订正答案"><Button size="compact" variant={replyMode === "followup" ? "secondary" : "quiet"} disabled={composerLocked || chatOpen && replyBlocked} aria-pressed={replyMode === "followup"} aria-expanded={chatOpen} aria-controls={chatId} onClick={() => openChat("followup")}><MessageCircle />问老师</Button>{showComposer && <Button size="compact" variant={replyMode === "answer" ? "secondary" : "quiet"} disabled={composerLocked || chatOpen && replyBlocked} aria-pressed={replyMode === "answer"} aria-expanded={chatOpen} aria-controls={chatId} onClick={() => openChat("answer")}><Hand />提交订正答案</Button>}</div>}
        {unreadReply && <p className="homework-tutor-unread" role="status"><MessageCircle aria-hidden="true" />老师回复了</p>}
        {correction ? <HomeworkCorrectionStatus correction={correction} /> : turn && teacherTextReady(turn, item) && turn.assessment && <p className="homework-tutor-assessment"><BookOpen aria-hidden="true" />{turn.assessment.status === "needs_confirmation" ? "原题有些地方还没看清，老师会陪你看图，不直接判断对错" : "这次是老师的讲解，听过不等于已经独立订正"}</p>}
        <HomeworkPaperCompletion key={`${item.id}:${item.revision}`} submission={submission} item={item} correction={correction} disabled={busy || composerLocked} onLockChange={setMarkLocked} onData={value => { const current = [...value.submission.items, ...value.submission.tutorItems, ...(value.submission.originalPaperItems ?? [])].find(saved => saved.id === item.id); if (current?.studentCorrection) setData(saved => saved ? { ...saved, correction: current.studentCorrection } : saved); onData?.(value); }} />
      </div>
    </aside><div id={chatId} className="homework-tutor-lesson homework-tutor-chat" hidden={!chatOpen}>
      <div ref={chatHeader} className="homework-tutor-teacher"><Image src={teacher.avatarPath} width={44} height={44} alt={isEssay ? homeworkStudentCopy.teacherEssayAlt : homeworkStudentCopy.teacherQuestionAlt} /><div><h2>问问老师</h2><p>哪里不懂，接着问</p></div><Button size="compact" variant="quiet" disabled={composerLocked} aria-expanded={chatOpen} aria-controls={chatId} onClick={closeChat}><ChevronDown />收起追问</Button></div>
      <div className="homework-chat-log" ref={chatLog} role="log" aria-label="和老师的对话" aria-live="polite" aria-relevant="additions text" onScroll={event => { const log = event.currentTarget; followsLatest.current = log.scrollHeight - log.scrollTop - log.clientHeight < 96; if (followsLatest.current) setShowLatest(false); }}>
        {!conversationTurns.length && !outgoingReply && <div className="homework-chat-welcome"><Image src={teacher.avatarPath} width={48} height={48} alt="老师" /><p>不懂的地方，直接问老师。</p></div>}
        {conversationTurns.map(saved => <div className="homework-chat-exchange" data-turn-id={saved.id} key={saved.id}>{saved.message.trim() && childMessage(saved, `${saved.id}:child`)}<article className="homework-chat-message is-teacher" aria-label={saved.mode === "answer" ? "老师对答案的回复" : "老师对问题的回复"} data-speaking={voice.playingTurnId === saved.id}><Image className="homework-chat-avatar" src={teacher.avatarPath} width={36} height={36} alt="老师" /><div className="homework-chat-bubble">{teacherContent(saved)}</div></article></div>)}
        {outgoingReply && <div className="homework-chat-exchange is-outgoing" data-request-key={outgoingReply.key}>{childMessage(outgoingReply, "outgoing:child")}<article className="homework-chat-message is-teacher" aria-label="老师正在回应这次消息"><Image className="homework-chat-avatar" src={teacher.avatarPath} width={36} height={36} alt="老师" /><div className="homework-chat-bubble"><div className="homework-tutor-reply-status" role="status">{outgoingReply.state === "sending" ? <LoaderCircle aria-hidden="true" /> : <HelpCircle aria-hidden="true" />}<p>{outgoingReply.state === "rejected" ? outgoingReply.mode === "answer" ? "这次答案还没提交成功，答案已保留。" : "问题没有发送成功，原问题已保留。" : outgoingReply.state === "unknown" ? outgoingReply.mode === "answer" ? "正在核实这次作答的处理结果，答案已保留。" : "这次问题的处理结果还在核实，原问题已保留。" : outgoingReply.mode === "answer" ? "老师正在核对你的答案…" : "老师正在回答这个问题…"}</p>{outgoingReply.state === "unknown" && <Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />查看回答状态</Button>}</div></div></article></div>}
        {error && chatOpen && <div role="alert" className="homework-tutor-error"><p>{error}</p>{!hasReadStatusAction && <Button size="compact" variant="quiet" onClick={() => void refresh()}><RefreshCw />查看准备情况</Button>}</div>}
        {limitReached && <p role="status" className="homework-tutor-source-note">这份原题的讲解次数已用完，已经核对好的讲解和声音可以继续看、继续听。</p>}
        {showLatest && <Button className="homework-chat-latest" size="compact" variant="secondary" onClick={scrollToLatest}><ArrowDown />看看最新回复</Button>}
        <div ref={chatEnd} className="homework-chat-end" />
      </div>
      {showComposer && <div className="homework-chat-composer">{reviewedTemplate ? replyMode === "followup" ? <Button size="compact" variant="quiet" disabled={replyBlocked || composerLocked} onClick={() => void send("followup", simplerExplanation)}><HelpCircle />再讲简单一点</Button> : <form className="homework-tutor-text-question" onSubmit={event => { event.preventDefault(); void send("answer", message); }}><label htmlFor={`tutor-answer-${item.id}`}><Hand />填一个数字给老师</label><Input id={`tutor-answer-${item.id}`} type="text" inputMode="numeric" pattern="[0-9]*" maxLength={3} value={message} disabled={replyBlocked} onChange={event => { if (/^\d*$/.test(event.target.value)) setMessage(event.target.value); }} /><Button size="compact" disabled={replyBlocked || !/^\d+$/.test(message)} type="submit"><Send />告诉老师我的数字</Button></form> : <HomeworkQuestionRecorder key={`${item.id}:${item.revision}:${replyMode}`} presentation="chat" active={chatOpen} endpoint={`${endpoint}/transcribe`} itemRevision={item.revision} disabled={replyBlocked} intent={replyMode === "answer" ? "answer" : "question"} actionLabel={replyMode === "answer" ? "提交答案" : "发送问题"} allowTyping onStartRecording={stopVoice} resetKey={acceptedRequestKey} onLockChange={setComposerLocked} onQuestion={value => void send(replyMode, value)} />}</div>}
    </div></div>
  </section>;
}
