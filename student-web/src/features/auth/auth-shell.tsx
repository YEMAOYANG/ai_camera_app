import { ShieldCheck } from "lucide-react";

import { MiraMark } from "@/components/student/mira-mark";
import { SpaceAtmosphere } from "@/components/student/space-atmosphere";

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-auth" data-space-stage>
      <div className="space-auth-scenery" aria-hidden="true" />
      <SpaceAtmosphere scenic />
      <header className="space-auth-header">
        <MiraMark />
        <span><ShieldCheck aria-hidden="true" />家长授权 · 学生专属</span>
      </header>
      <main id="main-content" className="space-auth-main">{children}</main>
    </div>
  );
}
