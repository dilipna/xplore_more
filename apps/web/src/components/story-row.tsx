import Link from "next/link";
import type { StorySummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

export function StoryRow({ story, rank }: { story: StorySummary; rank: number }) {
  const multi = story.source_count > 1;
  return (
    <li className="panel panel-hover relative flex gap-5 p-5">
      <span className="hidden w-7 shrink-0 pt-0.5 text-right font-mono text-sm text-fg-600 tabular-nums md:block">
        {String(rank).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="text-pretty text-[16px] leading-snug text-fg-50">
          <Link href={`/stories/${story.id}`} className="after:absolute after:inset-0">
            {story.title}
          </Link>
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-fg-500">
          <span className={multi ? "text-signal-300" : ""}>
            {multi ? `${story.source_count} sources → 1 story` : "1 source"}
          </span>
          <span className="truncate">{story.sources.slice(0, 4).join(" · ")}</span>
          <span>{relativeTime(story.published_at ?? story.first_seen_at)}</span>
        </div>
      </div>
    </li>
  );
}
