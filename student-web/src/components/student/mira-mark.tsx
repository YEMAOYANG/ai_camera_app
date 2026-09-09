import { Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export function MiraMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="inline-flex items-center gap-3" aria-label="Mira 学习空间">
      <span
        className={cn(
          "relative grid shrink-0 place-items-center rounded-[18px] bg-[var(--mira-brand-deep)] text-white shadow-[0_10px_24px_rgba(36,89,214,.22)]",
          compact ? "size-11" : "size-13",
        )}
        aria-hidden="true"
      >
        <span className={cn("font-black tracking-[-.08em]", compact ? "text-xl" : "text-2xl")}>米</span>
        <Sparkles className="absolute -right-1 -top-1 size-4 rounded-full bg-white p-[2px] text-[var(--mira-ai)]" />
      </span>
      <span className="text-left">
        <strong className="block text-[17px] leading-5 tracking-[-.02em] text-[var(--mira-ink)]">Mira</strong>
        <span className="block text-[12px] font-semibold tracking-[.12em] text-[var(--mira-muted)]">学习空间</span>
      </span>
    </div>
  );
}
