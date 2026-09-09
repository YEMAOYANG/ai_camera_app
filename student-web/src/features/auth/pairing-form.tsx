"use client";

import { ArrowRight, Check, ChevronDown, KeyRound, LoaderCircle, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { SoftReveal } from "@/components/motion/soft-reveal";
import { Button } from "@/components/ui/button";
import { MiraBuddy } from "@/components/student/mira-buddy";
import { QrPairing } from "@/features/auth/qr-pairing";

function normalizePairingCode(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
}

function displayPairingCode(value: string) {
  return value.length > 4 ? `${value.slice(0, 4)} ${value.slice(4)}` : value;
}

export function PairingForm() {
  const [usingCode, setUsingCode] = useState(false);

  return (
    <SoftReveal delay={0.16}>
      <section className="relative mx-auto w-full max-w-[540px] overflow-hidden rounded-[var(--mira-radius-playful)] border-2 border-white bg-white/94 p-5 shadow-[var(--mira-shadow-card)] sm:p-8">
        <div className="absolute right-0 top-0 size-40 translate-x-1/3 -translate-y-1/3 rounded-full bg-[var(--mira-sun-soft)]" aria-hidden="true" />
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-sm font-extrabold tracking-[.1em] text-[var(--mira-brand-deep)]">第一次使用</p>
              <h2 className="text-[30px] font-black leading-tight tracking-[-.045em] sm:text-[36px]">和家长一起登录</h2>
            </div>
            <MiraBuddy className="w-[78px] shrink-0 lg:hidden" label="Mira 来迎接你" />
          </div>
          <p className="mt-3 text-[17px] leading-7 text-[var(--mira-muted)]">不需要输入账号密码，家长确认后就能开始学习。</p>

          <QrPairing paused={usingCode} />

          <details
            className="group mt-6 border-t border-[var(--mira-border-soft)] pt-3"
            onToggle={(event) => setUsingCode(event.currentTarget.open)}
          >
            <summary className="focus-ring flex min-h-12 cursor-pointer list-none items-center justify-center gap-2 rounded-[var(--mira-radius-button)] px-3 text-[15px] font-extrabold text-[var(--mira-brand-deep)] [&::-webkit-details-marker]:hidden">
              <KeyRound className="size-5" aria-hidden="true" />
              无法扫码？使用配对码
              <ChevronDown className="size-5 transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
            </summary>
            <PairingCodeForm />
          </details>

          <div className="mt-5 flex items-start gap-3 border-t border-[var(--mira-border-soft)] pt-5 text-sm leading-6 text-[var(--mira-muted)]">
            <ShieldCheck className="mt-0.5 size-5 shrink-0 text-[var(--mira-success)]" aria-hidden="true" />
            <p>
              <strong className="text-[var(--mira-ink)]">只会打开你的学习内容。</strong>
              <br />
              家庭设置、摄像头和家长信息不会出现在这里。
            </p>
          </div>
        </div>
      </section>
    </SoftReveal>
  );
}

function PairingCodeForm() {
  const router = useRouter();
  const reduced = useReducedMotion();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const complete = useMemo(() => code.length === 8, [code]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!complete || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const payload = (await response.json()) as { ok?: boolean; message?: string };
      if (!response.ok) throw new Error(payload.message || "配对失败，请确认配对码后重试");
      router.replace("/today");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "配对失败，请稍后再试");
      setSubmitting(false);
    }
  }

  return (
    <form className="mt-3 rounded-[22px] bg-[var(--mira-surface-soft)] p-4 sm:p-5" onSubmit={submit} noValidate>
      <label htmlFor="pairing-code" className="mb-3 flex items-center gap-2 text-[15px] font-extrabold text-[var(--mira-ink)]">
        <KeyRound className="size-4 text-[var(--mira-brand-deep)]" aria-hidden="true" /> 8位配对码
      </label>
      <div className="relative">
        <input
          id="pairing-code"
          name="pairingCode"
          value={displayPairingCode(code)}
          onChange={(event) => {
            setCode(normalizePairingCode(event.target.value));
            setError("");
          }}
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          inputMode="text"
          maxLength={9}
          aria-describedby="pairing-help pairing-error"
          aria-invalid={Boolean(error)}
          placeholder="ABCD 1234"
          className="focus-ring h-[68px] w-full rounded-[20px] border-2 border-[var(--mira-border)] bg-[var(--mira-bg)] px-5 pr-14 text-center text-[26px] font-black uppercase tracking-[.16em] text-[var(--mira-ink)] outline-none transition-colors placeholder:text-[var(--mira-disabled)] focus:border-[var(--mira-brand)] focus:bg-white sm:text-[30px]"
        />
        <AnimatePresence>
          {complete ? (
            <motion.span
              initial={reduced ? false : { scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.6, opacity: 0 }}
              className="absolute right-4 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full bg-[#E6F4EE] text-[var(--mira-success)]"
              aria-label="配对码已填写完整"
            >
              <Check className="size-5" />
            </motion.span>
          ) : null}
        </AnimatePresence>
      </div>
      <p id="pairing-help" className="mt-3 text-sm leading-6 text-[var(--mira-muted)]">
        配对码10分钟内有效，并且只能使用一次。
      </p>
      <div id="pairing-error" aria-live="polite" className="min-h-8 pt-2 text-sm font-semibold text-[var(--mira-danger)]">
        {error}
      </div>
      <Button className="mt-2 w-full" type="submit" disabled={!complete || submitting}>
        {submitting ? <LoaderCircle className="size-5 animate-spin" aria-hidden="true" /> : null}
        {submitting ? "正在安全连接…" : "进入学习空间"}
        {!submitting ? <ArrowRight className="size-5" aria-hidden="true" /> : null}
      </Button>
    </form>
  );
}
