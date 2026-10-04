import type { NewsItem } from "@/lib/events";

import { SectionError } from "./Section";

export function NewsList({ items, error }: { items: NewsItem[]; error?: string }) {
  if (error && items.length === 0) return <SectionError message={error} />;
  if (items.length === 0) return <p className="text-sm text-muted">No recent news found.</p>;
  return (
    <ul className="arrive divide-y divide-rule">
      {items.slice(0, 6).map((item) => (
        <li key={item.url} className="py-2.5 first:pt-0">
          <a href={item.url} target="_blank" rel="noreferrer" className="group block">
            <span className="text-sm leading-snug group-hover:text-accent group-focus-visible:text-accent">{item.title}</span>
            <span className="mt-0.5 block font-mono text-[0.65rem] uppercase tracking-wider text-muted">
              {item.domain}
              {item.published ? ` · ${item.published.slice(0, 10)}` : ""}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
