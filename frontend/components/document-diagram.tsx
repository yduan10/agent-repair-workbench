"use client";

import { useEffect, useId, useState } from "react";
import { Skeleton } from "./ui/skeleton";

// Mermaid has shared configuration. Serialize renders so two diagrams cannot
// overwrite each other's theme while the asynchronous renderer is working.
let renderQueue: Promise<unknown> = Promise.resolve();

export default function DocumentDiagram({ source }: { source: string }) {
  const id = `document-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const [image, setImage] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let disposed = false;
    let revision = 0;
    const draw = () => {
      const current = ++revision;
      const dark = document.documentElement.dataset.theme === "dark";
      renderQueue = renderQueue.catch(() => undefined).then(async () => {
        if (disposed || current !== revision) return;
        // Only repository-owned flowcharts are supported. Directives, HTML,
        // image shapes and link actions fall back to readable source.
        if (!/^\s*flowchart\s+(LR|RL|TB|TD|BT)\b/.test(source)
          || /%%\{|^\s*---|\bclick\s|@\{|<|\b[a-z][a-z\d+.-]*:\/\//im.test(source)) throw new Error("Unsupported diagram");
        const { default: mermaid } = await import("mermaid");
        // Colours come from the site tokens so diagrams match the reader in both themes.
        const token = (name: string, fallback: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
        const themeVariables = {
          darkMode: dark,
          fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
          fontSize: "14px",
          background: token("--surface", dark ? "#16181b" : "#ffffff"),
          primaryColor: token("--surface-2", dark ? "#1c1f23" : "#f0f1f3"),
          primaryTextColor: token("--text", dark ? "#e8eaed" : "#15171c"),
          primaryBorderColor: token("--border-strong", dark ? "#363a42" : "#cfd3d9"),
          secondaryColor: token("--accent-soft", dark ? "#1d2040" : "#eceefc"),
          tertiaryColor: token("--surface", dark ? "#16181b" : "#ffffff"),
          lineColor: token("--text-3", dark ? "#858b95" : "#6e747e"),
          textColor: token("--text-2", dark ? "#a9afb8" : "#4a505a"),
          clusterBkg: token("--bg", dark ? "#0e0f11" : "#f6f7f8"),
          clusterBorder: token("--border", dark ? "#272a30" : "#e2e4e8"),
          edgeLabelBackground: token("--surface", dark ? "#16181b" : "#ffffff"),
        };
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables, htmlLabels: false, flowchart: { htmlLabels: false }, suppressErrorRendering: true });
        const { svg } = await mermaid.render(id, source);
        if (!disposed && current === revision) {
          setImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);
          setFailed(false);
        }
      }).catch(() => { if (!disposed && current === revision) setFailed(true); });
    };
    const observer = new MutationObserver(draw);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    draw();
    return () => { disposed = true; observer.disconnect(); };
  }, [id, source]);
  return <figure className="doc-diagram">
    <figcaption>架构流程图<span>可横向滚动查看全图</span></figcaption>
    {image && !failed ? <div className="doc-diagram-scroll" tabIndex={0} role="region" aria-label="架构流程图，可横向滚动">
      {/* SVG remains an inert image, without document scripts or click handlers. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={image} alt="架构流程图，文字描述见下方图表源码和模块职责" />
    </div> : failed
      ? <p className="doc-diagram-status" role="status">图表加载失败，可展开下方源码阅读。</p>
      : <div className="doc-diagram-status" role="status" aria-busy="true"><span className="sr-only">正在绘制图表…</span><Skeleton height={180} /></div>}
    <details><summary>查看图表源码</summary><pre tabIndex={0} role="region" aria-label="图表源码，可横向滚动" translate="no"><code>{source}</code></pre></details>
  </figure>;
}
