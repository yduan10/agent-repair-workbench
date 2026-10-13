// Build-time, repository-owned Markdown only. Never resolve route input as a file path.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { cache } from "react";
import { documentationUrl } from "./documentation";
import { sourceDocument } from "./project";

export type ProjectDocument = { slug: string; source: string; title: string; content: string };

export const projectDocuments = cache((): ProjectDocument[] => {
  const docsRoot = path.join(process.cwd(), "../docs");
  const files: string[] = ["README.md"];
  function collect(directory: string) {
    for (const entry of readdirSync(path.join(docsRoot, directory), { withFileTypes: true })) {
      const relative = directory ? `${directory}/${entry.name}` : entry.name;
      if (entry.isDirectory()) collect(relative);
      else if (entry.isFile() && entry.name.endsWith(".md")) files.push(`docs/${relative}`);
    }
  }
  collect("");
  return files.sort().map(source => {
    const content = source === "README.md"
      ? readFileSync(path.join(process.cwd(), "../README.md"), "utf8")
      : readFileSync(path.join(process.cwd(), "../docs", source.slice(5)), "utf8");
    const title = content.match(/^#\s+(.+)$/m)?.[1] ?? source;
    const slug = source === "README.md" ? "getting-started" : source === "docs/README.md" ? "index" : source.slice(5, -3);
    return { source, slug, title, content };
  });
});

export function documentLink(href: string, source: string): string | undefined {
  if (!href) return undefined;
  if (href.startsWith("#")) return href;
  if (/^https?:\/\//i.test(href)) return href;
  if (href.startsWith("/") || /^[a-z][a-z\d+.-]*:/i.test(href)) return undefined;
  const [file, fragment] = href.split("#", 2);
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(source), file));
  if (resolved.startsWith("../")) return undefined;
  const match = projectDocuments().find(doc => doc.source === resolved);
  if (match) return documentationUrl(match.slug) + (fragment ? `#${fragment}` : "");
  // Non-document source references remain explicitly external source links.
  return sourceDocument(resolved);
}

export function sectionId(text: string) {
  return text.toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, "").trim().replace(/\s/g, "-");
}

export function documentSections(content: string) {
  let fence = "";
  const used = new Map<string, number>();
  return content.split("\n").flatMap((line, index) => {
    const delimiter = line.match(/^\s*(`{3,}|~{3,})/);
    if (delimiter) {
      if (!fence) fence = delimiter[1];
      else if (delimiter[1][0] === fence[0] && delimiter[1].length >= fence.length) fence = "";
      return [];
    }
    const match = !fence && line.match(/^(#{2,3})\s+(.+?)\s*#*$/);
    if (!match) return [];
    const title = match[2].replace(/[`*_]/g, "");
    const base = sectionId(title);
    const count = used.get(base) ?? 0;
    used.set(base, count + 1);
    return [{ title, id: count ? `${base}-${count}` : base, depth: match[1].length, line: index + 1 }];
  });
}
