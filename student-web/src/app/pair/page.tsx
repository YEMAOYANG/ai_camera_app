import type { Metadata } from "next";

import { AuthShell } from "@/features/auth/auth-shell";
import { LearningPathPreview } from "@/features/auth/learning-path-preview";
import { PairingForm } from "@/features/auth/pairing-form";

export const metadata: Metadata = { title: "连接学习空间" };

export default function PairPage() {
  return (
    <AuthShell>
      <LearningPathPreview />
      <PairingForm />
    </AuthShell>
  );
}
