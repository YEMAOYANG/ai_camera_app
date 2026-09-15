"use client";
import { ArrowLeft, CirclePause, LoaderCircle } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { MiraMark } from "@/components/student/mira-mark";
import { SpaceAtmosphere } from "@/components/student/space-atmosphere";
import { SpaceNavigation, usePersistentSpaceNavigation } from "@/components/student/space-navigation";
import { gradeLabel } from "@/features/learning/learning-presenters";
import type { Student } from "@/lib/contracts/student-session";
import { cn } from "@/lib/utils";

export function SpaceShell({ student, active, children, className, scenic = false, showNav = true }: {
  student?: Student; active: "today" | "learning" | "practice"; children: ReactNode;
  className?: string; scenic?: boolean; showNav?: boolean;
}) {
  const router = useRouter();
  const persistentNavigation = usePersistentSpaceNavigation();
  const [locking, setLocking] = useState(false);
  const [lockError, setLockError] = useState("");
  async function lock() {
    setLocking(true); setLockError("");
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("暂时无法锁定，请再试一次");
      router.replace("/unlock"); router.refresh();
    } catch { setLockError("暂时无法锁定，请再试一次"); setLocking(false); }
  }
  return <div className={cn("space-shell", scenic && "space-shell--scenic", student?.gradeCode && /^primary_[12]$/.test(student.gradeCode) && "space-grade-lower", !showNav && "space-shell--no-nav", className)}>
    {scenic && <div className="space-scenery" aria-hidden="true"><Image src="/images/space/hero-space.png" alt="" fill priority sizes="100vw" /></div>}
    <SpaceAtmosphere scenic={scenic} showToggle={!showNav} />
    <header className="space-header"><Link className="focus-ring space-brand-link" href="/today" aria-label="Mira 学习空间首页"><MiraMark /></Link><div className="space-account">
      {student && <div className="space-student"><span className="space-avatar" aria-hidden="true"><Image src="/images/space/student-avatar.png" alt="" width={42} height={42} /></span><span><strong>{student.displayName}</strong><small>{student.gradeLabel || gradeLabel(student.gradeCode)}</small></span></div>}
      <button type="button" className="focus-ring space-rest" aria-label={locking ? "正在锁定" : "休息一下"} onClick={() => void lock()} disabled={locking}>{locking ? <LoaderCircle size={18} className="animate-spin motion-reduce:animate-none" /> : <CirclePause size={18} />}<span>{locking ? "正在锁定" : "休息一下"}</span></button>
    </div></header>
    {lockError && <p className="space-lock-error" role="alert">{lockError}</p>}
    {showNav && !persistentNavigation && <SpaceNavigation active={active} />}
    <main id="main-content" className="space-main">{children}</main>
  </div>;
}

export function SpacePageHeading({ eyebrow, title, description, backHref, backLabel = "返回", children }: {
  eyebrow?: string; title: string; description?: string; backHref?: string; backLabel?: string; children?: ReactNode;
}) {
  return <div className="space-page-heading">{backHref && <Link className="focus-ring space-back-link" href={backHref}><ArrowLeft size={18} />{backLabel}</Link>}<div className="space-page-heading__row"><div>{eyebrow && <p className="space-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="space-page-description">{description}</p>}</div>{children && <div className="space-heading-actions">{children}</div>}</div></div>;
}
