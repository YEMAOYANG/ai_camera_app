"use client";
import { Keyboard, Mic, Send, Square, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { homeworkTranscriptionSchema } from "@/lib/contracts/homework-tutor";

/** The browser records only; recognition is always performed by the server's Qwen ASR. */
export function encodeHomeworkQuestionWav(channels: Float32Array[], sourceRate: number) {
  if (!channels.length || !Number.isFinite(sourceRate) || sourceRate < 8000 || channels.some(channel => channel.length !== channels[0].length)) throw new Error("这段录音没有保存好，请再录一次");
  const seconds = channels[0].length / sourceRate;
  if (seconds <= 0 || seconds > 60.1) throw new Error("请录一分钟以内的一小段话");
  const samples = Math.min(60 * 16000, Math.floor(seconds * 16000));
  const bytes = new ArrayBuffer(44 + samples * 2), view = new DataView(bytes);
  const word = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  word(0, "RIFF"); view.setUint32(4, bytes.byteLength - 8, true); word(8, "WAVE"); word(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); word(36, "data"); view.setUint32(40, samples * 2, true);
  for (let i = 0; i < samples; i++) {
    const source = i * sourceRate / 16000, start = Math.floor(source), ratio = source - start;
    const sample = channels.reduce((sum, channel) => sum + channel[start] * (1 - ratio) + channel[Math.min(start + 1, channel.length - 1)] * ratio, 0) / channels.length;
    const clamped = Math.max(-1, Math.min(1, sample)); view.setInt16(44 + i * 2, Math.round(clamped * (clamped < 0 ? 32768 : 32767)), true);
  }
  return new Blob([bytes], { type: "audio/wav" });
}
type Clip = { wav: Blob; url: string; key: string };
export function HomeworkQuestionRecorder({ endpoint, itemRevision, disabled, onQuestion, actionLabel = "问老师", intent = "question", allowTyping = false, onLockChange, onStartRecording, resetKey, presentation = "standard", active = true }: { endpoint: string; itemRevision: number; disabled?: boolean; actionLabel?: string; intent?: "question" | "answer"; allowTyping?: boolean; onLockChange?: (locked: boolean) => void; onStartRecording?: () => void; resetKey?: string; presentation?: "standard" | "chat"; active?: boolean; onQuestion: (value: string) => void }) {
  const answering = intent === "answer";
  const [inputMethod, setInputMethod] = useState<"voice" | "text">("voice");
  const [state, setState] = useState<"idle" | "opening" | "recording" | "converting" | "recorded" | "working" | "unknown" | "failed" | "ready" | "sent">("idle");
  const [clip, setClip] = useState<Clip | null>(null), [transcript, setTranscript] = useState(""), [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null), stream = useRef<MediaStream | null>(null), timer = useRef<ReturnType<typeof setTimeout> | null>(null), alive = useRef(true), url = useRef<string | null>(null), converting = useRef(false);
  const opening = useRef(false), submitting = useRef(false);
  const clipGeneration = useRef(0), activeClipKey = useRef<string | null>(null);
  const reading = useRef<{ key: string; generation: number } | null>(null);
  const clipAudio = useRef<HTMLAudioElement>(null);
  useEffect(() => { if (!active) clipAudio.current?.pause(); }, [active]);
  const lastResetKey = useRef(resetKey);
  const inputLocked = ["opening", "recording", "converting", "working", "unknown"].includes(state);
  useEffect(() => { onLockChange?.(inputLocked); return () => onLockChange?.(false); }, [inputLocked, onLockChange]);
  const invalidateClipRequests = useCallback(() => { clipGeneration.current += 1; activeClipKey.current = null; reading.current = null; submitting.current = false; }, []);
  const currentClipRequest = (identity: { key: string; generation: number }) => alive.current && activeClipKey.current === identity.key && clipGeneration.current === identity.generation;
  const release = useCallback(() => { if (timer.current) clearTimeout(timer.current); timer.current = null; stream.current?.getTracks().forEach(track => track.stop()); stream.current = null; }, []);
  useEffect(() => { alive.current = true; return () => { alive.current = false; invalidateClipRequests(); if (recorder.current?.state === "recording") recorder.current.stop(); release(); if (url.current) URL.revokeObjectURL(url.current); }; }, [invalidateClipRequests, release]);
  useEffect(() => {
    if (!resetKey || lastResetKey.current === resetKey) return;
    lastResetKey.current = resetKey;
    invalidateClipRequests();
    // Clear only after the tutor has matched this send's saved receipt. Keep
    // the child's chosen input method; lost/rejected requests retain the draft.
    const timer = window.setTimeout(() => { clipAudio.current?.pause(); if (url.current) URL.revokeObjectURL(url.current); url.current = null; setClip(null); setTranscript(""); setState("idle"); setError(""); }, 0);
    return () => clearTimeout(timer);
  }, [invalidateClipRequests, resetKey]);
  function receive(value: unknown) {
    const result = homeworkTranscriptionSchema.parse(value).transcription;
    if (result.status === "ready" && result.transcript.trim()) { setTranscript(result.transcript); setState("ready"); setError(""); }
    else if (result.status === "working" || result.status === "queued") { setState("working"); setError(""); }
    else if (result.status === "unknown") { setState("unknown"); setError("这段话的处理结果还在核实，不会重新提交录音"); }
    else { setState("failed"); setError("这段话没有听清，可以重新录一小段；旧录音不会自动重发"); }
  }
  async function query(savedClip = clip) {
    if (!savedClip || reading.current) return;
    const identity = { key: savedClip.key, generation: clipGeneration.current };
    if (!currentClipRequest(identity)) return;
    reading.current = identity;
    try {
      const response = await fetch(`${endpoint}?${new URLSearchParams({ itemRevision: String(itemRevision), idempotencyKey: savedClip.key })}`, { cache: "no-store" });
      const value = await response.json();
      if (!currentClipRequest(identity) || reading.current !== identity) return;
      if (!response.ok) throw new Error(value.message || "录音状态还没核实，请稍后查看");
      receive(value);
    } catch (error) {
      if (currentClipRequest(identity) && reading.current === identity) throw error;
    } finally { if (reading.current === identity) reading.current = null; }
  }
  useEffect(() => {
    if (state !== "working" || !clip) return;
    const poll = window.setInterval(() => { if (!document.hidden && !submitting.current) void query(clip).catch(() => {}); }, 4000);
    return () => clearInterval(poll);
  // query only reads the current clip's saved identity; it never submits audio.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, clip, endpoint, itemRevision]);
  async function start() {
    if (disabled || opening.current || converting.current || ["recording", "working", "unknown"].includes(state)) return;
    invalidateClipRequests();
    const recordingGeneration = clipGeneration.current;
    onStartRecording?.();
    clipAudio.current?.pause();
    setError("");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined" || typeof AudioContext === "undefined") { setError(`需要在安全连接中使用麦克风，请用 HTTPS 或本机 localhost 打开学生端${allowTyping ? "；现在可以打字" : ""}`); if (allowTyping) setInputMethod("text"); return; }
    opening.current = true; setState("opening");
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (!alive.current || recordingGeneration !== clipGeneration.current) { mic.getTracks().forEach(track => track.stop()); return; }
      stream.current = mic;
      const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus"].find(type => MediaRecorder.isTypeSupported(type));
      const recording = new MediaRecorder(mic, mime ? { mimeType: mime } : undefined), chunks: BlobPart[] = [];
      recorder.current = recording;
      recording.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recording.onerror = () => { release(); if (alive.current && recordingGeneration === clipGeneration.current) { setState("idle"); setError("麦克风录音中断了，请再试一次"); } };
      recording.onstop = () => {
        release(); if (!alive.current || recordingGeneration !== clipGeneration.current) return;
        converting.current = true; setState("converting");
        void (async () => {
          let context: AudioContext | null = null;
          try {
            context = new AudioContext();
            const raw = new Blob(chunks, { type: recording.mimeType }), decoded = await context.decodeAudioData(await raw.arrayBuffer());
            const wav = encodeHomeworkQuestionWav(Array.from({ length: decoded.numberOfChannels }, (_, i) => decoded.getChannelData(i)), decoded.sampleRate);
            if (!alive.current || recordingGeneration !== clipGeneration.current) return;
            if (url.current) URL.revokeObjectURL(url.current); url.current = URL.createObjectURL(wav);
            const saved = { wav, url: url.current, key: crypto.randomUUID() };
            activeClipKey.current = saved.key;
            setClip(saved); setTranscript(""); setState("recorded");
          } catch (error) { if (alive.current && recordingGeneration === clipGeneration.current) { setState("idle"); setError(error instanceof Error ? error.message : "这段录音没有保存好"); } }
          finally { converting.current = false; if (context) { try { await context.close(); } catch { /* Closing an already unavailable decoder must not lock the input. */ } } }
        })();
      };
      recording.start(); setState("recording"); timer.current = setTimeout(() => { if (recording.state === "recording") recording.stop(); }, 60_000);
    } catch (failure) { release(); if (alive.current && recordingGeneration === clipGeneration.current) { setState("idle"); const name = failure && typeof failure === "object" && "name" in failure ? failure.name : ""; setError(`${name === "NotFoundError" || name === "DevicesNotFoundError" ? "没有找到麦克风" : name === "NotAllowedError" || name === "PermissionDeniedError" ? "麦克风权限还没打开" : "麦克风没打开"}${allowTyping ? "，可以先打字告诉老师" : "，请允许录音后再试一次"}`); if (allowTyping) setInputMethod("text"); } }
    finally { opening.current = false; }
  }
  async function transcribe() {
    if (!clip || state !== "recorded" || submitting.current) return;
    const identity = { key: clip.key, generation: clipGeneration.current };
    if (!currentClipRequest(identity)) return;
    submitting.current = true; setState("working"); setError("");
    let dispatched = false;
    try {
      const form = new FormData(); form.set("audio", clip.wav, "question.wav"); form.set("itemRevision", String(itemRevision)); form.set("idempotencyKey", clip.key);
      dispatched = true;
      const response = await fetch(endpoint, { method: "POST", body: form }); const value = await response.json();
      if (!currentClipRequest(identity)) return;
      if (!response.ok) { if (response.status >= 400 && response.status < 500) { setState("failed"); setError(value.message || "录音没有提交成功，可以重新录一小段"); return; } throw new Error(value.message || "正在核实这段录音"); }
      receive(value);
    } catch (error) {
      if (!currentClipRequest(identity)) return;
      if (!dispatched) { setState("failed"); setError("录音没有提交，可以重新录一小段"); return; }
      try { await query(); } catch { if (currentClipRequest(identity)) { setState("unknown"); setError(error instanceof Error ? error.message : "正在核实录音结果，不会重复提交"); } }
    }
    finally { if (currentClipRequest(identity)) submitting.current = false; }
  }
  const locked = disabled || inputLocked;
  const submit = () => { const clean = transcript.trim(); if (!clean || disabled || inputLocked || state === "sent") return; invalidateClipRequests(); clipAudio.current?.pause(); onQuestion(clean); setState("sent"); };
  const fieldId = `homework-reply-${intent}-${itemRevision}`;
  if (presentation === "chat") return <div className="homework-question-recorder homework-question-recorder-chat" aria-label={answering ? "说出自己的答案" : "说出自己的问题"} aria-busy={state === "working" || state === "converting"}>
    <div className="homework-recorder-chat-row">
      {allowTyping && <Button className="homework-recorder-mode-toggle" size="icon" variant="quiet" disabled={locked} aria-label={inputMethod === "voice" ? "切换到打字" : "切换到语音"} title={inputMethod === "voice" ? "切换到打字" : "切换到语音"} onClick={() => setInputMethod(inputMethod === "voice" ? "text" : "voice")}>{inputMethod === "voice" ? <Keyboard /> : <Mic />}</Button>}
      {inputMethod === "text" ? <form className="homework-reply-text homework-reply-text-chat" onSubmit={event => { event.preventDefault(); submit(); }}><label className="sr-only" htmlFor={fieldId}>{answering ? "写下你的答案和想法" : "写下你想问的"}</label><textarea id={fieldId} value={transcript} maxLength={1000} disabled={locked} placeholder={answering ? "写下你的答案和想法…" : "把问题写在这里…"} onChange={event => { setTranscript(event.target.value); if (state === "sent") setState("idle"); }} rows={1} /><Button size="compact" type="submit" disabled={locked || state === "sent" || !transcript.trim()}><Send />{actionLabel}</Button></form>
        : <div className="homework-recorder-chat-voice">{state === "recording" ? <Button size="compact" onClick={() => recorder.current?.stop()}><Square fill="currentColor" />我说完了</Button> : <Button size="compact" variant="secondary" disabled={locked} onClick={() => void start()}><Mic />{clip ? "重新说" : answering ? "说出我的答案" : "说出我的问题"}</Button>}</div>}
    </div>
    {inputMethod === "voice" && (state !== "idle" || clip) && <div className="homework-recorder-chat-details">
      {state === "opening" || state === "recording" || state === "working" || state === "converting" ? <p role="status">{state === "opening" ? "正在打开麦克风…" : state === "recording" ? "正在听你说，点方块说完" : state === "working" ? answering ? "老师正在听你的答案…" : "老师正在听你的问题…" : "正在保存录音…"}</p> : null}
      {state === "recorded" && <div className="homework-tutor-controls"><Button size="compact" disabled={disabled} onClick={() => void transcribe()}><Send />让老师听听</Button></div>}
      {state === "unknown" && <div className="homework-tutor-controls"><Button size="compact" variant="secondary" onClick={() => void query().catch(e => setError(e instanceof Error ? e.message : "录音状态还没打开"))}><RefreshCw />查看录音状态</Button></div>}
      {clip && <audio ref={clipAudio} controls src={clip.url} aria-label={answering ? "听听我刚才说的答案" : "听听我刚才说的问题"} />}
      {state === "ready" && <div className="homework-transcript-confirm"><label htmlFor={fieldId}>老师听到的是，可以改一改</label><textarea id={fieldId} aria-label={answering ? "确认识别的答案" : "确认识别的问题"} value={transcript} maxLength={1000} disabled={disabled} onChange={event => setTranscript(event.target.value)} rows={2} /><Button size="compact" disabled={disabled || !transcript.trim()} onClick={submit}><Send />{actionLabel}</Button><Button size="compact" variant="quiet" disabled={disabled} onClick={() => { setClip(null); setTranscript(""); setState("idle"); }}><Trash2 />重新录</Button></div>}
      {state === "sent" && <p>你刚才说的是：{transcript}</p>}
    </div>}
    {error && <p role="alert">{error}</p>}
  </div>;
  return <div className="homework-question-recorder" aria-label={answering ? "说出自己的答案" : "说出自己的问题"} aria-busy={state === "working" || state === "converting"}>
    <div className={`homework-recorder-visual${state === "recording" ? " is-recording" : ""}`} aria-hidden="true">{inputMethod === "text" ? <Keyboard /> : <Mic />}<span /><span /><span /><span /><span /></div>
    <div>{allowTyping && <div className="homework-reply-input-method" role="group" aria-label="选择说话或打字"><Button size="compact" variant={inputMethod === "voice" ? "secondary" : "quiet"} disabled={locked} aria-pressed={inputMethod === "voice"} onClick={() => setInputMethod("voice")}><Mic />语音</Button><Button size="compact" variant={inputMethod === "text" ? "secondary" : "quiet"} disabled={locked} aria-pressed={inputMethod === "text"} onClick={() => setInputMethod("text")}><Keyboard />打字</Button></div>}
      {inputMethod === "text" ? <form className="homework-reply-text" onSubmit={event => { event.preventDefault(); submit(); }}><label htmlFor={fieldId}>{answering ? "写下你的答案和想法" : "写下你想问的"}</label><textarea id={fieldId} value={transcript} maxLength={1000} disabled={locked} onChange={event => { setTranscript(event.target.value); if (state === "sent") setState("idle"); }} rows={2} /><Button size="compact" type="submit" disabled={locked || state === "sent" || !transcript.trim()}><Send />{actionLabel}</Button></form> : <><p>{state === "recording" ? "正在听你说，点方块说完" : state === "working" ? answering ? "老师正在听你的答案…" : "老师正在听你的问题…" : state === "converting" ? "正在保存录音…" : answering ? "看看原图，把你的答案说给老师听" : "你还想问什么？说给老师听"}</p>
      <div className="homework-tutor-controls">{state === "recording" ? <Button size="compact" onClick={() => recorder.current?.stop()}><Square fill="currentColor" />我说完了</Button> : <Button size="compact" variant="secondary" disabled={locked} onClick={() => void start()}><Mic />{clip ? "重新说" : answering ? "说出我的答案" : "说出我的问题"}</Button>}
        {state === "recorded" && <Button size="compact" disabled={disabled} onClick={() => void transcribe()}><Send />让老师听听</Button>}
        {state === "unknown" && <Button size="compact" variant="secondary" onClick={() => void query().catch(e => setError(e instanceof Error ? e.message : "录音状态还没打开"))}><RefreshCw />查看录音状态</Button>}
      </div>
      {clip && <audio ref={clipAudio} controls src={clip.url} aria-label={answering ? "听听我刚才说的答案" : "听听我刚才说的问题"} />}
      {state === "ready" && <div className="homework-transcript-confirm"><label htmlFor={fieldId}>老师听到的是，可以改一改</label><textarea id={fieldId} aria-label={answering ? "确认识别的答案" : "确认识别的问题"} value={transcript} maxLength={1000} disabled={disabled} onChange={event => setTranscript(event.target.value)} rows={2} /><Button size="compact" disabled={disabled || !transcript.trim()} onClick={submit}><Send />{actionLabel}</Button><Button size="compact" variant="quiet" disabled={disabled} onClick={() => { setClip(null); setTranscript(""); setState("idle"); }}><Trash2 />重新录</Button></div>}
      {state === "sent" && <p>你刚才说的是：{transcript}</p>}
      </>}
      {error && <p role="alert">{error}</p>}
    </div>
  </div>;
}
