/** UI-08: CodeMirror setup for the evidence editor. Loaded with a dynamic
 * import from evidence-editor.tsx so it only ships on /workbench.
 *
 * Text fidelity: the document is created with an explicit line separator
 * (CRLF only when the whole text uses CRLF, otherwise LF with stray CRs kept as
 * visible characters), so state.sliceDoc() returns exactly the text that was
 * loaded. Nothing here parses or re-serialises values. */
import { Compartment, EditorState, Prec, StateEffect, StateField, type Extension } from "@codemirror/state";
import {
  Decoration, EditorView, drawSelection, highlightActiveLine, highlightActiveLineGutter,
  highlightSpecialChars, keymap, lineNumbers, placeholder,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { bracketMatching, foldGutter, foldKeymap, indentOnInput, syntaxHighlighting } from "@codemirror/language";
import { json } from "@codemirror/lang-json";
import { linter, lintGutter, lintKeymap, type Diagnostic } from "@codemirror/lint";
// Transitive dependency of @codemirror/language; emits tok-* classes that workbench.css colours with design tokens.
import { classHighlighter } from "@lezer/highlight";
import { analyzeJson, detectLineBreak, lineColumn } from "./json-tools";

export type EditorCallbacks = {
  onChange: (text: string) => void;
  onRun: () => void;
  onFile: (file: File) => void;
};

const setTarget = StateEffect.define<{ from: number; to: number } | null>();
const targetMark = Decoration.mark({ class: "cm-wb-target" });
const targetField = StateField.define({
  create: () => Decoration.none,
  update(value, tr) {
    for (const effect of tr.effects) if (effect.is(setTarget)) {
      return effect.value && effect.value.to > effect.value.from ? Decoration.set([targetMark.range(effect.value.from, effect.value.to)]) : Decoration.none;
    }
    return tr.docChanged ? Decoration.none : value.map(tr.changes);
  },
  provide: field => EditorView.decorations.from(field),
});

const jsonLint = linter(view => {
  // LF-joined on purpose: diagnostic offsets must be CodeMirror positions (one per line break).
  const text = view.state.doc.toString();
  if (!text.trim()) return [];
  return analyzeJson(text).issues.map((issue): Diagnostic => {
    const { line, column } = lineColumn(text, issue.from);
    return {
      from: issue.from,
      to: issue.to,
      severity: issue.severity,
      source: "JSON",
      message: `第 ${line} 行第 ${column} 列：${issue.message}`,
    };
  });
}, { delay: 250 });

const theme = EditorView.theme({
  "&": { height: "100%", backgroundColor: "var(--code-bg)", color: "var(--code-text)", fontSize: "12.5px" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.65", overflow: "auto" },
  ".cm-content": { padding: "10px 0 24px", caretColor: "var(--text)" },
  ".cm-line": { padding: "0 16px 0 8px" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--text)" },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection":
    { backgroundColor: "color-mix(in srgb, var(--accent) 22%, transparent)" },
  ".cm-gutters": { backgroundColor: "var(--code-bg)", color: "color-mix(in srgb, var(--text-3) 60%, var(--text-2))", border: "none", borderRight: "1px solid var(--border)" },
  ".cm-lineNumbers .cm-gutterElement": { minWidth: "34px", padding: "0 6px 0 12px", fontVariantNumeric: "tabular-nums" },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--text) 4%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--text)" },
  ".cm-foldGutter .cm-gutterElement": { padding: "0 4px", color: "var(--text-3)", cursor: "pointer" },
  ".cm-foldPlaceholder": { backgroundColor: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-2)", borderRadius: "var(--r-sm)", padding: "0 4px", margin: "0 2px" },
  "&.cm-focused .cm-matchingBracket": { backgroundColor: "color-mix(in srgb, var(--accent) 16%, transparent)", outline: "1px solid color-mix(in srgb, var(--accent) 40%, transparent)" },
  "&.cm-focused .cm-nonmatchingBracket": { backgroundColor: "var(--fail-soft)" },
  ".cm-specialChar": { color: "var(--fail)" },
  ".cm-placeholder": { color: "var(--text-3)" },
  ".cm-wb-target": { backgroundColor: "var(--accent-soft)", boxShadow: "0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent)", borderRadius: "2px" },
  ".cm-lintRange-error": { backgroundImage: "none", textDecoration: "underline wavy var(--fail)", textDecorationSkipInk: "none", textUnderlineOffset: "3px" },
  ".cm-lintRange-warning": { backgroundImage: "none", textDecoration: "underline wavy var(--unknown)", textUnderlineOffset: "3px" },
  ".cm-lint-marker": { content: "none", width: "7px", height: "7px", margin: "0 0 0 6px", borderRadius: "50%" },
  ".cm-lint-marker-error": { backgroundColor: "var(--fail)" },
  ".cm-lint-marker-warning": { backgroundColor: "var(--unknown)" },
  ".cm-gutter-lint": { width: "14px" },
  ".cm-gutter-lint .cm-gutterElement": { padding: "0", display: "flex", alignItems: "center" },
  ".cm-tooltip": { backgroundColor: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", boxShadow: "var(--shadow-pop)", overflow: "hidden" },
  ".cm-tooltip-lint": { padding: "0" },
  ".cm-diagnostic": { padding: "6px 10px", fontFamily: "var(--font-sans)", fontSize: "var(--fs-xs)", borderLeft: "3px solid var(--border-strong)" },
  ".cm-diagnostic-error": { borderLeftColor: "var(--fail)" },
  ".cm-diagnostic-warning": { borderLeftColor: "var(--unknown)" },
  ".cm-diagnosticSource": { display: "none" },
  ".cm-panels": { backgroundColor: "var(--surface)", color: "var(--text)" },
  ".cm-panels.cm-panels-bottom": { borderTop: "1px solid var(--border)" },
  ".cm-panel.cm-panel-lint ul [aria-selected]": { backgroundColor: "var(--accent-soft)" },
});

export type EvidenceView = {
  view: EditorView;
  /** Replace the whole document. Keeps undo history unless the line-break style changes. */
  replace: (text: string) => void;
  setEditable: (editable: boolean) => void;
  /** Offsets are positions in the exact text (as returned by getText). */
  reveal: (from: number, to: number, focus?: boolean) => void;
  getText: () => string;
  destroy: () => void;
};

export function createEvidenceView(parent: HTMLElement, text: string, attributes: Record<string, string>, callbacks: { current: EditorCallbacks }): EvidenceView {
  const editable = new Compartment();
  const extensions = (separator: string, isEditable: boolean): Extension[] => [
    EditorState.lineSeparator.of(separator),
    EditorState.tabSize.of(2),
    editable.of([EditorView.editable.of(isEditable), EditorState.readOnly.of(!isEditable)]),
    EditorView.clipboardInputFilter.of(pasted => separator === "\r\n" ? pasted.replace(/\r?\n/g, "\r\n") : pasted.replace(/\r\n/g, "\n")),
    Prec.highest(keymap.of([{ key: "Mod-Enter", preventDefault: true, run: () => { callbacks.current.onRun(); return true; } }])),
    lineNumbers(),
    foldGutter({ openText: "⌄", closedText: "›" }),
    lintGutter(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    highlightActiveLine(),
    json(),
    syntaxHighlighting(classHighlighter),
    jsonLint,
    targetField,
    placeholder("粘贴调用证据 JSON，或把 .json 文件拖到这里"),
    keymap.of([...defaultKeymap, ...historyKeymap, ...foldKeymap, ...lintKeymap]),
    // tabindex makes the editable content count as focusable content of the scroll container (axe scrollable-region-focusable).
    EditorView.contentAttributes.of({ ...attributes, tabindex: "0", spellcheck: "false", autocorrect: "off", autocapitalize: "off", translate: "no" }),
    EditorView.domEventHandlers({
      drop(event) {
        const file = event.dataTransfer?.files?.[0];
        if (!file) return false;
        event.preventDefault();
        return true; // the wrapper's drop handler imports the file
      },
    }),
    EditorView.updateListener.of(update => {
      // sliceDoc joins lines with the configured separator; doc.toString() would always use "\n".
      if (update.docChanged) callbacks.current.onChange(update.state.sliceDoc());
    }),
    theme,
  ];
  let separator = detectLineBreak(text);
  let isEditable = true;
  const view = new EditorView({ parent, state: EditorState.create({ doc: text, extensions: extensions(separator, isEditable) }) });
  return {
    view,
    getText: () => view.state.sliceDoc(),
    replace(next) {
      if (next === view.state.sliceDoc()) return;
      const nextSeparator = detectLineBreak(next);
      if (nextSeparator !== separator) {
        separator = nextSeparator;
        view.setState(EditorState.create({ doc: next, extensions: extensions(separator, isEditable) }));
        return;
      }
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: view.state.toText(next) }, selection: { anchor: 0 }, effects: setTarget.of(null) });
      view.scrollDOM.scrollTop = 0;
    },
    setEditable(next) {
      if (next === isEditable) return;
      isEditable = next;
      view.dispatch({ effects: editable.reconfigure([EditorView.editable.of(next), EditorState.readOnly.of(!next)]) });
    },
    reveal(textFrom, textTo, focus = false) {
      // Offsets come from the exact text; CodeMirror counts a CRLF line break as one position.
      const toPos = (offset: number) => separator === "\r\n" ? offset - (view.state.sliceDoc().slice(0, offset).match(/\r\n/g)?.length ?? 0) : offset;
      const from = toPos(textFrom);
      const end = Math.min(toPos(textTo), view.state.doc.length);
      const start = Math.min(from, end);
      view.dispatch({ selection: { anchor: start }, effects: setTarget.of({ from: start, to: end }) });
      // Centre the line inside the editor only; EditorView.scrollIntoView would also scroll the page.
      const block = view.lineBlockAt(start);
      const scroller = view.scrollDOM;
      scroller.scrollTo({ top: Math.max(0, block.top + view.documentPadding.top - scroller.clientHeight / 2 + block.height / 2) });
      const rect = view.dom.getBoundingClientRect();
      if (rect.top < 0 || rect.bottom > window.innerHeight) {
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        view.dom.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
      }
      if (focus) view.contentDOM.focus({ preventScroll: true });
    },
    destroy: () => view.destroy(),
  };
}
