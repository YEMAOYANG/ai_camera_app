import type { Metadata } from "next";
import { SchoolbagMotionProvider } from "@/components/schoolbag/schoolbag-motion";
import "katex/dist/katex.min.css";
import "./globals.css";
import "../styles/student-auth.css";
import "../styles/student-status.css";
import "../styles/textbooks.css";
import "../styles/lesson-player.css";
import "../styles/course-detail.css";
import "../styles/schoolbag.css";
import "../styles/schoolbag-motion.css";
import "../styles/learning-picture-navigation.css";
import "../styles/learning-review.css";
import "../styles/learning-homework.css";
import "../styles/student-ui.css";
import "../styles/storybook.css";
import "../styles/buttons.css";

export const metadata: Metadata = {
  title: {
    default: "暖瞳学习空间",
    template: "%s · 暖瞳学习空间",
  },
  description: "面向小学一至六年级的互动学习空间",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body
        style={{
          "--font-mira-sans":
            '-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif',
        } as React.CSSProperties}
      >
        <a className="skip-link focus-ring" href="#main-content">
          跳到主要内容
        </a>
        <SchoolbagMotionProvider>{children}</SchoolbagMotionProvider>
      </body>
    </html>
  );
}
