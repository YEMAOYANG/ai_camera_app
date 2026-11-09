import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function StudentStatusScreen({
  icon: Icon,
  title,
  message,
  eyebrow,
  role,
  busy = false,
  children,
}: {
  icon: LucideIcon;
  title: string;
  message: string;
  eyebrow?: string;
  role?: "status" | "alert";
  busy?: boolean;
  children?: ReactNode;
}) {
  return (
    <main id="main-content" className="mira-ui-surface student-session-screen">
      <section className="student-session-state" role={role} aria-busy={role ? busy : undefined}>
        <span className="student-session-icon" aria-hidden="true"><Icon size={28} strokeWidth={1.6} /></span>
        {eyebrow && <p>{eyebrow}</p>}
        <h1>{title}</h1>
        <p>{message}</p>
        {busy && <div className="student-session-progress" aria-hidden="true"><i /></div>}
        {children && <div className="student-status-actions">{children}</div>}
      </section>
    </main>
  );
}
