"use client";

import { AlertCircle, LoaderCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { widgetMessageSchema, type WidgetMessage } from "@/features/classroom/interactive-protocol";
import { buildSandboxedWidgetDocument, widgetSandboxPermissions } from "@/features/classroom/sandbox-srcdoc";

type InteractiveFrameProps = {
  sceneId: string;
  title: string;
  html?: string;
  templateId?: "tap_choice.v1" | "match_pairs.v1" | "sort_order.v1" | "slider_lab.v1";
  instructions?: string;
  onMessage: (message: WidgetMessage) => void;
};

export function InteractiveFrame({ sceneId, title, html, templateId, instructions, onMessage }: InteractiveFrameProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const srcDoc = useMemo(
    () => buildSandboxedWidgetDocument({ sceneId, title, html, templateId, instructions }),
    [html, instructions, sceneId, templateId, title],
  );

  useEffect(() => {
    function receive(event: MessageEvent) {
      if (event.source !== iframeRef.current?.contentWindow) return;
      const parsed = widgetMessageSchema.safeParse(event.data);
      if (!parsed.success || parsed.data.sceneId !== sceneId) return;
      if (parsed.data.kind === "ready") setReady(true);
      if (parsed.data.kind === "error") setFailed(true);
      onMessage(parsed.data);
    }
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [onMessage, sceneId, srcDoc]);

  return (
    <div className="classroom-widget relative size-full min-h-[340px] overflow-hidden rounded-[24px] bg-white">
      {!ready && !failed ? (
        <div className="absolute inset-0 z-10 grid place-items-center bg-white/92" aria-live="polite">
          <p className="flex items-center gap-2 font-extrabold text-[var(--mira-muted)]">
            <LoaderCircle className="size-5 animate-spin text-[var(--mira-brand)]" />正在准备小实验
          </p>
        </div>
      ) : null}
      {failed ? (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[var(--mira-sun-soft)] p-6 text-center" role="alert">
          <div><AlertCircle className="mx-auto size-10 text-[var(--mira-warning)]" /><p className="mt-3 font-black">这个小实验暂时走神了</p><p className="mt-2 text-sm text-[var(--mira-muted)]">可以先去下一个场景，学习进度不会丢失。</p></div>
        </div>
      ) : null}
      <iframe
        ref={iframeRef}
        title={title}
        srcDoc={srcDoc}
        sandbox={widgetSandboxPermissions}
        className="size-full min-h-[340px] border-0"
      />
    </div>
  );
}
