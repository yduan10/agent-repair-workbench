"use client";
import Link from "next/link";

export default function WorkspaceError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="system-page" role="alert">
    <div>
      <span className="code">页面出错</span>
      <h1>这个页面没能显示出来</h1>
      <p>界面渲染时遇到异常，本机记录不受影响。可以重试；如果反复出现，请刷新浏览器或重启前端服务。</p>
      {error.digest && <p className="subtle small" translate="no">错误标识：{error.digest}</p>}
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={reset}>重试</button>
        <Link className="btn" href="/workspace">回到总览</Link>
      </div>
    </div>
  </div>;
}
