"use client";

import { useEffect, useId, useState } from "react";

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
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default", htmlLabels: false, flowchart: { htmlLabels: false }, suppressErrorRendering: true });
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
  return <figure className="document-diagram">
    <figcaption>架构流程图<span>横向滚动查看全图</span></figcaption>
    {image && !failed ? <div className="document-diagram-scroll" tabIndex={0} role="region" aria-label="架构流程图，可横向滚动">
      {/* SVG remains an inert image, without document scripts or click handlers. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={image} alt="架构流程图，文字描述见下方图表源码和模块职责" />
    </div> : <p role="status">{failed ? "图表暂未渲染，可展开源码阅读。" : "正在绘制架构图…"}</p>}
    <details><summary>查看图表源码</summary><pre tabIndex={0} role="region" aria-label="图表源码，可横向滚动"><code>{source}</code></pre></details>
  </figure>;
}
