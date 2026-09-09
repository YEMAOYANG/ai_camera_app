import { BookOpenText, Brain, Play, Sparkles } from "lucide-react";

import { SoftReveal } from "@/components/motion/soft-reveal";
import { MiraBuddy } from "@/components/student/mira-buddy";

const steps = [
  { icon: Play, label: "听老师讲", tone: "bg-[var(--mira-brand-wash)] text-[var(--mira-brand-deep)]" },
  { icon: BookOpenText, label: "一起练习", tone: "bg-[#E9F4EF] text-[#397864]" },
  { icon: Brain, label: "真正记住", tone: "bg-[#FFF1DE] text-[#AA6D1D]" },
];

export function LearningPathPreview() {
  return (
    <SoftReveal className="hidden lg:block" delay={0.08}>
      <div className="max-w-[520px]">
        <div className="mb-4 flex items-end gap-2">
          <MiraBuddy className="w-32" />
          <div className="mb-4 inline-flex items-center gap-2 rounded-[18px_18px_18px_5px] bg-white px-4 py-3 text-sm font-bold text-[var(--mira-brand-deep)] shadow-sm">
            <Sparkles className="size-4" />
            嗨，我陪你一起学！
          </div>
        </div>
        <h1 className="max-w-[500px] text-[clamp(42px,5.2vw,68px)] font-black leading-[1.08] tracking-[-.055em]">
          上课不只是
          <span className="relative mx-2 inline-block text-[var(--mira-brand-deep)]">
            做题
            <span className="absolute -bottom-1 left-0 h-3 w-full -rotate-1 rounded-full bg-[rgba(47,108,246,.13)]" aria-hidden="true" />
          </span>
        </h1>
        <p className="mt-6 max-w-[480px] text-xl leading-9 text-[var(--mira-muted)]">
          Mira 会先讲清楚，再陪你练一练，最后帮你把学会的内容记得更久。
        </p>
        <ol className="mt-10 grid grid-cols-3 gap-3" aria-label="学习过程">
          {steps.map(({ icon: Icon, label, tone }, index) => (
            <li key={label} className="relative rounded-[22px] border-2 border-white bg-white/82 p-4 shadow-sm">
              <span className={`mb-4 grid size-11 place-items-center rounded-[15px] ${tone}`}>
                <Icon className="size-5" aria-hidden="true" />
              </span>
              <span className="block text-xs font-bold text-[var(--mira-subtle)]">0{index + 1}</span>
              <span className="mt-1 block font-extrabold text-[var(--mira-ink)]">{label}</span>
              {index < steps.length - 1 ? <span className="absolute -right-3 top-9 z-10 h-[2px] w-6 bg-[var(--mira-border)]" aria-hidden="true" /> : null}
            </li>
          ))}
        </ol>
      </div>
    </SoftReveal>
  );
}
