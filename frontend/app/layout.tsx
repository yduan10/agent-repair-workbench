import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent 修复台 · 工具调用测试与修复",
  description:
    "面向 Agent 与 MCP 工具开发者，从调用证据、问题诊断到修复回归的产品工作区。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: `(function(){var t='system';try{var v=localStorage.getItem('awb-theme');if(v==='light'||v==='dark')t=v}catch(e){}var r=document.documentElement;r.dataset.themePreference=t;r.dataset.theme=t==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):t})()` }} /></head>
      <body>{children}</body>
    </html>
  );
}
