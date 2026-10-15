import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "页面不存在" };

export default function NotFound() {
  return <main className="system-page" id="main">
    <div>
      <span className="code">404</span>
      <h1>这个页面不存在</h1>
      <p>地址可能输错了，或者页面已经移动。可以回到总览，或打开调用检查。</p>
      <div className="actions">
        <Link className="btn btn-primary" href="/workspace">回到总览</Link>
        <Link className="btn" href="/workbench">打开调用检查</Link>
      </div>
    </div>
  </main>;
}
