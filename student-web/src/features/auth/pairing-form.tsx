"use client";

import { ArrowRight, Check, KeyRound, LoaderCircle } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useSchoolbagMotion } from "@/components/schoolbag/schoolbag-motion";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/ui/disclosure";
import { Input } from "@/components/ui/input";
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
    <div>
      <section className="space-auth-panel">
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="auth-form-welcome">第一次使用</p>
              <h2 className="auth-form-title">和家长一起登录</h2>
            </div>
          </div>
          <p className="auth-form-description">请家长扫码确认，帮你准备好学习空间。</p>

          <QrPairing paused={usingCode} />

          <Disclosure className="auth-pair-disclosure" title={<span><KeyRound size={17} aria-hidden="true" />无法扫码？使用配对码</span>} onOpenChange={setUsingCode}>
            <PairingCodeForm />
          </Disclosure>

        </div>
      </section>
    </div>
  );
}

function PairingCodeForm() {
  const { enterLearning } = useSchoolbagMotion();
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
      enterLearning();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "配对失败，请稍后再试");
      setSubmitting(false);
    }
  }

  return (
    <form className="space-pair-code-form" onSubmit={submit} noValidate>
      <label htmlFor="pairing-code" className="mb-3 flex items-center gap-2 text-lg font-extrabold text-[var(--mira-ink)]">
        <KeyRound className="size-4 text-[var(--mira-brand-deep)]" aria-hidden="true" /> 8位配对码
      </label>
      <div className="relative">
        <Input
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
          className="pairing-code-input"
        />
        <AnimatePresence>
          {complete ? (
            <motion.span
              initial={reduced ? false : { scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={reduced ? { opacity: 0 } : { scale: 0.6, opacity: 0 }}
              transition={reduced ? { duration: 0 } : { duration: 0.2 }}
              className="absolute right-4 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full bg-[var(--mira-mint)] text-[var(--mira-success)]"
              aria-label="配对码已填写完整"
            >
              <Check className="size-5" />
            </motion.span>
          ) : null}
        </AnimatePresence>
      </div>
      <p id="pairing-help" className="mt-3 text-lg leading-6 text-[var(--mira-muted)]">
        配对码10分钟内有效，并且只能使用一次。
      </p>
      <div id="pairing-error" aria-live="polite" className="min-h-8 pt-2 text-lg font-semibold text-[var(--mira-danger)]">
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
