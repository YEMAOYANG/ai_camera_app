"use client";

import { Backpack, CircleAlert, RotateCcw } from "lucide-react";
import Link from "next/link";
import { StudentStatusScreen } from "@/components/student/student-status-screen";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <StudentStatusScreen icon={CircleAlert} role="alert" title="暂时没有连接上" message="再试一次，或先回到书包。">
      <Button size="compact" onClick={retry}><RotateCcw aria-hidden="true" />再试一次</Button>
      <Button size="compact" variant="secondary" asChild><Link href="/learning"><Backpack aria-hidden="true" />回到书包</Link></Button>
    </StudentStatusScreen>
  );
}
