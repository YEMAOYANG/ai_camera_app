"use client";

import { Check, Clock3, LoaderCircle, RefreshCw, ScanLine, Smartphone, TriangleAlert } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { QRCodeSVG } from "qrcode.react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { studentQrStartResponseSchema, type StudentQrStartResponse } from "@/lib/contracts/student-session";

type QrStatus = "starting" | "waiting" | "expired" | "rejected" | "consumed" | "error" | "success";
type QrTerminalStatus = Extract<QrStatus, "expired" | "rejected" | "consumed">;

export function QrPairing({ paused = false }: { paused?: boolean }) {
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const [challenge, setChallenge] = useState<StudentQrStartResponse | null>(null);
  const [status, setStatus] = useState<QrStatus>("starting");
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [message, setMessage] = useState("");

  const startChallenge = useCallback(async () => {
    setStatus("starting");
    setMessage("");
    setChallenge(null);
    try {
      const response = await fetch("/api/auth/qr/start", { method: "POST" });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const error = payload as { message?: string } | null;
        throw new Error(error?.message || "二维码暂时没有准备好");
      }
      const parsed = studentQrStartResponseSchema.safeParse(payload);
      if (!parsed.success) throw new Error("二维码登录服务返回了无法识别的数据");
      setChallenge(parsed.data);
      setRemainingSeconds(secondsUntil(parsed.data.expiresAt));
      setStatus("waiting");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "二维码暂时没有准备好");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void startChallenge(), 0);
    return () => window.clearTimeout(timer);
  }, [startChallenge]);

  useEffect(() => {
    if (!challenge || status !== "waiting") return;
    const update = () => {
      const remaining = secondsUntil(challenge.expiresAt);
      setRemainingSeconds(remaining);
      if (remaining === 0) setStatus("expired");
    };
    const timer = window.setInterval(update, 1_000);
    return () => window.clearInterval(timer);
  }, [challenge, status]);

  useEffect(() => {
    if (!challenge || status !== "waiting" || paused) return;
    let disposed = false;
    let timer: number | undefined;
    const controller = new AbortController();
    const interval = Math.min(10_000, Math.max(1_000, challenge.pollingIntervalMs));

    const schedule = () => {
      timer = window.setTimeout(() => void poll(), interval);
    };
    const poll = async () => {
      try {
        const response = await fetch("/api/auth/qr/exchange", {
          method: "POST",
          signal: controller.signal,
        });
        if (disposed) return;
        if (response.status === 202) {
          schedule();
          return;
        }
        const payload = (await response.json().catch(() => null)) as {
          status?: string;
          error?: string;
          message?: string;
        } | null;
        if (response.ok) {
          setStatus("success");
          return;
        }
        const terminalStatus = qrTerminalStatus(payload, response.status);
        if (terminalStatus) {
          setStatus(terminalStatus);
          return;
        }
        setMessage(payload?.message || "还没有连接成功，请刷新二维码重试");
        setStatus("error");
      } catch (error) {
        if (disposed || (error instanceof DOMException && error.name === "AbortError")) return;
        setMessage("网络有点慢，请刷新二维码重试");
        setStatus("error");
      }
    };

    schedule();
    return () => {
      disposed = true;
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [challenge, paused, status]);

  useEffect(() => {
    if (status !== "success") return;
    const timer = window.setTimeout(() => {
      router.replace("/today");
      router.refresh();
    }, reducedMotion ? 0 : 650);
    return () => window.clearTimeout(timer);
  }, [reducedMotion, router, status]);

  return (
    <div className="mt-6" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[15px] font-extrabold text-[var(--mira-ink)]">
          <ScanLine className="size-5 text-[var(--mira-brand-deep)]" aria-hidden="true" />
          家长扫码确认
        </div>
        {status === "waiting" ? (
          <span className="flex min-h-12 items-center gap-1.5 rounded-full px-3 text-sm font-bold text-[var(--mira-muted)]">
            <Clock3 className="size-4" aria-hidden="true" />
            {formatCountdown(remainingSeconds)}
          </span>
        ) : null}
      </div>

      <div className="mt-3 grid min-h-[300px] place-items-center rounded-[26px] border-2 border-[var(--mira-border-soft)] bg-[var(--mira-bg-warm)] p-5 sm:min-h-[318px]">
        {status === "starting" ? <QrStarting /> : null}
        {status === "waiting" && challenge ? (
          <div className="text-center">
            <div className="mx-auto w-fit rounded-[30px] border-2 border-[var(--mira-brand-wash)] bg-white p-3 shadow-[0_16px_40px_rgba(33,54,89,.10)]">
              <QRCodeSVG
                value={challenge.qrValue}
                size={220}
                level="M"
                marginSize={4}
                bgColor="#ffffff"
                fgColor="#142033"
                title="Mira 学生登录二维码"
                className="h-auto w-[220px] max-w-full"
              />
            </div>
            <p className="mt-5 flex items-center justify-center gap-2 text-[16px] font-black text-[var(--mira-ink)]">
              <Smartphone className="size-5 text-[var(--mira-brand-deep)]" aria-hidden="true" />
              请家长用 Mira App 扫一扫
            </p>
            <div className="mx-auto mt-4 max-w-[290px] border-t border-[var(--mira-border-soft)] pt-4">
              <p className="text-xs font-extrabold tracking-[.12em] text-[var(--mira-muted)]">4 位核对码</p>
              <strong
                className="mt-1 block text-[34px] font-black tracking-[.28em] text-[var(--mira-brand-deep)]"
                aria-label={`核对码 ${challenge.displayCode}`}
              >
                {challenge.displayCode}
              </strong>
              <p className="mt-1 text-sm leading-6 text-[var(--mira-muted)]">请家长确认 App 里也是这 4 位数字，再同意登录。</p>
            </div>
          </div>
        ) : null}
        {status === "expired" ? (
          <QrRecovery title="二维码过期啦" description="为了保护你的学习空间，请换一张新的二维码。" onRefresh={startChallenge} />
        ) : null}
        {status === "rejected" ? (
          <QrRecovery title="家长这次没有确认" description="请和家长确认后，再刷新一张二维码。" onRefresh={startChallenge} />
        ) : null}
        {status === "consumed" ? (
          <QrRecovery title="二维码已经用过啦" description="每张二维码只能登录一次，请刷新后再试。" onRefresh={startChallenge} />
        ) : null}
        {status === "error" ? (
          <QrRecovery title="暂时没有连上" description={message || "请刷新二维码再试一次。"} onRefresh={startChallenge} error />
        ) : null}
        {status === "success" ? (
          <div className="text-center" role="status">
            <span className="mx-auto grid size-20 place-items-center rounded-full bg-[var(--mira-mint)] text-[var(--mira-success)]">
              <Check className="size-10" aria-hidden="true" />
            </span>
            <h3 className="mt-5 text-2xl font-black">家长已经确认</h3>
            <p className="mt-2 text-[var(--mira-muted)]">正在打开你的学习空间…</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function QrStarting() {
  return (
    <div className="text-center" role="status">
      <LoaderCircle className="mx-auto size-11 animate-spin text-[var(--mira-brand-deep)] motion-reduce:animate-none" aria-hidden="true" />
      <p className="mt-4 text-lg font-black">正在准备二维码</p>
      <p className="mt-1 text-sm text-[var(--mira-muted)]">马上就好</p>
    </div>
  );
}

function QrRecovery({
  title,
  description,
  onRefresh,
  error = false,
}: {
  title: string;
  description: string;
  onRefresh: () => Promise<void>;
  error?: boolean;
}) {
  return (
    <div className="max-w-[310px] text-center" role={error ? "alert" : "status"}>
      <span className={`mx-auto grid size-16 place-items-center rounded-full ${error ? "bg-[#fff1ee] text-[var(--mira-danger)]" : "bg-[var(--mira-sun-soft)] text-[var(--mira-warning)]"}`}>
        <TriangleAlert className="size-8" aria-hidden="true" />
      </span>
      <h3 className="mt-4 text-2xl font-black">{title}</h3>
      <p className="mt-2 leading-7 text-[var(--mira-muted)]">{description}</p>
      <Button className="mt-5 min-w-44" type="button" onClick={() => void onRefresh()}>
        <RefreshCw className="size-5" aria-hidden="true" />
        刷新二维码
      </Button>
    </div>
  );
}

function secondsUntil(expiresAt: number) {
  return Math.max(0, Math.ceil((expiresAt - Date.now()) / 1_000));
}

function formatCountdown(value: number) {
  const minutes = Math.floor(value / 60);
  const seconds = String(value % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function qrTerminalStatus(
  payload: { status?: string; error?: string } | null,
  responseStatus: number,
): QrTerminalStatus | null {
  if (payload?.status === "expired" || payload?.status === "rejected" || payload?.status === "consumed") {
    return payload.status;
  }
  if (payload?.error === "student_qr_challenge_rejected") return "rejected";
  if (payload?.error === "student_qr_challenge_consumed") return "consumed";
  if (payload?.error === "student_qr_challenge_expired" || responseStatus === 410) return "expired";
  return null;
}
