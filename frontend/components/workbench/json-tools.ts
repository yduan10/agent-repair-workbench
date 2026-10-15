/** UI-08: a small, exact JSON reader for the evidence editor.
 *
 * It never converts values: every node keeps its source offsets, so the
 * formatter can re-emit number and string tokens byte-for-byte and a JSON
 * Pointer from a finding can be mapped back to a text range. Grammar follows
 * RFC 8259 as enforced by the Python checker (no NaN/Infinity, no comments,
 * no trailing commas, no raw control characters in strings, no duplicate keys,
 * no leading BOM).
 */

export type JsonKind = "object" | "array" | "string" | "number" | "boolean" | "null";
export type JsonMember = { key: string; keyFrom: number; keyTo: number; value: JsonNode };
export type JsonNode = {
  kind: JsonKind;
  from: number;
  to: number;
  members?: JsonMember[];
  items?: JsonNode[];
};
export type JsonIssueKind = "syntax" | "duplicate" | "bom";
export type JsonIssue = { from: number; to: number; message: string; severity: "error" | "warning"; kind: JsonIssueKind };
export type JsonAnalysis = { root: JsonNode | null; issues: JsonIssue[]; bom: boolean };
export type LineBreak = "\n" | "\r\n";

const MAX_NESTING = 512;
const NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
const PLAIN = /[^"\\\u0000-\u001f]*/y;
const HEX4 = /[0-9a-fA-F]{4}/y;

class SyntaxProblem extends Error {
  constructor(readonly from: number, readonly to: number, message: string) {
    super(message);
  }
}

function describeChar(text: string, at: number) {
  if (at >= text.length) return "内容意外结束";
  const code = text.codePointAt(at)!;
  if (code < 0x20 || code === 0x7f || code === 0xfeff) return `意外的字符 U+${code.toString(16).toUpperCase().padStart(4, "0")}`;
  return `意外的字符 “${String.fromCodePoint(code)}”`;
}

export function analyzeJson(text: string): JsonAnalysis {
  const issues: JsonIssue[] = [];
  const bom = text.charCodeAt(0) === 0xfeff;
  if (bom) issues.push({
    from: 0, to: 1, severity: "error", kind: "bom",
    message: "开头有 BOM（U+FEFF）。检查器会判定证据格式无效，删除这个字符后再检查。",
  });
  let pos = bom ? 1 : 0;
  const length = text.length;

  const space = () => {
    for (;;) {
      const c = text.charCodeAt(pos);
      if (c === 32 || c === 10 || c === 13 || c === 9) pos += 1;
      else return;
    }
  };
  const fail = (message: string, from = pos, to = Math.min(pos + 1, length)): never => {
    throw new SyntaxProblem(from, to, message);
  };
  const unexpected = (expected: string) => fail(pos >= length ? `内容意外结束，${expected}` : `${describeChar(text, pos)}，${expected}`);

  const string = (): number => {
    const start = pos;
    pos += 1;
    for (;;) {
      PLAIN.lastIndex = pos;
      PLAIN.exec(text);
      pos = PLAIN.lastIndex;
      if (pos >= length) fail("字符串缺少结束引号", start, length);
      const c = text.charCodeAt(pos);
      if (c === 34) { pos += 1; return start; }
      if (c === 92) {
        const next = text[pos + 1];
        if (next === "u") {
          HEX4.lastIndex = pos + 2;
          if (!HEX4.test(text)) fail("\\u 后面需要 4 位十六进制数", pos, Math.min(pos + 6, length));
          pos += 6;
        } else if (next !== undefined && '"\\/bfnrt'.includes(next)) pos += 2;
        else fail("无效的转义序列", pos, Math.min(pos + 2, length));
      } else fail("字符串里不能直接出现控制字符（如换行、制表符），请改用 \\n、\\t 等转义写法");
    }
  };

  const value = (depth: number): JsonNode => {
    if (depth > MAX_NESTING) fail("嵌套层级过深，无法解析");
    space();
    const start = pos;
    const c = text[pos];
    if (c === "{") {
      pos += 1;
      const members: JsonMember[] = [];
      const seen = new Set<string>();
      space();
      if (text[pos] === "}") { pos += 1; return { kind: "object", from: start, to: pos, members }; }
      for (;;) {
        space();
        if (members.length && text[pos] === "}") fail("最后一个字段后面不能有逗号");
        if (text[pos] !== '"') unexpected("字段名必须是双引号字符串");
        const keyFrom = string();
        const keyTo = pos;
        const key = JSON.parse(text.slice(keyFrom, keyTo)) as string;
        if (seen.has(key)) issues.push({
          from: keyFrom, to: keyTo, severity: "error", kind: "duplicate",
          message: `字段名 ${text.slice(keyFrom, keyTo)} 重复。检查器会判定证据格式无效。`,
        });
        seen.add(key);
        space();
        if (text[pos] !== ":") unexpected("字段名后缺少冒号");
        pos += 1;
        members.push({ key, keyFrom, keyTo, value: value(depth + 1) });
        space();
        if (text[pos] === ",") { pos += 1; continue; }
        if (text[pos] === "}") { pos += 1; return { kind: "object", from: start, to: pos, members }; }
        unexpected("缺少逗号或 }");
      }
    }
    if (c === "[") {
      pos += 1;
      const items: JsonNode[] = [];
      space();
      if (text[pos] === "]") { pos += 1; return { kind: "array", from: start, to: pos, items }; }
      for (;;) {
        space();
        if (items.length && text[pos] === "]") fail("最后一个元素后面不能有逗号");
        items.push(value(depth + 1));
        space();
        if (text[pos] === ",") { pos += 1; continue; }
        if (text[pos] === "]") { pos += 1; return { kind: "array", from: start, to: pos, items }; }
        unexpected("缺少逗号或 ]");
      }
    }
    if (c === '"') { string(); return { kind: "string", from: start, to: pos }; }
    if (c === "-" || (c !== undefined && c >= "0" && c <= "9")) {
      NUMBER.lastIndex = pos;
      if (!NUMBER.test(text)) {
        if (text.startsWith("-Infinity", pos)) fail("JSON 不支持 NaN 或 Infinity", pos, pos + 9);
        fail("数字格式无效");
      }
      pos = NUMBER.lastIndex;
      const after = text[pos];
      if (after !== undefined && /[0-9.eE+-]/.test(after)) fail("数字格式无效", start, pos + 1);
      return { kind: "number", from: start, to: pos };
    }
    for (const [word, kind] of [["true", "boolean"], ["false", "boolean"], ["null", "null"]] as const) {
      if (text.startsWith(word, pos)) { pos += word.length; return { kind, from: start, to: pos }; }
    }
    if (pos >= length) return fail(depth === 0 ? "内容为空" : "内容意外结束，缺少值", length, length);
    if (/^(NaN|-?Infinity)/.test(text.slice(pos, pos + 9))) fail("JSON 不支持 NaN 或 Infinity", pos, pos + (text.slice(pos).match(/^-?\w+/)?.[0].length ?? 1));
    return unexpected("这里需要一个值");
  };

  let root: JsonNode | null = null;
  try {
    root = value(0);
    space();
    if (pos < length) fail("JSON 结束后还有多余内容", pos, length);
  } catch (error) {
    if (!(error instanceof SyntaxProblem)) throw error;
    root = null;
    issues.push({ from: error.from, to: Math.max(error.from, error.to), message: error.message, severity: "error", kind: "syntax" });
  }
  return { root, issues, bom };
}

/** "\r\n" only when every line break in the text is CRLF; otherwise "\n" (any stray CR stays a visible character). */
export function detectLineBreak(text: string): LineBreak {
  if (!text.includes("\r\n")) return "\n";
  return /\r(?!\n)|(?<!\r)\n/.test(text) ? "\n" : "\r\n";
}

export function lineColumn(text: string, offset: number) {
  let line = 1;
  let index = text.indexOf("\n");
  while (index !== -1 && index < offset) {
    line += 1;
    index = text.indexOf("\n", index + 1);
  }
  const lineStart = text.lastIndexOf("\n", offset - 1) + 1;
  return { line, column: offset - lineStart + 1 };
}

export function describeIssue(text: string, issue: JsonIssue) {
  const { line, column } = lineColumn(text, issue.from);
  return `第 ${line} 行第 ${column} 列：${issue.message}`;
}

/** Re-indent with two spaces. Keys, strings and numbers are copied from the
 * source text unchanged, so no value or number precision can change. Returns
 * null when the text is not syntactically valid JSON. A leading BOM, the line
 * break style and a trailing line break are kept. */
export function formatJson(text: string, analysis: JsonAnalysis): string | null {
  const { root } = analysis;
  if (!root || analysis.issues.some(issue => issue.kind === "syntax")) return null;
  const nl = detectLineBreak(text);
  const parts: string[] = [];
  const emit = (node: JsonNode, indent: string) => {
    if (node.kind === "object" && node.members!.length) {
      const inner = indent + "  ";
      parts.push("{", nl);
      node.members!.forEach((member, index) => {
        parts.push(inner, text.slice(member.keyFrom, member.keyTo), ": ");
        emit(member.value, inner);
        parts.push(index < node.members!.length - 1 ? "," : "", nl);
      });
      parts.push(indent, "}");
    } else if (node.kind === "array" && node.items!.length) {
      const inner = indent + "  ";
      parts.push("[", nl);
      node.items!.forEach((item, index) => {
        parts.push(inner);
        emit(item, inner);
        parts.push(index < node.items!.length - 1 ? "," : "", nl);
      });
      parts.push(indent, "]");
    } else if (node.kind === "object") parts.push("{}");
    else if (node.kind === "array") parts.push("[]");
    else parts.push(text.slice(node.from, node.to));
  };
  if (analysis.bom) parts.push("\uFEFF");
  emit(root, "");
  if (/\n[ \t\r\n]*$/.test(text)) parts.push(nl);
  return parts.join("");
}

function decode(pointer: string) {
  if (pointer === "") return [];
  return pointer.replace(/^\//, "").split("/").map(part => part.replace(/~1/g, "/").replace(/~0/g, "~"));
}

export type Resolved = { node: JsonNode; from: number; to: number; exact: boolean; depth: number };

/** Map a JSON Pointer to the source range of the member (key and value) or array item it names.
 * When the full path does not exist, returns the deepest existing ancestor with exact=false. */
export function resolvePointer(root: JsonNode | null, pointer: string): Resolved | null {
  if (!root) return null;
  let node = root;
  let from = root.from;
  let to = root.to;
  let depth = 0;
  for (const part of decode(pointer)) {
    if (node.kind === "object") {
      const member = node.members!.find(item => item.key === part);
      if (!member) return { node, from, to, exact: false, depth };
      node = member.value;
      from = member.keyFrom;
      to = member.value.to;
    } else if (node.kind === "array" && /^(0|[1-9]\d*)$/.test(part) && Number(part) < node.items!.length) {
      node = node.items![Number(part)];
      from = node.from;
      to = node.to;
    } else return { node, from, to, exact: false, depth };
    depth += 1;
  }
  return { node, from, to, exact: true, depth };
}

/** The JSON Schema type name of a value node; integers are numbers written without a fraction or exponent. */
export function jsonTypeOf(text: string, node: JsonNode) {
  if (node.kind !== "number") return node.kind;
  return /[.eE]/.test(text.slice(node.from, node.to)) ? "number" : "integer";
}
