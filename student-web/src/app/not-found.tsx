import { Backpack, BookOpen } from "lucide-react";
import Link from "next/link";
import { StudentStatusScreen } from "@/components/student/student-status-screen";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <StudentStatusScreen icon={BookOpen} title="没有找到这个页面" message="回到书包，就能继续学习。">
      <Button size="compact" asChild><Link href="/learning"><Backpack aria-hidden="true" />回到书包</Link></Button>
    </StudentStatusScreen>
  );
}
