import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Mira 学习空间",
    template: "%s · Mira 学习空间",
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
        {children}
      </body>
    </html>
  );
}
