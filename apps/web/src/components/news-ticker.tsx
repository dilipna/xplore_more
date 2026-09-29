import Link from "next/link";
import { getTopStories } from "@/lib/api";
import { relativeTime } from "@/lib/format";

/**
 * A scrolling strip of the feed's current top stories (real ranked data, re-fetched on every
 * render). Rendered twice so a -50% translate loops seamlessly; the second copy is hidden from
 * assistive tech. Renders nothing when the API is down: the pages say so on their own.
 */
export async function NewsTicker() {
  const result = await getTopStories();
  const stories = result.data?.results ?? [];
  if (stories.length === 0) return null;

  const items = (hidden: boolean) =>
    stories.map((s) => (
      <li
        key={`${hidden ? "b" : "a"}-${s.id}`}
        aria-hidden={hidden || undefined}
        className="flex shrink-0 items-center gap-3 pr-10"
      >
        <span className="font-mono text-[10px] text-signal-400/70">◆</span>
        <Link
          href={`/stories/${s.id}`}
          tabIndex={hidden ? -1 : undefined}
          className="text-[13px] text-fg-200 transition-colors hover:text-signal-300"
        >
          {s.title.length > 110 ? `${s.title.slice(0, 109).trimEnd()}…` : s.title}
        </Link>
        <span className="font-mono text-[10px] text-fg-600">
          {s.source_count > 1 ? `${s.source_count} sources · ` : ""}
          {relativeTime(s.published_at ?? s.first_seen_at)}
        </span>
      </li>
    ));

  return (
    <div className="border-b hairline bg-field-950/90">
      <div className="mx-auto flex max-w-[1400px] items-center gap-4 px-5">
        <span className="flex shrink-0 items-center gap-2 border-r hairline py-2 pr-4 font-mono text-[10px] font-semibold tracking-[0.2em] text-signal-400">
          <span className="live-dot" aria-hidden="true" />
          TOP NEWS
        </span>
        <div className="ticker-mask min-w-0 flex-1 overflow-hidden py-2">
          <ul className="ticker-track flex w-max animate-ticker" aria-label="Top stories right now">
            {items(false)}
            {items(true)}
          </ul>
        </div>
      </div>
    </div>
  );
}
