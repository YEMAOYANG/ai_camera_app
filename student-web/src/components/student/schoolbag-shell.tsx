"use client";

import { Backpack, Pause, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Student } from "@/lib/contracts/student-session";
import { useSchoolbagMotion } from "@/components/schoolbag/schoolbag-motion";

export function SchoolbagShell({ children, className = "", home = false, navigation, tools, onRest }: {
  student?: Student; children: ReactNode; className?: string; home?: boolean;
  navigation?: ReactNode; tools?: ReactNode; onRest?: () => void;
}) {
  const router = useRouter();
  const { returnHome, busy } = useSchoolbagMotion();
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState("");
  function goHome(event: React.MouseEvent<HTMLAnchorElement>) {
    if (home || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); if (!busy) returnHome();
  }
  async function rest() {
    if (locking) return;
    onRest?.();
    setLocking(true); setError("");
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error();
      router.replace("/unlock"); router.refresh();
    } catch { setError("暂时无法锁定，请再试一次"); setLocking(false); }
  }
  return <div className={`schoolbag-shell ${className}`}>
    <header className="schoolbag-header">
      <div className="schoolbag-header-start">
        <Link className="schoolbag-brand" href="/learning" aria-label="暖瞳学习首页" aria-current={home ? "page" : undefined} onClick={goHome}><span><Backpack size={26} strokeWidth={1.6} aria-hidden="true" /></span><strong>暖瞳</strong></Link>
        {navigation && <nav className="schoolbag-context-nav" aria-label="学生导航">{navigation}</nav>}
      </div>
      <div className="schoolbag-account">{tools}
        <button type="button" className="schoolbag-rest" onClick={() => void rest()} disabled={locking} aria-label={locking ? "正在锁定" : "休息一下"}>{locking ? <LoaderCircle size={19} aria-hidden="true" /> : <Pause size={19} aria-hidden="true" />}<span>休息一下</span></button>
      </div>
    </header>
    {error && <p className="schoolbag-lock-error" role="alert">{error}</p>}
    <main id="main-content" className="schoolbag-main">{children}</main>
  </div>;
}
