"use client";

import { Backpack, CircleAlert, RotateCcw } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main id="main-content" className="mira-ui-surface student-session-screen">
      <div className="student-session-state" role="alert">
        <span className="student-session-icon" aria-hidden="true"><CircleAlert size={28} strokeWidth={1.6} /></span>
        <h1>暂时没有连接上</h1>
        <p>再试一次，或先回到书包。</p>
        <div className="flex flex-wrap justify-center gap-3 pt-2">
          <Button size="compact" onClick={retry}><RotateCcw aria-hidden="true" />再试一次</Button>
          <Button size="compact" variant="secondary" asChild><Link href="/learning"><Backpack aria-hidden="true" />回到书包</Link></Button>
        </div>
      </div>
    </main>
  );
}
