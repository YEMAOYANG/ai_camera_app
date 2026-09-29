import { SchoolbagStage } from "@/components/schoolbag/schoolbag-motion";

export function LearningPathPreview() {
  return (
    <div className="space-auth-intro">
      <div className="auth-scene-copy"><h1>打开书包，上课啦。</h1>
      <p className="space-auth-description">看图、听故事，从一本课本开始。</p></div>
      <SchoolbagStage pose="closed" label="关着的黄色小书包，登录后一起打开" />
      <p className="auth-scene-caption">每一次打开，都有新的发现。</p>
    </div>
  );
}
