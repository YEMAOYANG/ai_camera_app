"use client";

import { Backpack, WifiOff } from "lucide-react";
import { StudentStatusScreen } from "@/components/student/student-status-screen";
import { Button } from "@/components/ui/button";

export function StudentSessionState({
  error,
  onRetry,
  title = "正在打开学习空间",
  description = "请稍等一下",
}: { error?: string; onRetry?: () => void; title?: string; description?: string }) {
  if (error) {
    return (
      <StudentStatusScreen icon={WifiOff} role="alert" title="暂时没有连接上" message={error}>
        {onRetry && <Button size="compact" onClick={onRetry}>再试一次</Button>}
      </StudentStatusScreen>
    );
  }
  return <StudentStatusScreen icon={Backpack} role="status" busy title={title} message={description} />;
}
