import Link from "next/link";
import { getTopStories } from "@/lib/api";
import { relativeTime } from "@/lib/format";

/**
 * A scrolling strip of the feed's current top stories. Rendered twice so a -50% translate loops
 * seamlessly; the copy is hidden from assistive tech. Renders nothing when the API is down.
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
        className="flex shrink-0 items-center gap-2 pr-8"
      >
        <Link
          href={`/stories/${s.id}`}
          tabIndex={hidden ? -1 : undefined}
          className="text-[13px] text-fg-200 transition-colors hover:text-signal-300"
        >
          {s.title.length > 100 ? `${s.title.slice(0, 99).trimEnd()}…` : s.title}
        </Link>
        <span className="text-[11px] text-fg-600">{relativeTime(s.published_at ?? s.first_seen_at)}</span>
        <span className="pl-6 text-fg-600" aria-hidden="true">
          /
        </span>
      </li>
    ));

  return (
    <div className="border-b hairline bg-field-900/60">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-5">
        <span className="flex shrink-0 items-center gap-2 py-2 text-xs font-semibold text-signal-400">
          <span className="live-dot" aria-hidden="true" />
          Trending
        </span>
        <div className="ticker-mask min-w-0 flex-1 overflow-hidden py-2">
          <ul className="ticker-track flex w-max animate-ticker" aria-label="Trending stories">
            {items(false)}
            {items(true)}
          </ul>
        </div>
      </div>
    </div>
  );
}
