/** JSON Pointer rendered as segments; the leaf is highlighted as the failing location. */
export function decodePointer(pointer: string) {
  if (pointer === "" || pointer === "/") return [];
  return pointer.replace(/^\//, "").split("/").map(part => part.replace(/~1/g, "/").replace(/~0/g, "~"));
}

export function PathTrail({ pointer, tone = "fail", label }: { pointer: string; tone?: "fail" | "neutral"; label?: string }) {
  const parts = decodePointer(pointer);
  return <span className="path-trail" data-tone={tone} translate="no" aria-label={label ? `${label} ${pointer || "/"}` : pointer || "/"} title={pointer || "/"}>
    {parts.length === 0 ? <span className="seg leaf">/</span> : parts.map((part, index) => <span key={index} style={{ display: "contents" }}>
      <span className="sep" aria-hidden="true">/</span>
      <span className={index === parts.length - 1 ? "seg leaf" : "seg"}>{part || " "}</span>
    </span>)}
  </span>;
}
