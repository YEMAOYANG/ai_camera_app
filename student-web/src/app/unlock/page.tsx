import type { Metadata } from "next";

import { AuthShell } from "@/features/auth/auth-shell";
import { LearningPathPreview } from "@/features/auth/learning-path-preview";
import { UnlockForm } from "@/features/auth/unlock-form";

export const metadata: Metadata = { title: "解锁学习空间" };

export default function UnlockPage() {
  return (
    <AuthShell>
      <LearningPathPreview />
      <UnlockForm />
    </AuthShell>
  );
}
