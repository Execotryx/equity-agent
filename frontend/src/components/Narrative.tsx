import ReactMarkdown from "react-markdown";

import { Placeholder, SectionError } from "./Section";

/** The Writer's note as markdown, growing while it streams. Raw HTML in the text is not rendered. */
export function Narrative({ text, streaming, error }: { text: string; streaming: boolean; error?: string }) {
  if (!text && error) return <SectionError message={error} />;
  if (!text) return <Placeholder label="The writer starts once the data branches finish…" lines={5} />;
  return (
    <div data-testid="narrative" className={`prose-note max-w-[68ch] ${streaming ? "caret" : ""}`}>
      <ReactMarkdown skipHtml>{text}</ReactMarkdown>
      {error ? <SectionError message={error} /> : null}
    </div>
  );
}

export const DISCLAIMER = "Educational project - not investment advice.";

export function Disclaimer() {
  return (
    <p
      role="note"
      className="sticky bottom-0 z-30 border-t border-rule bg-paper/95 px-4 py-2 text-center font-mono text-[0.7rem] uppercase tracking-[0.14em] text-muted backdrop-blur"
    >
      {DISCLAIMER}
    </p>
  );
}
