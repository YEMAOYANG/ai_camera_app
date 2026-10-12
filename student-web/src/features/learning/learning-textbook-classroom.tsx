"use client";

import { Backpack, RotateCcw } from "lucide-react";
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
    void fetch(`/api/learning/textbooks/courses/${encodeURIComponent(contentKey)}/launch`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", signal: controller.signal,
    }).then(async response => {
      const payload = await response.json();
      if (response.status === 401) { router.replace("/unlock"); return; }
      if (!response.ok) throw new Error(payload.message || "课堂暂时打不开");
      const result = textbookLaunchSchema.parse(payload);
      if (result.contentKey !== contentKey) throw new Error("课程身份已变化，请返回目录");
      if (!controller.signal.aborted) { setEntry(result); setError(""); }
    }).catch((caught: unknown) => {
      if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "课堂暂时打不开");
    });
    return () => controller.abort();
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
  return <SchoolbagShell student={student} className="textbook-classroom"
    navigation={<Link href={back}><Backpack size={32} aria-hidden="true" /><span>回到课本</span></Link>}>
    {error ? <div className="textbook-state" role="alert"><h1>暂时没有打开课堂</h1><p>{error}</p>
      <Button onClick={() => retry(value => value + 1)}><RotateCcw size={18} aria-hidden="true" />重新进入</Button></div>
      // The authenticated, origin-pinned runtime owns storage and nested
      // interactive sandboxes, like FullOpenMaicClassroom. Keep that reviewed
      // isolation inside the runtime instead of sandboxing the application.
      : entry ? <iframe ref={frame} className="textbook-classroom-frame" key={entry.launchUrl} src={entry.launchUrl}
        title={entry.title} allow="microphone; autoplay; fullscreen" allowFullScreen referrerPolicy="no-referrer" />
      : <div className="textbook-state" role="status"><h1>正在翻开课本…</h1><p>准备好，一起看图、听故事。</p></div>}
  </SchoolbagShell>;
}
