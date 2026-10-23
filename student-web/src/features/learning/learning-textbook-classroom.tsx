"use client";

import { Backpack, BookOpen, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import { textbookLaunchSchema } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

export function LearningTextbookClassroom({ student, contentKey }: { student: Student; contentKey: string }) {
  const router = useRouter();
  const frame = useRef<HTMLIFrameElement>(null);
  const [entry, setEntry] = useState<z.infer<typeof textbookLaunchSchema>>();
  const [error, setError] = useState("");
  const [revision, retry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      controller.abort();
      setError("打开课堂花的时间有点久，请再试一次。");
    }, 30_000);
    void fetch(`/api/learning/textbooks/courses/${encodeURIComponent(contentKey)}/launch`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: controller.signal,
    }).then(async response => {
      const payload = await response.json();
      if (controller.signal.aborted) return;
      if (response.status === 401) { router.replace("/unlock"); return; }
      if (!response.ok) throw new Error(payload.message || "课堂暂时打不开");
      const result = textbookLaunchSchema.parse(payload);
      if (result.contentKey !== contentKey) throw new Error("课程身份已变化，请返回目录");
      if (!controller.signal.aborted) { setEntry(result); setError(""); }
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "课堂暂时打不开");
    }).finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [contentKey, revision, router]);
  useEffect(() => {
    if (!entry) return;
    const origin = new URL(entry.launchUrl).origin;
    const receive = (event: MessageEvent) => {
      if (event.source === frame.current?.contentWindow && event.origin === origin
          && event.data?.type === 'mira.textbook.close') router.push('/learning');
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [entry, router]);
  const back = entry ? `/learning/textbooks?${new URLSearchParams({ editionId: entry.editionId, revisionId: entry.revisionId, ...(entry.unitId ? { unitId: entry.unitId } : {}) })}` : "/learning";
  const pauseBeforeRest = () => {
    if (entry) frame.current?.contentWindow?.postMessage(
      { type: "mira.textbook.pause" }, new URL(entry.launchUrl).origin,
    );
  };
  return <SchoolbagShell student={student} className="textbook-classroom" onRest={pauseBeforeRest}
    navigation={<Link href={back}><Backpack size={32} aria-hidden="true" /><span>回到课本</span></Link>}>
    {error ? <div className="textbook-state textbook-classroom-state" role="alert"><BookOpen className="textbook-classroom-state-icon" aria-hidden="true" /><h1>暂时没有打开课堂</h1><p>{error}</p>
      <Button onClick={() => { setError(""); retry(value => value + 1); }}><RotateCcw size={18} aria-hidden="true" />重新进入</Button></div>
      // The authenticated, origin-pinned runtime owns storage and nested
      // interactive sandboxes, like FullOpenMaicClassroom. Keep that reviewed
      // isolation inside the runtime instead of sandboxing the application.
      : entry ? <iframe ref={frame} className="textbook-classroom-frame" key={entry.launchUrl} src={entry.launchUrl}
        title={entry.title} allow="microphone; autoplay; fullscreen" allowFullScreen referrerPolicy="no-referrer" />
      : <div className="textbook-state textbook-classroom-state" role="status"><BookOpen className="textbook-classroom-state-icon" aria-hidden="true" /><h1>正在翻开课本…</h1><p>准备好，一起看图、听故事。</p></div>}
  </SchoolbagShell>;
}
