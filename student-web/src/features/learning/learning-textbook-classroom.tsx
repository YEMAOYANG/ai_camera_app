"use client";

import { Backpack, BookOpen, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import { textbookLaunchSchema, textbookSectionProgressSchema } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";
import { TEXTBOOK_CHECK_ENTRY, textbookCoursePath } from "./textbook-navigation";

const FRAME_SLOW_NOTICE_MS = 12_000;
const FRAME_READY_TIMEOUT_MS = 50_000;

export function LearningTextbookClassroom({ student, contentKey, requestedEntry }: {
  student: Student; contentKey: string; requestedEntry?: string;
}) {
  const router = useRouter();
  const frame = useRef<HTMLIFrameElement>(null);
  const [entry, setEntry] = useState<z.infer<typeof textbookLaunchSchema>>();
  const [error, setError] = useState("");
  const [revision, retry] = useState(0);
  const [frameReady, setFrameReady] = useState(false);
  const [frameLoad, setFrameLoad] = useState<"loading" | "slow" | "timed-out">("loading");
  const [progress, setProgress] = useState<z.infer<typeof textbookSectionProgressSchema>>();
  const frameTimedOut = frameLoad === "timed-out";
  const launchEndpoint = `/api/learning/textbooks/courses/${encodeURIComponent(contentKey)}/launch`;
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      controller.abort();
      setError("打开课堂花的时间有点久，请再试一次。");
    }, 30_000);
    void fetch(launchEndpoint, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestedEntry ? { entry: requestedEntry } : {}), signal: controller.signal,
    }).then(async response => {
      const payload = await response.json();
      if (controller.signal.aborted) return;
      if (response.status === 401) { router.replace("/unlock"); return; }
      if (!response.ok) throw new Error(payload.message || "课堂暂时打不开");
      const result = textbookLaunchSchema.parse(payload);
      if (result.contentKey !== contentKey || (requestedEntry && result.entry !== requestedEntry))
        throw new Error("课程身份已变化，请返回目录");
      if (!controller.signal.aborted) {
        setFrameReady(false); setFrameLoad("loading"); setEntry(result);
        setProgress(result.sectionProgress); setError("");
      }
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "课堂暂时打不开");
    }).finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [contentKey, launchEndpoint, requestedEntry, revision, router]);
  useEffect(() => {
    if (!entry) return;
    const origin = new URL(entry.launchUrl).origin;
    const ping = () => frame.current?.contentWindow?.postMessage({ type: 'mira.textbook.ready-ping' }, origin);
    const notice = window.setTimeout(() => setFrameLoad("slow"), FRAME_SLOW_NOTICE_MS);
    const timeout = window.setTimeout(() => setFrameLoad("timed-out"), FRAME_READY_TIMEOUT_MS);
    const interval = window.setInterval(ping, 1_000);
    const clearTimers = () => {
      window.clearTimeout(notice); window.clearTimeout(timeout); window.clearInterval(interval);
    };
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.origin !== origin) return;
      if (event.data?.type === 'mira.textbook.close') router.push('/learning');
      if (event.data?.type === 'mira.textbook.ready') {
        clearTimers(); setFrameLoad("loading"); setFrameReady(true);
      }
    };
    window.addEventListener('message', receive);
    ping();
    return () => { clearTimers(); window.removeEventListener('message', receive); };
  }, [entry, router]);
  const section = progress?.sections.find(item => item.nodeId === entry?.entry);
  const checkReady = progress?.checkReady === true;
  useEffect(() => {
    if (!entry?.entry || entry.entry === TEXTBOOK_CHECK_ENTRY || !frameReady || checkReady) return;
    const controller = new AbortController();
    let running = false;
    const refresh = async () => {
      if (document.hidden || running) return;
      running = true;
      try {
        const query = new URLSearchParams({ learningSessionId: entry.learningSessionId });
        const response = await fetch(`${launchEndpoint}?${query}`, { signal: controller.signal, cache: "no-store" });
        if (response.ok) {
          const next = textbookSectionProgressSchema.parse(await response.json());
          if (!controller.signal.aborted) setProgress(next);
        }
      } catch { /* Keep the last verified progress and retry while this tab is visible. */ }
      finally { running = false; }
    };
    void refresh();
    const interval = window.setInterval(() => void refresh(), 4_000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller.abort(); window.clearInterval(interval);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [checkReady, entry, frameReady, launchEndpoint]);
  const back = entry ? `/learning/textbooks?${new URLSearchParams({ editionId: entry.editionId, revisionId: entry.revisionId, ...(entry.unitId ? { unitId: entry.unitId } : {}) })}` : "/learning";
  const nextSection = progress?.sections.find(item => item.nodeId !== entry?.entry && !item.listened);
  const pauseBeforeRest = () => {
    if (entry) frame.current?.contentWindow?.postMessage(
      { type: "mira.textbook.pause" }, new URL(entry.launchUrl).origin,
    );
  };
  return <SchoolbagShell student={student} className="textbook-classroom" onRest={pauseBeforeRest} prefetchHome={false}
    navigation={<Link href={back} prefetch={false}><Backpack size={32} aria-hidden="true" /><span>回到课本</span></Link>}>
    {error ? <div className="textbook-state textbook-classroom-state" role="alert"><BookOpen className="textbook-classroom-state-icon" aria-hidden="true" /><h1>暂时没有打开课堂</h1><p>{error}</p>
      <Button onClick={() => { setError(""); retry(value => value + 1); }}><RotateCcw size={18} aria-hidden="true" />重新进入</Button></div>
      // The authenticated, origin-pinned runtime owns storage and nested
      // interactive sandboxes, like FullOpenMaicClassroom. Keep that reviewed
      // isolation inside the runtime instead of sandboxing the application.
      : entry ? <div className={`textbook-classroom-stage${section ? " textbook-classroom-stage--section" : ""}`}>
        {section && <section className="textbook-classroom-section" aria-label="课堂分段">
          <div><strong>{section.title}</strong><span>第 {section.firstPage}–{section.lastPage} 页</span>
            <span role="status">{section.listened ? "讲解已听完" : "听完两首诗的讲解，就能做小检查"}</span></div>
          {checkReady ? <Button asChild variant="secondary" size="compact">
            <Link prefetch={false} href={textbookCoursePath(contentKey, TEXTBOOK_CHECK_ENTRY)}>做共用小检查</Link>
          </Button> : section.listened && nextSection ? <Button asChild variant="secondary" size="compact">
            <Link prefetch={false} href={textbookCoursePath(contentKey, nextSection.nodeId)}>去学《{nextSection.title}》</Link>
          </Button> : null}
        </section>}
        <iframe ref={frame} className="textbook-classroom-frame" key={entry.launchUrl} src={entry.launchUrl}
          title={section?.title ?? (entry.entry === TEXTBOOK_CHECK_ENTRY ? "共用小检查" : entry.title)}
          allow="microphone; autoplay; fullscreen" allowFullScreen referrerPolicy="no-referrer"
          tabIndex={frameReady ? undefined : -1} aria-hidden={!frameReady} />
        {!frameReady && <div className="textbook-state textbook-classroom-state textbook-classroom-loading" role={frameTimedOut ? "alert" : "status"}>
          <BookOpen className="textbook-classroom-state-icon" aria-hidden="true" />
          <h1>{frameTimedOut ? "课堂暂时没有打开" : frameLoad === "slow" ? "课件还在加载…" : "正在翻开课本…"}</h1>
          <p>{frameTimedOut ? "打开课堂花的时间有点久，请再试一次。" : frameLoad === "slow" ? "准备好后会自动打开课堂。" : "准备好，一起看图、听故事。"}</p>
          {frameTimedOut && <Button onClick={() => { setEntry(undefined); setFrameLoad("loading"); retry(value => value + 1); }}><RotateCcw size={18} aria-hidden="true" />重新进入</Button>}
        </div>}
      </div>
      : <div className="textbook-state textbook-classroom-state" role="status"><BookOpen className="textbook-classroom-state-icon" aria-hidden="true" /><h1>正在翻开课本…</h1><p>准备好，一起看图、听故事。</p></div>}
  </SchoolbagShell>;
}
