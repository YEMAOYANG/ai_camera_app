"use client";

import { Backpack, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export function StudentSessionState({
  error,
  onRetry,
  title = "正在打开学习空间",
  description = "请稍等一下",
}: { error?: string; onRetry?: () => void; title?: string; description?: string }) {
  return <main id="main-content" className="mira-ui-surface student-session-screen">
    <section className="student-session-state" role={error ? "alert" : "status"} aria-busy={!error}>
      <span className="student-session-icon" aria-hidden="true">
        {error ? <WifiOff size={28} strokeWidth={1.6} /> : <Backpack size={28} strokeWidth={1.6} />}
      </span>
      <h1>{error ? "暂时没有连接上" : title}</h1>
      {error ? <>
        <p>{error}</p>
        <Button size="compact" className="student-session-retry" onClick={onRetry}>再试一次</Button>
      </> : <>
        <p>{description}</p>
        <div className="student-session-progress" aria-hidden="true"><i /></div>
      </>}
    </section>
  </main>;
}
