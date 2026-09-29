"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useSchoolbagMotion } from "@/components/schoolbag/schoolbag-motion";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { PinInput } from "@/components/ui/pin-input";
import Link from "next/link";

export function UnlockForm() {
  const { enterLearning } = useSchoolbagMotion();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const pinInput = useRef<HTMLInputElement>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pin.length !== 4 || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      const payload = (await response.json()) as { message?: string };
      if (!response.ok) throw new Error(payload.message || "PIN不正确，请重试");
      enterLearning();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "解锁失败，请稍后再试");
      setPin("");
      setSubmitting(false);
      requestAnimationFrame(() => pinInput.current?.focus());
    }
  }

  return (
    <section className="space-auth-panel space-unlock-panel" data-pin-state={submitting ? "connecting" : error ? "error" : pin.length === 4 ? "ready" : "entering"}>
      <p className="auth-form-welcome">欢迎回来</p>
      <h2 className="auth-form-title">输入学习 PIN</h2>
      <p className="auth-form-description">用家长设置的 4 位数字解锁。</p>
      <form className="auth-pin-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="student-pin">4位学习PIN</label>
        <PinInput
          ref={pinInput}
          id="student-pin"
          value={pin}
          onChange={(value) => {
            setPin(value.replace(/\D/g, "").slice(0, 4));
            setError("");
          }}
          disabled={submitting}
          invalid={Boolean(error)}
          describedBy="pin-error"
        />
        <p id="pin-error" aria-live="polite" className="auth-field-error">{error}</p>
        <Button className="mt-2 w-full" type="submit" disabled={pin.length !== 4 || submitting}>
          {submitting ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : null}
          {submitting ? "正在解锁…" : "继续学习"}
          {!submitting ? <ArrowRight className="size-5" aria-hidden="true" /> : null}
        </Button>
      </form>
      <Button asChild variant="quiet" className="mt-3 w-full">
        <Link href="/pair">换一台设备配对</Link>
      </Button>
    </section>
  );
}
