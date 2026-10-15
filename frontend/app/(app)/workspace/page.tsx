import type { Metadata } from "next";
import Overview from "../../../components/overview";

export const metadata: Metadata = { title: "总览", description: "本机环境状态与最近的复现、分析和修复。" };

export default function OverviewPage() {
  return <Overview />;
}
