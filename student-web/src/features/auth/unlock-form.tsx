"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { MiraBuddy } from "@/components/student/mira-buddy";

export function UnlockForm() {
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
      router.replace("/today");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "解锁失败，请稍后再试");
      setPin("");
      setSubmitting(false);
    }
  }

  return (
    <section className="mx-auto w-full max-w-[480px] rounded-[var(--mira-radius-playful)] border-2 border-white bg-white/94 p-6 shadow-[var(--mira-shadow-card)] sm:p-9">
      <MiraBuddy mood="hello" className="mb-2 w-24 lg:hidden" label="Mira 欢迎你回来" />
      <p className="text-sm font-extrabold tracking-[.1em] text-[var(--mira-brand-deep)]">欢迎回来</p>
      <h1 className="mt-2 text-[34px] font-black tracking-[-.045em]">输入学习PIN</h1>
      <p className="mt-3 text-[17px] leading-7 text-[var(--mira-muted)]">这是家长为你的学习空间设置的4位数字。</p>
      <form className="mt-8" onSubmit={submit}>
        <label className="sr-only" htmlFor="student-pin">4位学习PIN</label>
        <input
          id="student-pin"
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="current-password"
          maxLength={4}
          autoFocus
          value={pin}
          onChange={(event) => {
            setPin(event.target.value.replace(/\D/g, "").slice(0, 4));
            setError("");
          }}
          aria-invalid={Boolean(error)}
          aria-describedby="pin-error"
          className="focus-ring h-[72px] w-full rounded-[18px] border-2 border-[var(--mira-border)] bg-white px-5 text-center text-[36px] font-black tracking-[.5em] outline-none transition-colors focus:border-[var(--mira-brand)]"
        />
        <p id="pin-error" aria-live="polite" className="min-h-10 pt-3 text-sm font-semibold text-[var(--mira-danger)]">{error}</p>
        <Button className="mt-2 w-full" type="submit" disabled={pin.length !== 4 || submitting}>
          {submitting ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : null}
          {submitting ? "正在解锁…" : "继续学习"}
          {!submitting ? <ArrowRight className="size-5" aria-hidden="true" /> : null}
        </Button>
      </form>
      <Button asChild variant="quiet" className="mt-3 w-full">
        <a href="/pair">换一台设备配对</a>
      </Button>
    </section>
  );
}
