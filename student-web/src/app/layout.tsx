import type { Metadata } from "next";
import { SpaceNavigationProvider } from "@/components/student/space-navigation";
import { SchoolbagMotionProvider } from "@/components/schoolbag/schoolbag-motion";
import "./globals.css";
import "../styles/space.css";
import "../styles/space-pages.css";
import "../styles/space-legacy.css";
import "../styles/space-effects.css";
import "../styles/space-explore.css";
import "../styles/space-practice-motion.css";
import "../styles/space-journey.css";
import "../styles/space-navigation.css";
import "../styles/space-controls.css";
import "../styles/space-session-transition.css";
import "../styles/space-textbooks.css";
import "../styles/schoolbag.css";
import "../styles/schoolbag-motion.css";
import "../styles/student-ui.css";
import "../styles/storybook.css";

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
        <SpaceNavigationProvider><SchoolbagMotionProvider>{children}</SchoolbagMotionProvider></SpaceNavigationProvider>
      </body>
    </html>
  );
}
