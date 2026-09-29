import Link from "next/link";
import type { StorySummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

function Meta({ story }: { story: StorySummary }) {
  return (
    <p className="mt-1.5 flex flex-wrap gap-x-2 text-xs text-fg-500">
      {story.source_count > 1 ? (
        <span className="text-signal-400">{story.source_count} sources</span>
      ) : (
        <span>{story.sources[0]}</span>
      )}
      <span aria-hidden="true">·</span>
      <span>{relativeTime(story.published_at ?? story.first_seen_at)}</span>
    </p>
  );
}

/** A front page: the top-ranked story as the lead, the next ones as a numbered list. */
export function TopStories({ stories, count = 10 }: { stories: StorySummary[]; count?: number }) {
  const [lead, ...rest] = stories;
  if (!lead) return null;
  return (
    <div>
      <article className="panel neon-edge relative p-6">
        <p className="text-xs font-semibold text-signal-400">Top story</p>
        <h3 className="mt-2 text-pretty text-2xl leading-snug font-semibold tracking-tight text-fg-50 [overflow-wrap:anywhere] md:text-[28px]">
          <Link href={`/stories/${lead.id}`} className="after:absolute after:inset-0 hover:text-signal-300">
            {lead.title}
          </Link>
        </h3>
        <Meta story={lead} />
      </article>

      <ol className="mt-2">
        {rest.slice(0, count - 1).map((s, i) => (
          <li key={s.id} className="group relative flex gap-4 border-b hairline py-3.5">
            <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-sm text-fg-600 tabular-nums">{i + 2}</span>
            <div className="min-w-0 flex-1">
              <Link
                href={`/stories/${s.id}`}
                className="text-[15px] leading-snug text-fg-50 [overflow-wrap:anywhere] after:absolute after:inset-0 group-hover:text-signal-300"
              >
                {s.title}
              </Link>
              <Meta story={s} />
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
