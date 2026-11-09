import { Backpack, BookOpen } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main id="main-content" className="mira-ui-surface student-session-screen">
      <div className="student-session-state">
        <span className="student-session-icon" aria-hidden="true"><BookOpen size={28} strokeWidth={1.6} /></span>
        <h1>没有找到这个页面</h1>
        <p>回到书包，就能继续学习。</p>
        <Button size="compact" className="student-session-retry" asChild><Link href="/learning"><Backpack aria-hidden="true" />回到书包</Link></Button>
      </div>
    </main>
  );
}
