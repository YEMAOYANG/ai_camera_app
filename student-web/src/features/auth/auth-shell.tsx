import { Backpack, ShieldCheck } from "lucide-react";

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="schoolbag-shell schoolbag-auth">
      <header className="space-auth-header">
        <div className="schoolbag-brand"><span><Backpack size={26} aria-hidden="true" /></span><strong>暖瞳<small>学习空间</small></strong></div>
        <span><ShieldCheck aria-hidden="true" />家长授权 · 学生专属</span>
      </header>
      <main id="main-content" className="space-auth-main">{children}</main>
    </div>
  );
}
