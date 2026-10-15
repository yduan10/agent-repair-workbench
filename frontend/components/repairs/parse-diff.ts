/** Parses a single-file unified diff (difflib / git format) into rows for the diff viewer. */

export type DiffLine = {
  kind: "add" | "del" | "ctx";
  /** The raw line, including its leading sign character. */
  text: string;
  oldLine: number | null;
  newLine: number | null;
  /** Changed character range within the content (after the sign), for paired edits. */
  word?: [number, number];
};
export type DiffRow =
  | DiffLine
  | { kind: "hunk"; text: string; section: string }
  | { kind: "note"; text: string };
export type ParsedDiff = {
  oldPath: string | null;
  newPath: string | null;
  rows: DiffRow[];
  additions: number;
  deletions: number;
  hunks: number;
};

const HUNK = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$/;

/** "baseline/source/server.py\t2026-…" → "source/server.py". */
function cleanPath(value: string) {
  const path = value.split("\t")[0].trim();
  if (path === "/dev/null") return null;
  const [head, ...rest] = path.split("/");
  return rest.length && ["a", "b", "baseline", "candidate"].includes(head) ? rest.join("/") : path;
}

export function parseUnifiedDiff(text: string): ParsedDiff {
  const lines = text.split("\n");
  if (lines.at(-1) === "") lines.pop();
  const rows: DiffRow[] = [];
  let oldPath: string | null = null;
  let newPath: string | null = null;
  let oldNo = 0, newNo = 0, oldLeft = 0, newLeft = 0;
  let additions = 0, deletions = 0, hunks = 0;
  for (const raw of lines) {
    const line = raw.replace(/\r$/, "");
    const inHunk = oldLeft > 0 || newLeft > 0;
    if (!inHunk) {
      if (line.startsWith("--- ") && oldPath === null) { oldPath = cleanPath(line.slice(4)); continue; }
      if (line.startsWith("+++ ") && newPath === null) { newPath = cleanPath(line.slice(4)); continue; }
      const match = HUNK.exec(line);
      if (match) {
        oldNo = Number(match[1]); newNo = Number(match[3]);
        oldLeft = match[2] === undefined ? 1 : Number(match[2]);
        newLeft = match[4] === undefined ? 1 : Number(match[4]);
        hunks += 1;
        rows.push({ kind: "hunk", text: line, section: match[5] ?? "" });
        continue;
      }
      if (line.startsWith("\\")) { rows.push({ kind: "note", text: line }); continue; }
      // Change lines without a hunk header: keep them, but without line numbers.
      if (line.startsWith("+")) { rows.push({ kind: "add", text: line, oldLine: null, newLine: null }); additions += 1; continue; }
      if (line.startsWith("-")) { rows.push({ kind: "del", text: line, oldLine: null, newLine: null }); deletions += 1; continue; }
      rows.push({ kind: "note", text: line });
      continue;
    }
    if (line.startsWith("+")) {
      rows.push({ kind: "add", text: line, oldLine: null, newLine: newNo++ });
      newLeft -= 1; additions += 1;
    } else if (line.startsWith("-")) {
      rows.push({ kind: "del", text: line, oldLine: oldNo++, newLine: null });
      oldLeft -= 1; deletions += 1;
    } else if (line.startsWith("\\")) {
      rows.push({ kind: "note", text: line });
    } else {
      rows.push({ kind: "ctx", text: line, oldLine: oldNo++, newLine: newNo++ });
      oldLeft -= 1; newLeft -= 1;
    }
  }
  markWords(rows);
  return { oldPath, newPath, rows, additions, deletions, hunks };
}

/** Pairs each run of deletions with the following run of additions and marks the changed span. */
function markWords(rows: DiffRow[]) {
  let i = 0;
  while (i < rows.length) {
    if (rows[i].kind !== "del") { i += 1; continue; }
    const dels: DiffLine[] = [];
    while (i < rows.length && rows[i].kind === "del") dels.push(rows[i++] as DiffLine);
    const adds: DiffLine[] = [];
    while (i < rows.length && rows[i].kind === "add") adds.push(rows[i++] as DiffLine);
    if (dels.length !== adds.length) continue;
    dels.forEach((del, index) => {
      const add = adds[index];
      const a = del.text.slice(1), b = add.text.slice(1);
      let start = 0;
      while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
      let end = 0;
      while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end += 1;
      const shared = start + end;
      // Only highlight when the lines are recognisably the same line with an edit.
      if (shared < 4 || shared < Math.min(a.length, b.length) * 0.3) return;
      del.word = [start, a.length - end];
      add.word = [start, b.length - end];
    });
  }
}
