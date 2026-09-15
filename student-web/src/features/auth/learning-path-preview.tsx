import { BookOpenText, Brain, Play } from "lucide-react";

import { SoftReveal } from "@/components/motion/soft-reveal";

const steps = [
  { icon: Play, label: "听老师讲" },
  { icon: BookOpenText, label: "一起练习" },
  { icon: Brain, label: "真正记住" },
];

export function LearningPathPreview() {
  return (
    <SoftReveal className="space-auth-intro" delay={0.08}>
      <p className="space-eyebrow">MIRA · 学习空间</p>
      <h1>准备好，<br />探索新世界。</h1>
      <p className="space-auth-description">每一次好奇，都是新的起点。<br />和老师一起，把知识变成自己的发现。</p>
      <ol className="space-auth-steps" aria-label="学习过程">
        {steps.map(({ icon: Icon, label }, index) => (
          <li key={label}><Icon aria-hidden="true" /><span><small>0{index + 1}</small>{label}</span></li>
        ))}
      </ol>
    </SoftReveal>
  );
}
