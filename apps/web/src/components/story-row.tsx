import Link from "next/link";
import type { StorySummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

export function StoryRow({ story, rank }: { story: StorySummary; rank: number }) {
  return (
    <li className="group relative flex gap-4 border-b hairline py-3.5">
      <span className="w-6 shrink-0 pt-0.5 text-right font-mono text-sm text-fg-600 tabular-nums">{rank}</span>
      <div className="min-w-0 flex-1">
        <Link
          href={`/stories/${story.id}`}
          className="text-[15px] leading-snug text-fg-50 [overflow-wrap:anywhere] after:absolute after:inset-0 group-hover:text-signal-300"
        >
          {story.title}
        </Link>
        <p className="mt-1.5 flex flex-wrap gap-x-2 text-xs text-fg-500">
          {story.source_count > 1 ? (
            <span className="text-signal-400">{story.source_count} sources</span>
          ) : (
            <span>{story.sources[0]}</span>
          )}
          <span aria-hidden="true">·</span>
          <span>{relativeTime(story.published_at ?? story.first_seen_at)}</span>
        </p>
      </div>
    </li>
  );
}
