"use client";
/** UI-08: evidence editor. Renders a plain textarea (SSR and until CodeMirror
 * has loaded, or if it fails to load), then swaps in CodeMirror. The parent owns
 * the text; this component never rewrites it except on explicit replace. */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Upload } from "lucide-react";
import type { EditorCallbacks, EvidenceView } from "./codemirror";

export type EvidenceEditorHandle = {
  focus: () => void;
  /** Select and highlight a source range; scrolls it into view. */
  reveal: (from: number, to: number, focus?: boolean) => void;
};

type Props = EditorCallbacks & {
  value: string;
  disabled: boolean;
  labelledBy: string;
  describedBy: string;
};

export const EvidenceEditor = forwardRef<EvidenceEditorHandle, Props>(function EvidenceEditor(
  { value, disabled, labelledBy, describedBy, onChange, onRun, onFile }, ref,
) {
  const host = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const editor = useRef<EvidenceView | null>(null);
  const callbacks = useRef<EditorCallbacks>({ onChange, onRun, onFile });
  const latest = useRef({ value, labelledBy, describedBy });
  const [ready, setReady] = useState(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    callbacks.current = { onChange, onRun, onFile };
    latest.current = { value, labelledBy, describedBy };
  });

  useEffect(() => {
    let cancelled = false;
    import("./codemirror").then(({ createEvidenceView }) => {
      if (cancelled || !host.current) return;
      const area = textarea.current;
      const hadFocus = area !== null && document.activeElement === area;
      const selection = area ? [area.selectionStart, area.selectionEnd] as const : null;
      // The textarea is controlled, so the parent's value already includes any edits made while loading.
      const text = latest.current.value;
      editor.current = createEvidenceView(host.current, text, {
        "aria-labelledby": latest.current.labelledBy,
        "aria-describedby": latest.current.describedBy,
        id: "evidence",
      }, callbacks);
      setReady(true);
      if (hadFocus) {
        editor.current.view.focus();
        if (selection) editor.current.view.dispatch({ selection: { anchor: Math.min(selection[0], text.length), head: Math.min(selection[1], text.length) } });
      }
    }).catch(() => { /* keep the textarea */ });
    return () => {
      cancelled = true;
      editor.current?.destroy();
      editor.current = null;
    };
  }, []);

  useEffect(() => { editor.current?.replace(value); }, [value, ready]);
  useEffect(() => { editor.current?.setEditable(!disabled); }, [disabled, ready]);

  useImperativeHandle(ref, () => ({
    focus: () => (editor.current ? editor.current.view.focus() : textarea.current?.focus()),
    reveal: (from, to, focus) => {
      if (editor.current) return editor.current.reveal(from, to, focus);
      const area = textarea.current;
      if (!area) return;
      // The textarea normalises CRLF to LF, so shift offsets taken from the exact text.
      const text = latest.current.value;
      const shift = (offset: number) => offset - (text.slice(0, offset).match(/\r\n/g)?.length ?? 0);
      area.focus();
      area.setSelectionRange(shift(from), shift(to));
    },
  }), []);

  const hasFiles = (event: React.DragEvent) => Array.from(event.dataTransfer.types).includes("Files");
  return <div
    className="wb-code"
    data-dragging={dragging || undefined}
    data-disabled={disabled || undefined}
    onDragEnter={event => { if (hasFiles(event) && !disabled) { event.preventDefault(); setDragging(true); } }}
    onDragOver={event => { if (hasFiles(event)) { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? "none" : "copy"; } }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={event => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      setDragging(false);
      const file = event.dataTransfer.files[0];
      if (file && !disabled) onFile(file);
    }}
  >
    <div ref={host} className="wb-code-host" hidden={!ready} />
    {!ready && <textarea
      ref={textarea}
      id="evidence"
      name="evidence"
      className="wb-textarea"
      value={value}
      disabled={disabled}
      spellCheck={false}
      autoComplete="off"
      autoCapitalize="off"
      wrap="off"
      translate="no"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      placeholder="粘贴调用证据 JSON，或把 .json 文件拖到这里"
      onChange={event => onChange(event.target.value)}
      onKeyDown={event => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); onRun(); }
      }}
    />}
    {dragging && <div className="wb-drop" aria-hidden="true"><Upload size={18} />松开即可导入文件</div>}
  </div>;
});
